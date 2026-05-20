"""
Manju Studio Pipeline 编排器 v3
--------------------------------------------------
串联所有模块实现从主题到最终视频的一键生成。

改进 v3:
  - 多线程并行图片生成（角色立绘 + 关键帧同时跑）
  - 按幕(Act)多线程生成视频片段，最后拼接
  - 分镜头保持角色/画风一致性
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── 导入各模块 ──────────────────────────────────────────────────────────────
from manju.story_engine.expander import StoryExpander
from manju.story_engine.scriptwriter import ScriptWriter
from manju.story_engine.shot_generator import ShotGenerator
from manju.tts.engine import TTSEngine
from manju.visual.tongyi_client import TongyiImageClient
from manju.visual.prompt_gen import PromptGenerator
from manju.video.compositor import VideoCompositor
from manju.schemas.story import Story, Storyboard, Shot
from manju.config import load_config

logger = logging.getLogger("pipeline")


# =============================================================================
# StepResult — 每步执行结果
# =============================================================================


class StepResult:
    """记录 Pipeline 中一个步骤的执行结果。"""

    def __init__(self, step: int, name: str) -> None:
        self.step = step
        self.name = name
        self.status: str = "pending"  # pending / success / skipped / failed
        self.message: str = ""
        self.duration: float = 0.0
        self.error: str | None = None

    def succeed(self, msg: str = "") -> None:
        self.status = "success"
        self.message = msg

    def skip(self, reason: str = "") -> None:
        self.status = "skipped"
        self.message = reason

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error
        self.message = f"❌ {error}"

    def __repr__(self) -> str:
        return f"[{self.step}/?] {self.name}: {self.status} — {self.message}"


# =============================================================================
# BGM 选择器
# =============================================================================


class BGMSelector:
    """根据镜头情绪自动选择背景音乐。

    策略（按优先级）:
      1. data/bgm_library/ 中按 mood 子目录查找
      2. 无匹配时返回 None（跳过 BGM）
    """

    MOOD_DIR_MAP: dict[str, str] = {
        "epic": "epic",
        "tense": "tense",
        "gentle": "gentle",
        "comic": "comic",
        "action": "action",
        "sad": "sad",
        "mystery": "mystery",
        "happy": "happy",
    }

    def __init__(self, bgm_dir: str = "data/bgm_library") -> None:
        self.bgm_dir = Path(bgm_dir)
        self._cache: dict[str, list[str]] = {}

    def pick(self, mood: str) -> str | None:
        """根据 mood 选择 BGM 文件路径。无匹配时返回 None。"""
        sub_dir_name = self.MOOD_DIR_MAP.get(mood, "gentle")
        bgm_files = self._scan(sub_dir_name)
        if not bgm_files:
            # fallback 到 gentle
            if sub_dir_name != "gentle":
                bgm_files = self._scan("gentle")
        if not bgm_files:
            return None
        # 简单轮转选择（后续可改为更智能的匹配）
        idx = hash(mood) % len(bgm_files)
        return bgm_files[idx]

    def _scan(self, sub_dir: str) -> list[str]:
        """扫描子目录下的 BGM 文件。"""
        if sub_dir in self._cache:
            return self._cache[sub_dir]
        dir_path = self.bgm_dir / sub_dir
        if not dir_path.exists():
            self._cache[sub_dir] = []
            return []
        files = sorted(
            str(p) for p in dir_path.iterdir()
            if p.suffix.lower() in (".mp3", ".wav", ".flac", ".m4a", ".ogg")
        )
        self._cache[sub_dir] = files
        return files


# =============================================================================
# ManjuPipeline v2
# =============================================================================


class ManjuPipeline:
    """漫剧一键生成 Pipeline — 主题 → 最终视频。"""

    def __init__(self, work_dir: str = "data/projects") -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self._config = load_config()

        # 初始化各模块
        self.expander = StoryExpander()
        self.scriptwriter = ScriptWriter()
        self.shot_generator = ShotGenerator()

        # 图像客户端 — 可选（无 API Key 时跳过图像生成）
        try:
            self.image_client = TongyiImageClient()
            self._image_available = True
        except (ValueError, KeyError):
            logger.warning("TongyiImageClient 初始化失败：缺少 API Key，将跳过图像生成")
            self.image_client = None
            self._image_available = False

        self.prompt_gen = PromptGenerator()

        # VideoCompositor 从配置读取参数
        video_cfg = self._config.get("video", {})
        fps = video_cfg.get("fps", 24)
        resolution = tuple(video_cfg.get("resolution", [1920, 1080]))
        self.compositor = VideoCompositor(fps=fps, resolution=resolution)

        # BGM 选择器
        bgm_dir = video_cfg.get("bgm_dir", "data/bgm_library")
        self.bgm_selector = BGMSelector(bgm_dir=bgm_dir)

        # TTS 引擎延迟初始化（需要输出目录）
        self._tts: TTSEngine | None = None

        logger.info(
            "Pipeline initialized: work_dir=%s, fps=%s, resolution=%s",
            self.work_dir, fps, resolution,
        )

    # ── 主入口 ───────────────────────────────────────────────────────────

    def run(self, theme: str) -> str:
        """执行完整 Pipeline，返回最终视频文件路径。

        Pipeline 步骤:
          1/8 生成故事大纲
          2/8 生成剧本
          3/8 生成分镜头
          4/8 生成图片（角色立绘 + 关键帧）
          5/8 生成配音
          6/8 选择 BGM
          7/8 合成视频（含字幕）
          8/8 最终输出
        """
        # 创建项目目录
        project_id = datetime.now(timezone.utc).strftime("proj_%Y%m%d_%H%M%S")
        proj_dir = self.work_dir / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        char_dir = proj_dir / "characters"
        keyframe_dir = proj_dir / "keyframes"
        audio_dir = proj_dir / "audio"
        video_dir = proj_dir / "video"
        for d in (char_dir, keyframe_dir, audio_dir, video_dir):
            d.mkdir(parents=True, exist_ok=True)

        # 步骤结果收集
        results: list[StepResult] = []

        start_time = time.time()
        logger.info("=" * 60)
        logger.info("Pipeline 开始 | 主题: %s | 项目: %s", theme, project_id)
        logger.info("=" * 60)

        # ── 步骤 1/8: 生成故事大纲 ──────────────────────────────────────
        sr1 = StepResult(1, "生成故事大纲")
        story = None
        try:
            story = self.expander.expand(theme)
            self._save(proj_dir / "story.json", story.model_dump())
            sr1.succeed(
                f"故事《story.title》({story.genre}), {len(story.characters)} 角色"
            )
        except Exception as e:
            sr1.fail(str(e))
            logger.exception("步骤 1 失败")
        results.append(sr1)
        self._log_step(sr1)

        # 如果故事生成失败，后面的步骤无法进行
        if sr1.status == "failed":
            elapsed = time.time() - start_time
            logger.error("故事生成失败，Pipeline 终止")
            self._save(proj_dir / "pipeline_report.json", self._build_report(theme, results))
            return ""

        # ── 步骤 2/8: 生成剧本 ──────────────────────────────────────────
        sr2 = StepResult(2, "生成剧本")
        scenes = []
        try:
            scenes = self.scriptwriter.write(story)
            self._save(proj_dir / "scenes.json", scenes)
            sr2.succeed(f"{len(scenes)} 个场景")
        except Exception as e:
            sr2.fail(str(e))
            logger.exception("步骤 2 失败")
            # 如果剧本失败但有故事，可以尝试用 acts 中的 scenes 作为降级
            if story and story.acts:
                scenes = [
                    {"scene_id": i, "location": "未知", "time": "日",
                     "atmosphere": "", "dialogue": [], "action": "",
                     "transition": "cut"}
                    for i, _ in enumerate(
                        [s for act in story.acts for s in act.scenes], 1
                    )
                ]
                sr2.skip("使用降级场景列表（基于故事大纲）")
        results.append(sr2)
        self._log_step(sr2)

        # ── 步骤 3/8: 生成分镜头 ────────────────────────────────────────
        sr3 = StepResult(3, "生成分镜头")
        storyboard = None
        try:
            storyboard = self.shot_generator.generate(story, scenes)
            self._save(proj_dir / "storyboard.json", storyboard.model_dump())
            sr3.succeed(
                f"{storyboard.total_shots} 个镜头, 预计 {storyboard.estimated_duration}s"
            )
        except Exception as e:
            sr3.fail(str(e))
            logger.exception("步骤 3 失败")
        results.append(sr3)
        self._log_step(sr3)

        # 如果分镜头失败，用一个默认单镜头 storyboard 降级
        if storyboard is None:
            from manju.schemas.story import Camera, Shot as ShotModel
            storyboard = Storyboard(
                story=story,
                shots=[
                    ShotModel(
                        shot_id=1,
                        scene="1",
                        duration=10,
                        camera=Camera(),
                        description=story.plot_summary[:100] if story else "故事",
                        prompt=story.plot_summary[:200] if story else "A scene",
                        dialogue="",
                        speaker=None,
                        character=[],
                        bgm_mood="gentle",
                    )
                ],
                total_shots=1,
                estimated_duration=10,
            )
            sr3.skip("使用降级分镜头（单镜头）")

        # ── 步骤 4/8: 生成图片（全量，多线程并行） ────────────────────────
        sr4 = StepResult(4, "生成图片")
        char_image_map: dict[str, str] = {}
        shot_image_map: dict[int, str] = {}
        MAX_IMAGE_WORKERS = 3  # 通义万相免费额度有限，控制并行数

        if self._image_available:
            try:
                style_en = self.prompt_gen.STYLE_PREFIX.get(
                    story.genre if story else "仙侠",
                    self.prompt_gen.STYLE_PREFIX["仙侠"],
                )["en"]

                # 构建所有图片生成任务
                image_tasks: list[dict] = []

                # 4a. 角色立绘（全部角色）
                for ch in (story.characters if story else []):
                    prompt = (
                        f"Portrait of {ch.name}, {ch.appearance}, "
                        f"{style_en}, "
                        f"character portrait, full body, clean background, detailed illustration"
                    )
                    image_tasks.append({
                        "type": "character",
                        "name": ch.name,
                        "prompt": prompt,
                        "output_dir": char_dir,
                        "filename": f"{ch.name}.png",
                    })

                # 4b. 关键帧（所有镜头）
                for shot in (storyboard.shots if storyboard else []):
                    full_prompt = self.prompt_gen.build_prompt(
                        shot, story.genre if story else "仙侠"
                    )
                    image_tasks.append({
                        "type": "keyframe",
                        "shot_id": shot.shot_id,
                        "prompt": full_prompt,
                        "output_dir": keyframe_dir,
                        "filename": f"shot_{shot.shot_id:04d}.png",
                    })

                # 多线程并行执行
                def _gen_one(task: dict) -> tuple[str, str | int] | None:
                    """生成单张图片，返回 (type_key, path) or None。"""
                    try:
                        urls = self.image_client.generate(task["prompt"], n=1)
                        if not urls:
                            return None
                        out_path = task["output_dir"] / task["filename"]
                        self.image_client.download(urls[0], out_path)
                        if task["type"] == "character":
                            return ("char", task["name"])
                        else:
                            return ("shot", task["shot_id"])
                    except Exception as e:
                        logger.warning("  图片生成失败 (%s): %s", task.get("filename", "?"), e)
                        return None

                with ThreadPoolExecutor(max_workers=MAX_IMAGE_WORKERS) as pool:
                    futures = {pool.submit(_gen_one, t): t for t in image_tasks}
                    done_count = 0
                    for future in as_completed(futures):
                        done_count += 1
                        result = future.result()
                        if result:
                            kind, key = result
                            if kind == "char":
                                char_image_map[key] = str(char_dir / f"{key}.png")
                            elif kind == "shot":
                                shot_image_map[key] = str(keyframe_dir / f"shot_{key:04d}.png")
                        # 通义万相免费额度限制检查
                        if done_count >= 50:
                            logger.warning("已达到每日免费上限 50 张, 停止图片生成")
                            for f in futures:
                                f.cancel()
                            break

                sr4.succeed(
                    f"角色立绘 {len(char_image_map)} 张, 关键帧 {len(shot_image_map)} 张"
                )
            except Exception as e:
                sr4.fail(str(e))
                logger.exception("步骤 4 整体异常")
        else:
            sr4.skip("未配置 API Key")
        results.append(sr4)
        self._log_step(sr4)

        # ── 步骤 5/8: 生成配音 ──────────────────────────────────────────
        sr5 = StepResult(5, "生成配音")
        audio_paths: list[Path] = []
        try:
            self._tts = TTSEngine(output_dir=str(audio_dir))

            # 构建角色信息字典供 TTS 匹配声线
            characters_dict: dict[str, dict[str, str]] = {
                ch.name: {"voice_style": ch.voice_style, "gender": ch.gender}
                for ch in (story.characters if story else [])
            }

            audio_paths = self._tts.generate_dialogue(
                shots=storyboard.shots if storyboard else [],
                characters=characters_dict,
            )
            sr5.succeed(f"{len(audio_paths)} 条配音")
        except Exception as e:
            # TTS 失败不阻塞后续流程（可以生成无声视频）
            sr5.skip(f"配音跳过: {e}")
            logger.warning("配音生成异常（跳过）: %s", e)
        results.append(sr5)
        self._log_step(sr5)

        # ── 步骤 6/8: 选择 BGM ─────────────────────────────────────────
        sr6 = StepResult(6, "选择 BGM")
        bgm_path: str | None = None
        try:
            if storyboard and storyboard.shots:
                # 取最主要的 mood（出现最多的 mood）
                from collections import Counter
                moods = [s.bgm_mood for s in storyboard.shots if s.bgm_mood]
                if moods:
                    primary_mood = Counter(moods).most_common(1)[0][0]
                    bgm_path = self.bgm_selector.pick(primary_mood)
                    if bgm_path:
                        sr6.succeed(f"BGM: {primary_mood} → {Path(bgm_path).name}")
                    else:
                        # 下载默认 BGM
                        bgm_path = self._ensure_default_bgm()
                        if bgm_path:
                            sr6.succeed(f"使用默认 BGM: {Path(bgm_path).name}")
                        else:
                            sr6.skip("无可用 BGM 文件")
                else:
                    sr6.skip("无镜头 mood 信息")
            else:
                sr6.skip("无分镜头数据")
        except Exception as e:
            sr6.skip(f"BGM 选择失败: {e}")
        results.append(sr6)
        self._log_step(sr6)

        # ── 步骤 7/8: 合成视频（按幕多线程） ──────────────────────────
        sr7 = StepResult(7, "合成视频")
        final_video = ""

        try:
            shots = storyboard.shots if storyboard else []
            if not clip_paths_from_images(shots, keyframe_dir, shot_image_map, self.compositor, self.fps):
                sr7.fail("没有可用的视频片段")
                results.append(sr7)
                self._log_step(sr7)
                elapsed = time.time() - start_time
                self._save(
                    proj_dir / "pipeline_report.json",
                    self._build_report(theme, results, elapsed),
                )
                return ""

            # 按幕（Act）分组生成视频
            acts = story.acts if story and story.acts else []
            if acts:
                final_video = compose_video_by_acts(
                    story=story,
                    shots=shots,
                    keyframe_dir=keyframe_dir,
                    video_dir=video_dir,
                    audio_dir=audio_dir,
                    bgm_path=bgm_path,
                    subtitle_entries=subtitle_entries_from_shots(shots, keyframe_dir, shot_image_map),
                )
            else:
                final_video = compose_video_flat(
                    shots=shots,
                    keyframe_dir=keyframe_dir,
                    video_dir=video_dir,
                    audio_dir=audio_dir,
                    bgm_path=bgm_path,
                    shot_image_map=shot_image_map,
                )

            if final_video:
                sr7.succeed(f"视频合成完成: {Path(final_video).name}")
            else:
                sr7.fail("视频合成为空")
        except Exception as e:
            sr7.fail(str(e))
            logger.exception("步骤 7 失败")
        results.append(sr7)
        self._log_step(sr7)

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("Pipeline 完成! 耗时: %.1fs", elapsed)
        logger.info("=" * 60)

        # 保存 Pipeline 报告
        self._save(
            proj_dir / "pipeline_report.json",
            self._build_report(theme, results, elapsed, final_video),
        )

        return final_video

    # ── 内部辅助方法 ─────────────────────────────────────────────────────

    @staticmethod
    def _save(path: Path, data: Any) -> None:
        """将数据 JSON 序列化写入文件。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        logger.debug("  Saved: %s", path)

    @staticmethod
    def _log_step(sr: StepResult) -> None:
        """打印步骤结果。"""
        icon = {"success": "✓", "skipped": "○", "failed": "✗", "pending": "·"}.get(
            sr.status, "?"
        )
        logger.info("  %s [%d] %s — %s", icon, sr.step, sr.name, sr.message)

    @staticmethod
    def _build_report(
        theme: str,
        results: list[StepResult],
        elapsed: float = 0.0,
        final_video: str = "",
    ) -> dict:
        """构建 Pipeline 执行报告。"""
        total = len(results)
        success = sum(1 for r in results if r.status == "success")
        skipped = sum(1 for r in results if r.status == "skipped")
        failed = sum(1 for r in results if r.status == "failed")

        return {
            "theme": theme,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": round(elapsed, 1),
            "total_steps": total,
            "success": success,
            "skipped": skipped,
            "failed": failed,
            "final_video": final_video,
            "steps": [
                {
                    "step": r.step,
                    "name": r.name,
                    "status": r.status,
                    "message": r.message,
                    "error": r.error,
                }
                for r in results
            ],
        }

    def _ensure_default_bgm(self) -> str | None:
        """如果 BGM 目录为空，尝试从网络下载一个免费的默认 BGM。"""
        gentle_dir = self.bgm_selector.bgm_dir / "gentle"
        gentle_dir.mkdir(parents=True, exist_ok=True)
        # 检查是否已有文件
        existing = self.bgm_selector._scan("gentle")
        if existing:
            return existing[0]
        logger.info("BGM 目录为空, 尝试下载默认 BGM...")
        try:
            import urllib.request

            url = (
                "https://www.soundhelix.com/examples/mp3/"
                "SoundHelix-Song-1.mp3"
            )
            output = gentle_dir / "default_bgm.mp3"
            urllib.request.urlretrieve(url, output)
            logger.info("  默认 BGM 下载完成: %s", output)
            return str(output)
        except Exception as e:
            logger.warning("  下载默认 BGM 失败: %s", e)
            return None

    @staticmethod
    def _concat_audio(audio_paths: list[str], output_path: str) -> None:
        """用 ffmpeg concat 协议合并多条音频。"""
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_file = f.name
            for p in audio_paths:
                abs_p = os.path.abspath(p)
                f.write(f"file '{abs_p}'\n")

        try:
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                    "-f", "concat", "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    output_path,
                ],
                check=True,
            )
        finally:
            os.unlink(concat_file)


