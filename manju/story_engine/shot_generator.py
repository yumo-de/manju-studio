"""
故事引擎 — 分镜头生成器（ShotGenerator）v2

改进:
  - 多线程并行生成（每场戏独立线程）
  - 一致性上下文：角色/世界观/画风信息传递给每个场景
  - shot_id 全局递增，不乱序
"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from manju.llm.llm_client import LLMClient
from manju.llm.prompt_templates import SHOT_SYSTEM, SHOT_USER
from manju.schemas.story import Camera, Shot, Story, Storyboard

logger = logging.getLogger(__name__)

# 最大并行线程数
MAX_WORKERS = 4


def _fmt_dialogue(dialogue_list: list[dict[str, str]]) -> str:
    """将对话列表格式化为可读文本。"""
    lines: list[str] = []
    for d in dialogue_list:
        speaker = d.get("speaker", "未知")
        text = d.get("text", "")
        emotion = d.get("emotion", "")
        if emotion:
            lines.append(f"  [{speaker}]({emotion}): {text}")
        else:
            lines.append(f"  [{speaker}]: {text}")
    return "\n".join(lines) if lines else "（无对话）"


def _parse_shot_id(raw_id: Any) -> int:
    """将 shot_id 转为整数，支持 "S1-03" -> 103, "shot_5" -> 5。"""
    if isinstance(raw_id, int):
        return raw_id
    if isinstance(raw_id, str):
        nums = re.findall(r"\d+", raw_id)
        if nums:
            return int(nums[-1])
    return 0


def _build_shot(raw: dict[str, Any]) -> Shot:
    """将 LLM 返回的原始 shot dict 转为 Shot 模型实例。"""
    camera_raw = raw.get("camera", {})
    camera_obj: Camera
    if isinstance(camera_raw, Camera):
        camera_obj = camera_raw
    elif isinstance(camera_raw, dict):
        camera_obj = Camera(
            type=camera_raw.get("type", "wide"),
            angle=camera_raw.get("angle", "eye"),
            move=camera_raw.get("move", "static"),
        )
    else:
        camera_obj = Camera()

    return Shot(
        shot_id=_parse_shot_id(raw.get("shot_id", 0)),
        scene=str(raw.get("scene", "")),
        duration=int(raw.get("duration", 5)),
        camera=camera_obj,
        description=str(raw.get("description", "")),
        prompt=str(raw.get("prompt", "")),
        dialogue=str(raw.get("dialogue", "")),
        speaker=str(raw.get("speaker")) if raw.get("speaker") else None,
        character=raw.get("character", []),
        bgm_mood=str(raw.get("bgm_mood", "gentle")),
        sfx=str(raw.get("sfx", "")),
    )


def _build_consistency_context(story: Story) -> str:
    """构建一致性上下文信息，传递给每个场景的 LLM 调用。

    包含角色外表、世界观、画风，确保不同场景中同一角色描述一致。
    """
    lines = ["【全局一致性设定 — 请在所有镜头中严格遵守】", ""]

    # 世界观
    lines.append(f"世界观：{story.worldview}")
    lines.append(f"题材：{story.genre}")
    lines.append(f"旁白风格：{story.narration_style}")
    lines.append("")

    # 角色表
    lines.append("【角色表】")
    for ch in story.characters:
        lines.append(
            f"- {ch.name}（{ch.role}，{ch.gender}）：{ch.personality}，"
            f"外貌：{ch.appearance}，声线：{ch.voice_style}"
        )
    lines.append("")

    # 画风参考
    from manju.visual.prompt_gen import PromptGenerator
    style_info = PromptGenerator.STYLE_PREFIX.get(
        story.genre, PromptGenerator.STYLE_PREFIX["仙侠"]
    )
    lines.append(f"画风参考：{style_info['zh']}")
    lines.append(f"英文风格标签：{style_info['en']}")
    lines.append("")

    lines.append("注意事项：")
    lines.append("- 同一角色在不同场景中外貌、服装需保持一致")
    lines.append("- 角色 names（character 字段）中英文皆可，但要保持统一")
    lines.append("- prompt 字段用英文描述画面，需与 description 中文一致")

    return "\n".join(lines)


def _process_one_scene(
    scene: dict[str, Any],
    consistency_context: str,
    shot_counter_start: int,
) -> list[Shot]:
    """处理单个场景，返回 Shot 列表。"""
    scene_id = scene.get("scene_id", 0)
    location = scene.get("location", "未知地点")
    time_ = scene.get("time", "日")
    atmosphere = scene.get("atmosphere", "")
    dialogue_list = scene.get("dialogue", [])
    action = scene.get("action", "")

    dialogue_text = _fmt_dialogue(dialogue_list)

    # 在 SHOT_USER 后追加一致性上下文
    user_prompt = SHOT_USER.format(
        scene_id=scene_id,
        location=location,
        time=time_,
        atmosphere=atmosphere,
        dialogue_text=dialogue_text,
        action=action,
    )
    user_prompt += f"\n\n{consistency_context}"

    llm = LLMClient()
    try:
        raw_response = llm.chat_json(system=SHOT_SYSTEM, user=user_prompt)
    except Exception as e:
        logger.warning("场景 %s 镜头生成失败: %s", scene_id, e)
        return []

    # 兼容两种格式
    raw_shots: list[dict[str, Any]]
    if "shots" in raw_response:
        raw_shots = raw_response["shots"]
    elif isinstance(raw_response, list):
        raw_shots = raw_response
    else:
        raw_shots = []

    shots = []
    for i, raw_shot in enumerate(raw_shots):
        if not raw_shot.get("scene"):
            raw_shot["scene"] = str(scene_id)
        raw_shot["shot_id"] = shot_counter_start + i
        shot = _build_shot(raw_shot)
        shots.append(shot)

    return shots


# =============================================================================
# ShotGenerator v2
# =============================================================================


class ShotGenerator:
    """分镜头生成器 v2 — 多线程并行，保持一致性。"""

    def __init__(self, max_workers: int = MAX_WORKERS) -> None:
        self.max_workers = max_workers

    def generate(self, story: Story, scenes: list[dict[str, Any]]) -> Storyboard:
        """多线程并行生成所有场景的镜头。

        Parameters
        ----------
        story : Story
            完整的故事对象（含角色、世界观等一致性信息）。
        scenes : list[dict]
            剧本场景列表。

        Returns
        -------
        Storyboard
            包含所有镜头、总镜头数、估计总时长的分镜板。
        """
        if not scenes:
            logger.warning("没有场景数据，返回空 Storyboard")
            return Storyboard(story=story, shots=[], total_shots=0, estimated_duration=0)

        consistency_context = _build_consistency_context(story)
        all_shots: list[Shot] = []

        logger.info(
            "开始并行生成分镜头: %d 个场景, %d 线程",
            len(scenes), self.max_workers,
        )

        # 每个场景分配 shot_counter 起始值（预估每场景 5 个镜头）
        shots_per_scene = 5  # 预估，实际以返回为准

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            for idx, scene in enumerate(scenes):
                start_id = idx * shots_per_scene + 1
                future = executor.submit(
                    _process_one_scene, scene, consistency_context, start_id
                )
                futures[future] = idx

            # 按场景顺序收集结果
            results: dict[int, list[Shot]] = {}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("场景 %d 处理异常: %s", idx + 1, e)
                    results[idx] = []

            # 按原始顺序组装
            for idx in sorted(results.keys()):
                all_shots.extend(results[idx])

        # 重新分配连续的 shot_id
        for i, shot in enumerate(all_shots, 1):
            shot.shot_id = i

        total_duration = sum(s.duration for s in all_shots)

        logger.info(
            "分镜头生成完成: %d 个镜头, %d 秒",
            len(all_shots), total_duration,
        )

        return Storyboard(
            story=story,
            shots=all_shots,
            total_shots=len(all_shots),
            estimated_duration=total_duration,
        )
