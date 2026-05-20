"""Tests for manju.visual.prompt_gen — PromptGenerator.build_prompt."""

import pytest
from manju.schemas.story import Shot, Camera
from manju.visual.prompt_gen import PromptGenerator


class TestPromptGenerator:
    """Verify PromptGenerator.build_prompt output format and content."""

    def test_build_prompt_default_genre(self):
        """Default genre (仙侠) should produce xianxia style prompt."""
        cam = Camera(type="wide", angle="eye", move="static")
        shot = Shot(
            shot_id=1,
            scene="test",
            duration=5,
            camera=cam,
            description="主角站在山顶",
            prompt="A hero stands on a mountain peak",
            dialogue="",
            character=["英雄"],
            bgm_mood="epic",
        )
        gen = PromptGenerator()
        result = gen.build_prompt(shot)

        assert "xianxia style" in result
        assert "wide shot" in result
        assert "eye-level angle" in result
        assert "A hero stands on a mountain peak" in result
        assert "英雄" in result
        assert "masterpiece" in result

    def test_build_prompt_scifi_genre(self):
        """Sci-fi genre should produce cyberpunk style prompt."""
        cam = Camera(type="closeup", angle="low", move="zoom-in")
        shot = Shot(
            shot_id=2,
            scene="test",
            duration=5,
            camera=cam,
            description="机器人启动",
            prompt="A robot activates its optical sensors",
            dialogue="",
            character=["机器人"],
            bgm_mood="tense",
        )
        gen = PromptGenerator()
        result = gen.build_prompt(shot, genre="科幻")

        assert "sci-fi style" in result
        assert "close-up shot" in result
        assert "low angle shot" in result
        assert "Zoom In" in result or "zoom in" in result
        assert "A robot activates" in result

    def test_build_prompt_camera_move(self):
        """Camera motion should be included as text when not static."""
        cam = Camera(type="wide", angle="overhead", move="pan-right")
        shot = Shot(
            shot_id=3,
            scene="test",
            duration=5,
            camera=cam,
            description="大军前进",
            prompt="An army marches forward",
            dialogue="",
            character=[],
            bgm_mood="epic",
        )
        gen = PromptGenerator()
        result = gen.build_prompt(shot, genre="历史")

        assert "historical epic style" in result
        assert "overhead bird's-eye view" in result
        assert "Pan Right" in result or "pan right" in result

    def test_build_prompt_no_characters(self):
        """Empty character list should not produce 'char_text' prefix."""
        cam = Camera(type="medium", angle="eye", move="static")
        shot = Shot(
            shot_id=4,
            scene="test",
            duration=5,
            camera=cam,
            description="风景如画",
            prompt="A beautiful landscape",
            dialogue="",
            character=[],
            bgm_mood="gentle",
        )
        gen = PromptGenerator()
        result = gen.build_prompt(shot, genre="都市")

        # Should not have any trailing comma artifact before core prompt
        assert "A beautiful landscape" in result
        # Should not start with a comma
        assert not result.startswith(",")
        assert "modern urban style" in result

    def test_build_prompt_unknown_genre_fallback(self):
        """Unknown genre should fall back to 仙侠 style."""
        cam = Camera(type="closeup", angle="eye", move="static")
        shot = Shot(
            shot_id=5,
            scene="test",
            duration=5,
            camera=cam,
            description="测试",
            prompt="Test",
            dialogue="",
            character=["A"],
            bgm_mood="comic",
        )
        gen = PromptGenerator()
        result = gen.build_prompt(shot, genre="未知题材")

        # Falls back to 仙侠
        assert "xianxia style" in result