# =============================================================================
# 视频合成工具函数
# =============================================================================


def clip_paths_from_images(
    shots: list,
    keyframe_dir: Path,
    shot_image_map: dict[int, str],
    compositor,
    fps: int,
) -> bool:
    """检查是否有可用的图片来合成视频。"""
    for shot in shots:
        img_path = shot_image_map.get(shot.shot_id)
        if not img_path:
            fallback = keyframe_dir / f"shot_{shot.shot_id:04d}.png"
            if fallback.exists():
                continue
        else:
            return True
    return False


def subtitle_entries_from_shots(
    shots: list,
    keyframe_dir: Path,
    shot_image_map: dict[int, str],
) -> list[dict]:
    """从镜头列表生成字幕条目。"""
    entries = []
    current_time = 0.0
    for shot in shots:
        img_path = shot_image_map.get(shot.shot_id)
        if not img_path:
            fallback = keyframe_dir / f"shot_{shot.shot_id:04d}.png"
            if not fallback.exists():
                continue
        if shot.dialogue:
            entries.append({
                "start": current_time,
                "end": current_time + shot.duration,
                "text": f"{shot.speaker + ': ' if shot.speaker else ''}{shot.dialogue}",
            })
        current_time += float(shot.duration)
    return entries


def _build_act_clip(
    act_shots: list,
    act_index: int,
    keyframe_dir: Path,
    video_dir: Path,
    shot_image_map: dict[int, str],
    comp,
) -> str | None:
    """为单幕生成视频片段，返回视频路径。"""
    clip_paths = []
    for shot in act_shots:
        img_path = shot_image_map.get(shot.shot_id)
        if not img_path:
            img_path = str(keyframe_dir / f"shot_{shot.shot_id:04d}.png")
        if not Path(img_path).exists():
            continue
        try:
            cp = comp.build_shot_clip(img_path, float(shot.duration), "zoom-in")
            clip_paths.append(cp)
        except Exception:
            continue

    if not clip_paths:
        return None

    act_video = str(video_dir / f"act_{act_index:04d}.mp4")
    comp.concatenate_clips(clip_paths, act_video)
    return act_video


