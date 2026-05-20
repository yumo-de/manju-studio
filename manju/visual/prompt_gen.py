"""
Task 9: 图像 Prompt 生成器
根据 Shot List 生成高质量英文绘画 Prompt。
"""

from typing import Optional

from manju.schemas.story import Shot


class PromptGenerator:
    """根据镜头信息和题材生成高质量英文绘画 Prompt。"""

    # 题材风格中英文映射
    STYLE_PREFIX: dict[str, dict[str, str]] = {
        "仙侠": {
            "zh": "仙侠风格，水墨意境，东方玄幻",
            "en": "xianxia style, ink-wash artistic conception, eastern fantasy, ethereal atmosphere",
        },
        "武侠": {
            "zh": "武侠风格，写意江湖，古风韵味",
            "en": "wuxia style, martial arts epic, ancient Chinese painting aesthetics, misty mountains",
        },
        "科幻": {
            "zh": "科幻风格，赛博朋克/未来科技",
            "en": "sci-fi style, cyberpunk aesthetic, neon-lit futuristic cityscape, high-tech atmosphere",
        },
        "奇幻": {
            "zh": "奇幻风格，史诗感，魔法世界",
            "en": "high fantasy style, epic scale, mythical creatures, magical world, dramatic lighting",
        },
        "都市": {
            "zh": "现代都市风格，写实生活场景",
            "en": "modern urban style, realistic city life, contemporary architecture, natural lighting",
        },
        "历史": {
            "zh": "历史题材风格，写实厚重质感",
            "en": "historical epic style, period-accurate details, aged texture, cinematic composition",
        },
    }

    # 景别 → 英文描述
    CAMERA_MAP: dict[str, str] = {
        "wide": "wide shot",
        "medium": "medium shot",
        "closeup": "close-up shot",
        "extreme-closeup": "extreme close-up shot",
    }

    # 角度 → 英文描述
    ANGLE_MAP: dict[str, str] = {
        "eye": "eye-level angle",
        "low": "low angle shot",
        "high": "high angle shot",
        "overhead": "overhead bird's-eye view",
    }

    # 默认构图后缀
    SUFFIX: str = (
        "masterpiece, best quality, cinematic lighting, highly detailed, "
        "professional color grading, 8K, stunning visuals"
    )

    def build_prompt(self, shot: Shot, genre: str = "仙侠") -> str:
        """
        组合风格 + 景别 + 角度 + shot.prompt + 后缀，生成完整英文 Prompt。

        Args:
            shot: Shot 对象（包含 camera 信息和 prompt）
            genre: 题材类型，如 "仙侠"、"武侠"、"科幻" 等

        Returns:
            完整的英文绘画 Prompt 字符串
        """
        # 获取题材风格描述
        style_info = self.STYLE_PREFIX.get(genre, self.STYLE_PREFIX["仙侠"])
        style_en = style_info["en"]

        # 获取景别描述
        cam_type = shot.camera.type
        cam_desc = self.CAMERA_MAP.get(cam_type, f"{cam_type} shot")

        # 获取角度描述
        angle = shot.camera.angle
        angle_desc = self.ANGLE_MAP.get(angle, f"{angle} angle")

        # 镜头运动
        move = shot.camera.move
        if move and move != "static":
            move_desc = move.replace("-", " ").title()
            move_text = f", {move_desc}"
        else:
            move_text = ""

        # 角色描述（添加到 prompt 前）
        char_text = ""
        if shot.character:
            char_list = ", ".join(shot.character)
            char_text = f"{char_list}, "

        # 组合完整 prompt
        core_prompt = shot.prompt or shot.description or ""

        full_prompt = (
            f"{style_en}, {cam_desc}, {angle_desc}{move_text}, "
            f"{char_text}{core_prompt}, {self.SUFFIX}"
        )

        return full_prompt.strip().rstrip(",").strip()
