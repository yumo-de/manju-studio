"""Tests for manju.schemas.story — Character, Story, Camera, Shot, Storyboard."""

import pytest
from manju.schemas.story import Character, Story, Act, Camera, Shot, Storyboard


class TestStoryCreation:
    """Verify Character and Story creation with correct field types."""

    def test_character_fields(self):
        c = Character(
            name="Alice",
            role="主角",
            gender="女",
            personality="勇敢",
            appearance="红衣",
            voice_style="温柔女声",
            backstory="一名侠客",
        )
        assert c.name == "Alice"
        assert c.role == "主角"
        assert c.gender == "女"
        assert c.personality == "勇敢"
        assert c.appearance == "红衣"
        assert c.voice_style == "温柔女声"
        assert c.backstory == "一名侠客"

    def test_character_default_backstory(self):
        """backstory should default to empty string."""
        c = Character(
            name="Bob",
            role="配角",
            gender="男",
            personality="沉稳",
            appearance="黑衣",
            voice_style="青年男声",
        )
        assert c.backstory == ""

    def test_story_creation(self):
        c1 = Character(
            name="Alice",
            role="主角",
            gender="女",
            personality="勇敢",
            appearance="红衣",
            voice_style="温柔女声",
        )
        c2 = Character(
            name="Bob",
            role="配角",
            gender="男",
            personality="沉稳",
            appearance="黑衣",
            voice_style="青年男声",
        )
        act = Act(
            act_number=1,
            name="开端",
            summary="故事开始",
            scenes=["intro", "出发"],
        )
        story = Story(
            title="测试故事",
            genre="仙侠",
            worldview="东方玄幻世界",
            plot_summary="一个测试故事",
            characters=[c1, c2],
            acts=[act],
            narration_style="第三人称",
        )
        assert story.title == "测试故事"
        assert story.genre == "仙侠"
        assert len(story.characters) == 2
        assert len(story.acts) == 1
        assert story.acts[0].act_number == 1
        assert story.narration_style == "第三人称"

    def test_story_empty_acts(self):
        """Story should accept empty acts list."""
        story = Story(
            title="空故事",
            genre="都市",
            worldview="现代",
            plot_summary="无",
            characters=[],
            acts=[],
            narration_style="第一人称",
        )
        assert story.acts == []


class TestShotCreation:
    """Verify Camera and Shot creation with correct field types."""

    def test_camera_defaults(self):
        cam = Camera()
        assert cam.type == "wide"
        assert cam.angle == "eye"
        assert cam.move == "static"

    def test_camera_custom(self):
        cam = Camera(type="closeup", angle="low", move="zoom-in")
        assert cam.type == "closeup"
        assert cam.angle == "low"
        assert cam.move == "zoom-in"

    def test_shot_creation(self):
        cam = Camera(type="medium", angle="eye", move="pan-left")
        shot = Shot(
            shot_id=1,
            scene="开场",
            duration=5,
            camera=cam,
            description="主角登场",
            prompt="A hero appears on the stage",
            dialogue="我来了",
            speaker="Alice",
            character=["Alice"],
            bgm_mood="epic",
            sfx="脚步声",
        )
        assert shot.shot_id == 1
        assert shot.scene == "开场"
        assert shot.duration == 5
        assert shot.camera.type == "medium"
        assert shot.camera.move == "pan-left"
        assert shot.dialogue == "我来了"
        assert shot.speaker == "Alice"
        assert shot.character == ["Alice"]
        assert shot.bgm_mood == "epic"
        assert shot.sfx == "脚步声"

    def test_shot_default_sfx(self):
        """sfx should default to empty string, speaker to None."""
        cam = Camera()
        shot = Shot(
            shot_id=2,
            scene="打斗",
            duration=3,
            camera=cam,
            description="打斗场景",
            prompt="fighting scene",
            dialogue="",
            character=["Bob"],
            bgm_mood="action",
        )
        assert shot.sfx == ""
        assert shot.speaker is None


class TestStoryboardCreation:
    """Verify Storyboard creation and total_shots field."""

    def test_storyboard_creation(self):
        character = Character(
            name="Alice",
            role="主角",
            gender="女",
            personality="勇敢",
            appearance="红衣",
            voice_style="温柔女声",
        )
        story = Story(
            title="测试",
            genre="仙侠",
            worldview="东方玄幻",
            plot_summary="测试故事",
            characters=[character],
            acts=[],
            narration_style="第三人称",
        )
        cam = Camera()
        shots = [
            Shot(
                shot_id=i,
                scene=f"scene_{i}",
                duration=5,
                camera=cam,
                description=f"描述{i}",
                prompt=f"prompt_{i}",
                dialogue="",
                character=["Alice"],
                bgm_mood="gentle",
            )
            for i in range(1, 4)
        ]
        board = Storyboard(
            story=story,
            shots=shots,
            total_shots=len(shots),
            estimated_duration=15,
        )
        assert board.total_shots == 3
        assert len(board.shots) == 3
        assert board.estimated_duration == 15
        assert board.story.title == "测试"

    def test_storyboard_zero_shots(self):
        """Storyboard with no shots should still validate correctly."""
        story = Story(
            title="空", genre="都市", worldview="现代",
            plot_summary="无", characters=[], acts=[],
            narration_style="第一人称",
        )
        board = Storyboard(
            story=story,
            shots=[],
            total_shots=0,
            estimated_duration=0,
        )
        assert board.total_shots == 0
        assert board.shots == []
