"""
Frame interpolation — 视频帧率提升引擎。

支持两种模式：
  - ffmpeg minterpolate（默认，免费，在任何系统可用）
  - rife-ncnn-vulkan（需要独立二进制，GPU 加速，质量更高）
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("interpolator")


class FrameInterpolator:
    """视频帧率插值引擎。

    Args:
        target_fps: 目标帧率（默认 60）。
        method: 插值方法，可选 ``"minterpolate"``（默认）或 ``"rife"``。
        rife_binary: rife-ncnn-vulkan 可执行文件路径（method="rife" 时必填）。
    """

    def __init__(
        self,
        target_fps: int = 60,
        method: str = "minterpolate",
        rife_binary: str = "",
    ) -> None:
        self.target_fps = target_fps
        self.method = method.lower()
        self.rife_binary = rife_binary

        if self.method not in ("minterpolate", "rife"):
            raise ValueError(
                f"Unknown interpolation method: {method!r}. "
                f"Expected 'minterpolate' or 'rife'."
            )

        if self.method == "rife":
            self._check_rife()

    # ── public API ────────────────────────────────────────────────────────

    def interpolate(self, video_path: str, output_path: str = "") -> str:
        """对视频做帧率插值，返回输出视频路径。

        Args:
            video_path: 输入视频文件路径。
            output_path: 输出视频路径。为空时使用临时文件。

        Returns:
            输出视频路径。
        """
        if not output_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            import os
            os.close(fd)

        if self.method == "minterpolate":
            self._run_minterpolate(video_path, output_path)
        else:
            self._run_rife(video_path, output_path)

        logger.info(
            "插帧完成: %s → %s (%.0ffps)",
            Path(video_path).name,
            Path(output_path).name,
            self.target_fps,
        )
        return output_path

    def stats(self, video_path: str) -> dict[str, Any]:
        """读取视频的帧率信息。"""
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=r_frame_rate,avg_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
        )
        lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
        # ffprobe returns fractions like "24000/1001" or "24/1"
        def _parse_fraction(s: str) -> float:
            try:
                parts = s.split("/")
                return float(parts[0]) / float(parts[1]) if len(parts) == 2 else float(s)
            except (ValueError, ZeroDivisionError, IndexError):
                return 0.0

        return {
            "input_fps": _parse_fraction(lines[0]) if len(lines) > 0 else 0.0,
            "avg_fps": _parse_fraction(lines[1]) if len(lines) > 1 else 0.0,
            "target_fps": self.target_fps,
            "method": self.method,
        }

    # ── internal ──────────────────────────────────────────────────────────

    def _run_minterpolate(self, input_path: str, output_path: str) -> None:
        """使用 ffmpeg minterpolate 滤波器做运动补偿插帧。

        minterpolate 参数说明：
          - mi_mode=mci: 运动补偿插值（比 blend 更平滑）
          - mc_mode=aobmc: 自适应重叠块运动补偿
          - me_mode=bidir: 双向运动估计
          - vsbmc=1: 可变尺寸块运动补偿（提升细节保留）
        """
        cmd = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-i", input_path,
            "-vf", (
                f"minterpolate="
                f"fps={self.target_fps}:"
                f"mi_mode=mci:"
                f"mc_mode=aobmc:"
                f"me_mode=bidir:"
                f"vsbmc=1"
            ),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "copy",
            output_path,
        ]
        subprocess.run(cmd, check=True)

    def _check_rife(self) -> None:
        """检查 rife-ncnn-vulkan 是否可用。"""
        if not self.rife_binary:
            raise ValueError(
                "rife_binary must be provided when method='rife'"
            )
        rife_path = Path(self.rife_binary)
        if not rife_path.exists():
            raise FileNotFoundError(
                f"rife-ncnn-vulkan binary not found: {rife_path}"
            )

    def _run_rife(self, input_path: str, output_path: str) -> None:
        """使用 rife-ncnn-vulkan 做 AI 帧插值（更高画质）。"""
        # rife-ncnn-vulkan 用法:
        #   rife-ncnn-vulkan -i input.mp4 -o output.mp4 -r 2x/4x/...
        # 计算需要的倍数
        from manju.config import load_config
        import os

        # 探测输入帧率
        info = self.stats(input_path)
        input_fps = info.get("input_fps", 24)
        multiplier = max(2, round(self.target_fps / input_fps))

        cmd = [
            self.rife_binary,
            "-i", input_path,
            "-o", output_path,
            "-r", f"{multiplier}x",
            "-j", "1:1:1",  # GPU:线程数:任务数
        ]
        subprocess.run(cmd, check=True)

        # 如果 rife 输出的帧率还不是目标帧率，再用 ffmpeg 调整
        after_info = self.stats(output_path)
        after_fps = after_info.get("avg_fps", 0)
        if after_fps > 0 and abs(after_fps - self.target_fps) > 0.5:
            resample_path = output_path + ".tmp.mp4"
            cmd2 = [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
                "-i", output_path,
                "-r", str(self.target_fps),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "medium",
                "-crf", "18",
                "-c:a", "copy",
                resample_path,
            ]
            subprocess.run(cmd2, check=True)
            import shutil
            shutil.move(resample_path, output_path)
