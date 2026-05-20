from pydantic import BaseModel
from typing import Optional


class Character(BaseModel):
    name: str
    role: str           # 主角/配角/反派
    gender: str
    personality: str
    appearance: str
    voice_style: str    # Edge-TTS voice name
    backstory: str = ""


class Act(BaseModel):
    act_number: int
    name: str
    summary: str
    scenes: list[str]


class Story(BaseModel):
    title: str
    genre: str
    worldview: str
    plot_summary: str
    characters: list[Character]
    acts: list[Act]
    narration_style: str   # 旁白风格


class Camera(BaseModel):
    type: str = "wide"    # wide/medium/closeup/extreme-closeup
    angle: str = "eye"    # eye/low/high/overhead
    move: str = "static"  # static/pan-left/pan-right/tilt-up/tilt-down/zoom-in/zoom-out


class Shot(BaseModel):
    shot_id: int
    scene: str
    duration: int         # 秒
    camera: Camera
    description: str      # 画面描述（中文）
    prompt: str           # 文生图 prompt（英文）
    dialogue: str         # 台词/旁白
    speaker: Optional[str] = None  # 说话角色
    character: list[str]
    bgm_mood: str         # epic/tense/gentle/comic/action
    sfx: str = ""


class Storyboard(BaseModel):
    story: Story
    shots: list[Shot]
    total_shots: int
    estimated_duration: int  # 总时长（秒）