# 模块级 compositor 实例（供视频合成函数使用）
_VCOMP = VideoCompositor()


# =============================================================================
# 视频合成入口
# =============================================================================


def compose_video_by_acts(
    story,
    shots: list,
    keyframe_dir: Path,
    video_dir: Path,
    audio_dir: Path,
    bgm_path: str | None,
    subtitle_entries: list[dict],
) -> str:
    """按幕(Act)多线程生成视频，最后拼接。"""
    import logging
    logger = logging.getLogger("pipeline.compose")
    comp = VideoCompositor()

    # 将 shots 按 act 分组
    act_scenes = {i: set(a.scenes) for i, a in enumerate(story.acts)}
    act_shots: dict[int, list] = {i: [] for i in range(len(story.acts))}

    for shot in shots:
        # 查找 shot 属于哪一幕
        for act_idx, scene_ids in act_scenes.items():
            if shot.scene in scene_ids or str(shot.scene) in scene_ids:
                act_shots[act_idx].append(shot)
                break
        else:
            # 未匹配的镜头归到最后一幕
            if act_shots:
                act_shots[max(act_shots.keys())].append(shot)

    logger.info("按幕分组: %s", {k: len(v) for k, v in act_shots.items()})

    # 多线程生成每幕视频
    act_videos: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=len(act_shots)) as pool:
        futures = {}
        for act_idx, act_shot_list in act_shots.items():
            if not act_shot_list:
                continue
            future = pool.submit(
                _build_act_clip,
                act_shot_list, act_idx, keyframe_dir, video_dir, {}, comp,
            )
            futures[future] = act_idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                act_videos[idx] = future.result()
            except Exception as e:
                logger.warning("幕 %d 视频生成失败: %s", idx + 1, e)
                act_videos[idx] = None

    # 按幕顺序收集有效视频
    valid_videos = []
    for i in sorted(act_videos.keys()):
        if act_videos[i]:
            valid_videos.append(act_videos[i])

    if not valid_videos:
        return ""

    # 拼接所有幕
    raw_video = str(video_dir / "raw_acts.mp4")
    comp.concatenate_clips(valid_videos, raw_video)

    # 添加音频
    video_with_audio = _add_audio_to_video(raw_video, video_dir, audio_dir, bgm_path, comp)
    if video_with_audio is None:
        video_with_audio = raw_video

    # 添加字幕
    if subtitle_entries:
        final = str(video_dir / "final.mp4")
        comp.add_subtitles(video_with_audio, subtitle_entries, final)
    else:
        final = video_with_audio

    return final


