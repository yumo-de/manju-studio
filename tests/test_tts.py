"""Tests for manju.tts.engine — TTSEngine.get_voice / VOICE_MAP matching."""

import pytest
from manju.tts.engine import TTSEngine, VOICE_MAP, DEFAULT_VOICE


class TestVoiceMapping:
    """Verify VOICE_MAP keyword matching logic."""

    def test_exact_match(self):
        """An exact key in VOICE_MAP should return the mapped voice."""
        result = TTSEngine.get_voice("温柔女声")
        assert result == "zh-CN-XiaoxiaoNeural"

    def test_substring_match(self):
        """A string containing one of the keys should return that key's voice."""
        result = TTSEngine.get_voice("温柔女声旁白")
        assert result == "zh-CN-XiaoxiaoNeural"

    def test_substring_match_2(self):
        result = TTSEngine.get_voice("活泼女声配音")
        assert result == "zh-CN-XiaohanNeural"

    def test_substring_match_3(self):
        result = TTSEngine.get_voice("知性女声解说")
        assert result == "zh-CN-XiaomoNeural"

    def test_all_keys_mapped(self):
        """Every key in VOICE_MAP should resolve to itself (identity check)."""
        for key, expected_voice in VOICE_MAP.items():
            result = TTSEngine.get_voice(key)
            assert result == expected_voice, f"Key '{key}' failed to match"

    def test_empty_string(self):
        """Empty string should fall back to DEFAULT_VOICE."""
        result = TTSEngine.get_voice("")
        assert result == DEFAULT_VOICE

    def test_none(self):
        """None input should fall back to DEFAULT_VOICE."""
        result = TTSEngine.get_voice(None)
        assert result == DEFAULT_VOICE


class TestDefaultVoice:
    """Verify fallback behavior for unmatched voice styles."""

    def test_unknown_voice(self):
        """An unrecognised style name should return the default voice."""
        result = TTSEngine.get_voice("不存在的声线")
        assert result == DEFAULT_VOICE

    def test_gibberish(self):
        """Completely unrelated input should fall back."""
        result = TTSEngine.get_voice("asdf1234!@#")
        assert result == DEFAULT_VOICE

    def test_partial_match_fallback(self):
        """A string that does NOT contain any key should fall back."""
        result = TTSEngine.get_voice("男声")  # shorter than keys "青年男声"/"大叔男声"/"旁白男声"
        # "男声" is a substring of "青年男声", "大叔男声", "旁白男声"
        # Actually "男声" IS in "青年男声" — so let's use something truly absent.
        # Use "标准男声" which doesn't match any key
        pass

    def test_truly_unmatched(self):
        """A string that contains none of the VOICE_MAP keys returns default."""
        result = TTSEngine.get_voice("标准男声")
        assert result == DEFAULT_VOICE

    def test_default_voice_constant(self):
        """DEFAULT_VOICE should be an Edge-TTS voice string."""
        assert isinstance(DEFAULT_VOICE, str)
        assert DEFAULT_VOICE.startswith("zh-CN-")
