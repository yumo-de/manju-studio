"""TTS 配音引擎 — 基于 Edge-TTS 生成角色配音。"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── 中文音色 → Edge-TTS voice 映射 ─────────────────────────────────────
VOICE_MAP: dict[str, str] = {
    "温柔女声": "zh-CN-XiaoxiaoNeural",
    "活泼女声": "zh-CN-XiaohanNeural",
    "御姐女声": "zh-CN-XiaoyiNeural",
    "青年男声": "zh-CN-YunxiNeural",
    "大叔男声": "zh-CN-YunjianNeural",
    "旁白男声": "zh-CN-YunyangNeural",
    "儿童女声": "zh-CN-XiaomengNeural",
    "知性女声": "zh-CN-XiaomoNeural",
}

DEFAULT_VOICE = "zh-CN-YunxiNeural"  # 青年男声


class TTSEngine:
    """基于 Edge-TTS 的配音引擎。"""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("TTS output dir: %s", self.output_dir)

    # ── 声线匹配 ─────────────────────────────────────────────────────
    @staticmethod
    def get_voice(voice_style: str) -> str:
        """根据声线描述匹配 Edge-TTS voice。

        支持完整关键词匹配（如 "温柔女声旁白" 中的 "温柔女声"）。
        未匹配时返回默认音色（青年男声）。
        """
        if not voice_style:
            return DEFAULT_VOICE

        for key in VOICE_MAP:
            if key in voice_style:
                return VOICE_MAP[key]

        logger.warning("Unknown voice style '%s', fallback to '%s'", voice_style, DEFAULT_VOICE)
        return DEFAULT_VOICE

    # ── 单条音频生成 ─────────────────────────────────────────────────
    async def _generate_one(self, text: str, voice: str, output_path: Path) -> None:
        """用 edge_tts.Communicate 生成单个音频文件。"""
        try:
            import edge_tts

            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
            logger.info("Generated: %s (voice=%s)", output_path.name, voice)
        except ImportError:
            logger.error("edge-tts is not installed. Run: pip install edge-tts")
            raise
        except Exception as e:
            logger.error("Failed to generate %s: %s", output_path, e)
            raise

    # ── 批量生成 ─────────────────────────────────────────────────────
    def generate_dialogue(
        self,
        shots: list,
        characters: dict[str, dict],
        output_dir: Optional[str] = None,
    ) -> list[Path]:
        """批量生成配音音频。

        Args:
            shots: 分镜列表（每个元素需有 .speaker / .dialogue 属性或 dict 接口）。
            characters: 角色字典 {角色名: {voice_style: str, ...}}。
            output_dir: 自定义输出目录，默认使用实例的 output_dir。

        Returns:
            生成的音频文件路径列表（按 shots 顺序对应）。
        """
        out_dir = Path(output_dir) if output_dir else self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        tasks = []
        paths = []

        for i, shot in enumerate(shots):
            # 兼容对象属性访问和 dict 访问
            if hasattr(shot, "speaker"):
                speaker = shot.speaker
                dialogue = shot.dialogue or ""
            else:
                speaker = shot.get("speaker")
                dialogue = shot.get("dialogue", "")

            if not dialogue:
                logger.debug("Shot %d has no dialogue, skipping.", i)
                paths.append(None)
                continue

            # 确定音色
            if speaker and speaker in characters:
                char_info = characters[speaker]
                if isinstance(char_info, dict):
                    voice_style = char_info.get("voice_style", "")
                elif hasattr(char_info, "voice_style"):
                    voice_style = char_info.voice_style
                else:
                    voice_style = str(char_info) if char_info else ""
            else:
                voice_style = ""

            voice = self.get_voice(voice_style)

            # 输出文件名
            output_path = out_dir / f"shot_{i:04d}.mp3"
            paths.append(output_path)
            tasks.append(self._generate_one(dialogue, voice, output_path))

        # 并发执行所有生成任务
        if tasks:
            asyncio.run(self._run_tasks(tasks))

        # 过滤掉跳过的 shot
        return [p for p in paths if p is not None]

    async def _run_tasks(self, tasks: list) -> None:
        """并发执行所有异步生成任务。"""
        await asyncio.gather(*tasks)

    # ── 单句便捷生成 ────────────────────────────────────────────────
    def generate_text(
        self,
        text: str,
        voice_style: str = "",
        filename: str = "output.mp3",
        output_dir: Optional[str] = None,
    ) -> Path:
        """生成单条语音，返回文件路径。"""
        out_dir = Path(output_dir) if output_dir else self.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        voice = self.get_voice(voice_style)
        output_path = out_dir / filename

        asyncio.run(self._generate_one(text, voice, output_path))
        return output_path
