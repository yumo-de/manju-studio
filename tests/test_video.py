"""Tests for manju.video.compositor — VideoCompositor._fmt_time."""

import pytest
from manju.video.compositor import VideoCompositor


class TestTimeFormat:
    """Verify VideoCompositor._fmt_time produces correct HH:MM:SS.mmm strings."""

    def test_zero_seconds(self):
        result = VideoCompositor._fmt_time(0.0)
        assert result == "00:00:00.000"

    def test_single_second(self):
        result = VideoCompositor._fmt_time(1.0)
        assert result == "00:00:01.000"

    def test_minutes_and_seconds(self):
        result = VideoCompositor._fmt_time(65.5)
        assert result == "00:01:05.500"

    def test_hours(self):
        result = VideoCompositor._fmt_time(3600.0)  # 1 hour
        assert result == "01:00:00.000"

    def test_hours_minutes_seconds(self):
        result = VideoCompositor._fmt_time(3661.123)
        assert result == "01:01:01.123"

    def test_milliseconds_precision(self):
        result = VideoCompositor._fmt_time(1.001)
        assert result == "00:00:01.001"

    def test_rounding(self):
        """Fractional milliseconds should be truncated/rounded by format."""
        result = VideoCompositor._fmt_time(1.9999)
        # The format uses f"{secs:06.3f}" so 1.9999 → 1.999 or 2.000
        assert result in ("00:00:01.999", "00:00:02.000")

    def test_large_value(self):
        """Large values should still format correctly."""
        result = VideoCompositor._fmt_time(100000.0)
        assert result == "27:46:40.000"

    def test_returns_string(self):
        result = VideoCompositor._fmt_time(42.0)
        assert isinstance(result, str)
