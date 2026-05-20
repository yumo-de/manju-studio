"""
Task 11: Pipeline 编排器
串联所有模块实现从主题到最终视频的一键生成。
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pipeline")


# =============================================================================
# ManjuPipeline
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
          1/6 生成故事大纲
          2/6 生成剧本
          3/6 生成分镜头
          4/6 生成图片（角色立绘 + 关键帧）
          5/6 生成配音
          6/6 合成视频
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

        start_time = time.time()
        logger.info("=" * 60)
        logger.info("Pipeline 开始 | 主题: %s | 项目: %s", theme, project_id)
        logger.info("=" * 60)

        # ── [1/6] 生成故事大纲 ────────────────────────────────────────────
        logger.info("[1/6] 生成故事大纲 …")
        story = self.expander.expand(theme)
        self._save(proj_dir / "story.json", story.model_dump())
        self._log_done(1, f"故事《{story.title}》({story.genre}), {len(story.characters)} 角色")

        # ── [2/6] 生成剧本 ────────────────────────────────────────────────
        logger.info("[2/6] 生成剧本 …")
        scenes = self.scriptwriter.write(story)
        self._save(proj_dir / "scenes.json", scenes)
        self._log_done(2, f"{len(scenes)} 个场景")

        # ── [3/6] 生成分镜头 ──────────────────────────────────────────────
        logger.info("[3/6] 生成分镜头 …")
        storyboard = self.shot_generator.generate(story, scenes)
        self._save(proj_dir / "storyboard.json", storyboard.model_dump())
        self._log_done(3, f"{storyboard.total_shots} 个镜头, 预计 {storyboard.estimated_duration}s")

        # ── [4/6] 生成图片 ────────────────────────────────────────────────
        logger.info("[4/6] 生成图片 …")

        char_image_map: dict[str, str] = {}
        shot_image_map: dict[int, str] = {}

        if self._image_available:
            # 4a. 角色立绘（只生成前 3 个角色）
            characters = story.characters[:3]
            for ch in characters:
                logger.info("  生成角色立绘: %s", ch.name)
                style_en = self.prompt_gen.STYLE_PREFIX.get(
                    story.genre, self.prompt_gen.STYLE_PREFIX["仙侠"]
                )["en"]
                prompt = (
                    f"Portrait of {ch.name}, {ch.appearance}, "
                    f"{style_en}, "
                    f"character portrait, full body, clean background, detailed illustration"
                )
                try:
                    urls = self.image_client.generate(prompt, n=1)
                    if urls:
                        img_path = char_dir / f"{ch.name}.png"
                        self.image_client.download(urls[0], img_path)
                        char_image_map[ch.name] = str(img_path)
                        logger.info("  ✓  %s → %s", ch.name, img_path)
                    else:
                        logger.warning("  ✗  %s: 图片生成返回空", ch.name)
                except Exception as e:
                    logger.warning("  ✗  %s: %s", ch.name, e)

            # 4b. 关键帧（前 5 帧）
            for shot in storyboard.shots[:5]:
                logger.info("  生成关键帧: shot_%d", shot.shot_id)
                full_prompt = self.prompt_gen.build_prompt(shot, story.genre)
                try:
                    urls = self.image_client.generate(full_prompt, n=1)
                    if urls:
                        img_path = keyframe_dir / f"shot_{shot.shot_id:04d}.png"
                        self.image_client.download(urls[0], img_path)
                        shot_image_map[shot.shot_id] = str(img_path)
                        logger.info("  ✓  shot_%d → %s", shot.shot_id, img_path)
                    else:
                        logger.warning("  ✗  shot_%d: 图片生成返回空", shot.shot_id)
                except Exception as e:
                    logger.warning("  ✗  shot_%d: %s", shot.shot_id, e)

            self._log_done(4, f"角色立绘 {len(char_image_map)} 张, 关键帧 {len(shot_image_map)} 张")
        else:
            logger.warning("  跳过图像生成（未配置 API Key）")
            self._log_done(4, "跳过（未配置 API Key）")

        # ── [5/6] 生成配音 ────────────────────────────────────────────────
        logger.info("[5/6] 生成配音 …")
        self._tts = TTSEngine(output_dir=str(audio_dir))

        # 构建角色信息字典供 TTS 匹配声线
        characters_dict: dict[str, dict[str, str]] = {
            ch.name: {"voice_style": ch.voice_style, "gender": ch.gender}
            for ch in story.characters
        }

        try:
            audio_paths = self._tts.generate_dialogue(
                shots=storyboard.shots,
                characters=characters_dict,
            )
            logger.info("  生成 %d 条配音音频", len(audio_paths))
            self._log_done(5, f"{len(audio_paths)} 条配音")
        except Exception as e:
            logger.warning("  ✗  配音生成异常: %s", e)
            audio_paths = []
            self._log_done(5, "失败 (跳过)")

        # ── [6/6] 合成视频 ────────────────────────────────────────────────
        logger.info("[6/6] 合成视频 …")

        clip_paths: list[str] = []
        subtitle_entries: list[dict] = []
        current_time = 0.0

        for shot in storyboard.shots:
            # 只有已生成图片的镜头才能构建 clip
            img_path = shot_image_map.get(shot.shot_id)
            if not img_path:
                # 尝试在 keyframe_dir 中按序号查找
                fallback = keyframe_dir / f"shot_{shot.shot_id:04d}.png"
                if fallback.exists():
                    img_path = str(fallback)
                else:
                    logger.debug("  shot_%d: 无图片, 跳过视频片段", shot.shot_id)
                    continue

            try:
                clip_path = self.compositor.build_shot_clip(
                    image_path=img_path,
                    duration=float(shot.duration),
                    ken_burns="zoom-in",
                )
                clip_paths.append(clip_path)

                # 收集字幕信息
                if shot.dialogue:
                    subtitle_entries.append({
                        "start": current_time,
                        "end": current_time + shot.duration,
                        "text": f"{shot.speaker + ': ' if shot.speaker else ''}{shot.dialogue}",
                    })

                current_time += float(shot.duration)
            except Exception as e:
                logger.warning("  ✗  shot_%d clip 构建失败: %s", shot.shot_id, e)

        if not clip_paths:
            logger.error("没有可用的视频片段, 无法合成视频!")
            return ""

        # 拼接片段
        raw_video = str(video_dir / "raw.mp4")
        try:
            self.compositor.concatenate_clips(clip_paths, raw_video)
            logger.info("  片段拼接完成: %s", raw_video)
        except Exception as e:
            logger.error("  拼接失败: %s", e)
            return ""

        # 添加配音
        if audio_paths:
            mixed_audio = str(video_dir / "audio_mixed.mp3")
            try:
                # 如果有多条音频, 用 ffmpeg concat 合成一条
                if len(audio_paths) > 1:
                    self._concat_audio(audio_paths, mixed_audio)
                    audio_source = mixed_audio
                else:
                    audio_source = str(audio_paths[0])

                video_with_audio = str(video_dir / "with_audio.mp4")
                self.compositor.add_audio(raw_video, audio_source, video_with_audio)
                logger.info("  配音添加完成")
            except Exception as e:
                logger.warning("  添加配音失败: %s, 使用无声版本", e)
                video_with_audio = raw_video
        else:
            video_with_audio = raw_video

        # 添加字幕
        if subtitle_entries:
            final_video = str(video_dir / "final.mp4")
            try:
                self.compositor.add_subtitles(video_with_audio, subtitle_entries, final_video)
                logger.info("  字幕添加完成")
            except Exception as e:
                logger.warning("  添加字幕失败: %s", e)
                final_video = video_with_audio
        else:
            final_video = video_with_audio

        elapsed = time.time() - start_time
        logger.info("=" * 60)
        logger.info("Pipeline 完成! 耗时: %.1fs", elapsed)
        logger.info("最终视频: %s", final_video)
        logger.info("=" * 60)

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
    def _log_done(step: int, msg: str) -> None:
        """打印步骤完成信息。"""
        logger.info("  ✓ [%d/6] %s", step, msg)

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