def compose_video_flat(
    shots: list,
    keyframe_dir: Path,
    video_dir: Path,
    audio_dir: Path,
    bgm_path: str | None,
    shot_image_map: dict[int, str],
) -> str:
    """平面合成视频（所有镜头按顺序拼接，无幕分组）。"""
    import logging
    logger = logging.getLogger("pipeline.compose")
    comp = VideoCompositor()

    clip_paths = []
    for shot in shots:
        img_path = shot_image_map.get(shot.shot_id)
        if not img_path:
            img_path = str(keyframe_dir / f"shot_{shot.shot_id:04d}.png")
        if not Path(img_path).exists():
            continue
        try:
            cp = comp.build_shot_clip(img_path, float(shot.duration), "zoom-in")
            clip_paths.append(cp)
        except Exception:
            continue

    if not clip_paths:
        return ""

    raw = str(video_dir / "raw_flat.mp4")
    comp.concatenate_clips(clip_paths, raw)

    video_with_audio = _add_audio_to_video(raw, video_dir, audio_dir, bgm_path, comp)
    if video_with_audio is None:
        video_with_audio = raw

    return video_with_audio


def _add_audio_to_video(
    video_path: str,
    video_dir: Path,
    audio_dir: Path,
    bgm_path: str | None,
    comp,
) -> str | None:
    """为视频添加配音 + BGM。"""
    import logging
    logger = logging.getLogger("pipeline.compose")
    import glob
    import os

    audio_files = sorted(glob.glob(str(audio_dir / "shot_*.mp3")))
    if not audio_files and not bgm_path:
        return video_path

    current = video_path

    # 添加配音
    if audio_files:
        try:
            if len(audio_files) > 1:
                mixed = str(video_dir / "audio_mixed.mp3")
                ManjuPipeline._concat_audio(audio_files, mixed)
                src = mixed
            else:
                src = audio_files[0]
            va = str(video_dir / "with_audio.mp4")
            comp.add_audio(current, src, va)
            current = va
        except Exception as e:
            logger.warning("配音添加失败: %s", e)

    # 添加 BGM
    if bgm_path:
        try:
            vb = str(video_dir / "with_bgm.mp4")
            comp.add_audio(current, bgm_path, vb)
            current = vb
        except Exception as e:
            logger.warning("BGM 添加失败: %s", e)

    return current


# =============================================================================
# CLI 入口
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Manju Studio — 漫剧一键生成 Pipeline",
    )
    parser.add_argument(
        "theme",
        nargs="?",
        default="一个关于勇气与友谊的仙侠故事",
        help="漫剧主题（默认: 一个关于勇气与友谊的仙侠故事）",
    )
    parser.add_argument(
        "--work-dir",
        default="data/projects",
        help="工作目录（默认: data/projects）",
    )
    args = parser.parse_args()

    pipeline = ManjuPipeline(work_dir=args.work_dir)
    result = pipeline.run(args.theme)
    if result:
        print(f"\n✅ 生成完成! 视频文件: {result}")
    else:
        print("\n❌ 生成失败, 请检查日志。")
        sys.exit(1)
