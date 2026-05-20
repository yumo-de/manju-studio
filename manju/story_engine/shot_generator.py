"""
故事引擎 — 分镜头生成器（ShotGenerator）

将剧本中的每一场戏（scene）拆解为具体镜头（Shot），返回 Storyboard。
"""

from __future__ import annotations

from typing import Any

from manju.llm.llm_client import LLMClient
from manju.llm.prompt_templates import SHOT_SYSTEM, SHOT_USER
from manju.schemas.story import Camera, Shot, Story, Storyboard


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


def _build_shot(raw: dict[str, Any]) -> Shot:
    """将 LLM 返回的原始 shot dict 转为 Shot 模型实例。"""
    camera_raw = raw.get("camera", {})
    # Camera 是 Pydantic model，支持从 dict 自动构建
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
        shot_id=int(raw.get("shot_id", 0)),
        scene=raw.get("scene", ""),
        duration=int(raw.get("duration", 5)),
        camera=camera_obj,
        description=raw.get("description", ""),
        prompt=raw.get("prompt", ""),
        dialogue=raw.get("dialogue", ""),
        speaker=raw.get("speaker", None),
        character=raw.get("character", []),
        bgm_mood=raw.get("bgm_mood", "gentle"),
        sfx=raw.get("sfx", ""),
    )


class ShotGenerator:
    """分镜头生成器 — 剧本 → Shot List"""

    def __init__(self) -> None:
        self._llm = LLMClient()

    # ── public API ─────────────────────────────────────────────────────

    def generate(self, story: Story, scenes: list[dict[str, Any]]) -> Storyboard:
        """遍历 scenes，对每个 scene 调用 LLM 生成镜头列表，合并返回 Storyboard。

        Parameters
        ----------
        story : Story
            完整的故事对象。
        scenes : list[dict]
            剧本场景列表，每项包含 scene_id, location, time, atmosphere,
            dialogue(list[dict]), action, transition 等字段。

        Returns
        -------
        Storyboard
            包含所有镜头、总镜头数、估计总时长的分镜板。
        """
        all_shots: list[Shot] = []
        shot_counter = 0  # 全局镜头编号种子

        for scene in scenes:
            scene_id = scene.get("scene_id", 0)
            location = scene.get("location", "未知地点")
            time_ = scene.get("time", "日")
            atmosphere = scene.get("atmosphere", "")
            dialogue_list = scene.get("dialogue", [])
            action = scene.get("action", "")

            dialogue_text = _fmt_dialogue(dialogue_list)

            user_prompt = SHOT_USER.format(
                scene_id=scene_id,
                location=location,
                time=time_,
                atmosphere=atmosphere,
                dialogue_text=dialogue_text,
                action=action,
            )

            raw_response = self._llm.chat_json(
                system=SHOT_SYSTEM,
                user=user_prompt,
            )

            # 兼容两种格式: {"shots": [...]} 或直接返回 shots 数组
            raw_shots: list[dict[str, Any]]
            if "shots" in raw_response:
                raw_shots = raw_response["shots"]
            elif isinstance(raw_response, list):
                raw_shots = raw_response
            else:
                raw_shots = []

            for raw_shot in raw_shots:
                # 填充 scene 字段（如果 LLM 未填写）
                if not raw_shot.get("scene"):
                    raw_shot["scene"] = str(scene_id)

                shot_counter += 1
                # 如果 LLM 没有给 shot_id 或编号混乱，用全局计数器重写
                if not raw_shot.get("shot_id"):
                    raw_shot["shot_id"] = shot_counter

                shot = _build_shot(raw_shot)
                all_shots.append(shot)

        total_duration = sum(s.duration for s in all_shots)

        return Storyboard(
            story=story,
            shots=all_shots,
            total_shots=len(all_shots),
            estimated_duration=total_duration,
        )
