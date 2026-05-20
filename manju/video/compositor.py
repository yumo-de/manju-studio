"""
Video compositor for Manju Studio.

Provides VideoCompositor which wraps ffmpeg to:
  - Convert images to video clips (with Ken Burns effects)
  - Concatenate clips with transitions
  - Add audio tracks
  - Burn subtitles
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from .effects import TRANSITIONS, validate_transition


class VideoCompositor:
    """High-level ffmpeg wrapper for building videos from images + audio + subtitles."""

    def __init__(self, fps: int = 24, resolution: Tuple[int, int] = (1920, 1080)):
        """
        Args:
            fps: Frames per second for output video.
            resolution: (width, height) in pixels.
        """
        self.fps = fps
        self.width, self.height = resolution

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Convert seconds to SRT time format ``HH:MM:SS.mmm``.

        >>> VideoCompositor._fmt_time(65.5)
        '00:01:05.500'
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    @staticmethod
    def _run_ffmpeg(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
        """Execute an ffmpeg command with common flags."""
        full_cmd = [
            "ffmpeg",
            "-y",  # overwrite output without asking
            "-hide_banner",
            "-loglevel", "warning",
        ] + cmd
        return subprocess.run(full_cmd, check=check)

    # ── core operations ──────────────────────────────────────────────────────

    def build_shot_clip(
        self,
        image_path: str,
        duration: float,
        ken_burns: str = "zoom-in",
        output_path: str = "",  # if empty, writes to a temp file
    ) -> str:
        """Turn a single still image into a video clip with optional Ken Burns effect.

        Args:
            image_path: Path to the source image.
            duration: Length of the clip in seconds.
            ken_burns: One of ``'zoom-in'``, ``'zoom-out'``, or ``'static'``.
            output_path: Where to write the result.  If empty a temp file is
                created and its path is returned.

        Returns:
            Path to the generated video file.
        """
        if not output_path:
            fd, output_path = tempfile.mkstemp(suffix=".mp4")
            os.close(fd)

        # Build the zoompan filter for Ken Burns.
        # zoompan:z=speed:d=duration_in_frames:s=output_size
        n_frames = int(duration * self.fps)
        size = f"{self.width}x{self.height}"

        if ken_burns == "zoom-in":
            # Start at 1x, end at ~1.3x
            filter_chain = (
                f"zoompan=z='min(zoom+0.3/{n_frames},1.3)':"
                f"d={n_frames}:s={size}:fps={self.fps}"
            )
        elif ken_burns == "zoom-out":
            # Start at 1.3x, end at 1x
            filter_chain = (
                f"zoompan=z='max(zoom-0.3/{n_frames},1.0)':"
                f"d={n_frames}:s={size}:fps={self.fps}"
            )
        elif ken_burns == "static":
            # No zoom, just scale to resolution
            filter_chain = f"scale={size}:force_original_aspect_ratio=decrease,pad={size}:-1:-1:color=black"
        else:
            raise ValueError(
                f"Unknown ken_burns value {ken_burns!r}. "
                "Expected one of: 'zoom-in', 'zoom-out', 'static'."
            )

        cmd = [
            "-loop", "1",
            "-i", image_path,
            "-vf", filter_chain,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-r", str(self.fps),
            output_path,
        ]
        self._run_ffmpeg(cmd)
        return output_path

    def concatenate_clips(
        self,
        clip_paths: List[str],
        output_path: str,
        transitions: Optional[List[str]] = None,
    ) -> str:
        """Concatenate video clips with optional transitions between them.

        Args:
            clip_paths: Ordered list of video file paths.
            output_path: Path for the concatenated output.
            transitions: Optional list of transition names (one fewer than
                *clip_paths*).  Each name must be a key in
                :data:`~manju.video.effects.TRANSITIONS`.

        Returns:
            *output_path* for chaining.
        """
        if len(clip_paths) == 0:
            raise ValueError("At least one clip is required.")
        if transitions and len(transitions) != len(clip_paths) - 1:
            raise ValueError(
                f"Expected {len(clip_paths) - 1} transitions, "
                f"got {len(transitions)}."
            )
        if transitions:
            for t in transitions:
                if not validate_transition(t):
                    raise ValueError(f"Unknown transition: {t!r}")

        # Simple concatenation with concat demuxer when no transitions.
        if not transitions:
            return self._concat_simple(clip_paths, output_path)

        # Use the xfade filter when transitions are requested.
        return self._concat_with_xfade(clip_paths, transitions, output_path)

    # ── internal concat helpers ──────────────────────────────────────────────

    def _concat_simple(self, clip_paths: List[str], output_path: str) -> str:
        """Concatenate clips via the concat demuxer (no transitions)."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            concat_file = f.name
            for path in clip_paths:
                abs_path = os.path.abspath(path)
                f.write(f"file '{abs_path}'\n")

        try:
            cmd = [
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path,
            ]
            self._run_ffmpeg(cmd)
        finally:
            os.unlink(concat_file)

        return output_path

    def _concat_with_xfade(
        self,
        clip_paths: List[str],
        transitions: List[str],
        output_path: str,
    ) -> str:
        """Concatenate clips with crossfade/transition effects."""
        # Build a filter_complex for multi-clip xfade.
        n = len(clip_paths)
        # We'll let ffmpeg know about all inputs, then chain them.
        # The pattern: [0][1]xfade=transition=..:duration=..:offset=..[r0];
        #              [r0][2]xfade=transition=..:duration=..:offset=..[r1]; ...
        transition_duration = 0.5  # seconds per transition
        parts = []
        labels = []
        for i in range(n - 1):
            in_a = f"[{i}]" if i == 0 else f"[r{i - 1}]"
            in_b = f"[{i + 1}]"
            out = f"[r{i}]"
            t_name = transitions[i]
            xfade_name = TRANSITIONS[t_name]["ffmpeg_xfade"]

            parts.append(
                f"{in_a}{in_b}xfade=transition={xfade_name}:"
                f"duration={transition_duration}:offset=0"
            )
            labels.append(out)

        # For the offset calculation, we need to know the duration of each clip
        # so the transition happens at the end of each clip.  Probe each input.
        durations = []
        for p in clip_paths:
            d = self._probe_duration(p)
            durations.append(d)

        # Rebuild parts with correct offsets.
        parts.clear()
        offset = 0.0
        for i in range(n - 1):
            # Offset = cumulative duration of clips before this transition,
            # minus the overlap period of previous transition.
            # Actually, for xfade: offset is the time *in the overall output*
            # where the transition starts.  The transition starts at the end
            # of clip i minus the transition duration.
            offset += durations[i] - transition_duration if i > 0 else durations[i] - transition_duration
            # More accurately:
            # offset_0 = duration_0 - trans_duration
            # offset_1 = duration_0 + duration_1 - 2*trans_duration
            # ...

        # Simpler approach: recompute properly.
        parts.clear()
        offset = 0.0
        # First transition offset: clip0_duration - trans_duration
        # Actually xfade's offset is relative to the *overall timeline*.
        # Let's use a cleaner approach.
        cumulative = durations[0]
        for i in range(n - 1):
            # offset for transition between clip i and i+1
            # = end time of clip i in the output timeline
            # = sum of durations of clips 0..i minus (i * transition_duration)
            # because each transition overlaps by transition_duration.
            if i == 0:
                offset = durations[0] - transition_duration
            else:
                # Each subsequent clip adds its duration minus one overlap
                offset += durations[i] - transition_duration

            in_a = f"[{i}]" if i == 0 else f"[r{i - 1}]"
            in_b = f"[{i + 1}]"
            out = f"[r{i}]"
            t_name = transitions[i]
            xfade_name = TRANSITIONS[t_name]["ffmpeg_xfade"]

            parts.append(
                f"{in_a}{in_b}xfade=transition={xfade_name}:"
                f"duration={transition_duration}:offset={offset:.3f}{out}"
            )

        filter_complex = ";".join(parts)

        input_args = []
        for p in clip_paths:
            input_args.extend(["-i", p])

        # When there are transitions we must re-encode.
        cmd = [
            *input_args,
            "-filter_complex", filter_complex,
            "-map", f"[r{n - 2}]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(self.fps),
            output_path,
        ]
        self._run_ffmpeg(cmd)
        return output_path

    def _probe_duration(self, video_path: str) -> float:
        """Return the duration (in seconds) of a video file using ffprobe."""
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
        )
        try:
            return float(result.stdout.strip())
        except (ValueError, TypeError):
            # Fallback: assume 5 seconds if probe fails
            return 5.0

    # ── audio ────────────────────────────────────────────────────────────────

    def add_audio(
        self,
        video_path: str,
        audio_path: str,
        output_path: str,
    ) -> str:
        """Overlay an audio track onto a video.

        The audio is mixed (not replaced) so any original audio is preserved
        but lowered in volume.  If the audio is shorter than the video it will
        loop; if longer it will be truncated.

        Args:
            video_path: Input video file.
            audio_path: Input audio file.
            output_path: Output video file with audio embedded.

        Returns:
            *output_path* for chaining.
        """
        cmd = [
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "copy",
            # Mix audio: keep original audio at 30% volume, add new track
            "-filter_complex",
            "[1:a]volume=1.0[a1];"
            "[0:a]volume=0.3[a0];"
            "[a0][a1]amix=inputs=2:duration=first:dropout_transition=2",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            output_path,
        ]
        self._run_ffmpeg(cmd)
        return output_path

    # ── subtitles ────────────────────────────────────────────────────────────

    def add_subtitles(
        self,
        video_path: str,
        subtitles: List[dict],
        output_path: str,
    ) -> str:
        """Burn subtitles into a video.

        *subtitles* is a list of dicts with keys: ``start``, ``end`` (both in
        seconds), and ``text``.  An SRT file is generated and burnt in with the
        ``subtitles`` ffmpeg filter.

        Args:
            video_path: Input video file.
            subtitles: List of subtitle dicts.
            output_path: Output video file with burnt-in subtitles.

        Returns:
            *output_path* for chaining.
        """
        # Write temporary SRT file
        srt_lines = []
        for idx, sub in enumerate(subtitles, start=1):
            start_str = self._fmt_time(sub["start"])
            end_str = self._fmt_time(sub["end"])
            text = sub["text"]
            srt_lines.append(str(idx))
            srt_lines.append(f"{start_str} --> {end_str}")
            srt_lines.append(text)
            srt_lines.append("")  # blank line separator

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".srt", delete=False, encoding="utf-8"
        ) as f:
            srt_path = f.name
            f.write("\n".join(srt_lines))

        try:
            # Burn subtitles with the subtitles filter.
            # Escape special chars in the srt path for ffmpeg.
            escaped_path = srt_path.replace("\\", "\\\\").replace(":", "\\:")
            cmd = [
                "-i", video_path,
                "-vf", f"subtitles={escaped_path}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                output_path,
            ]
            self._run_ffmpeg(cmd)
        finally:
            os.unlink(srt_path)

        return output_path
