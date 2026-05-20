"""剧本生成引擎 — 将故事大纲转化为结构化剧本（含对白和动作）。"""

from manju.llm.llm_client import LLMClient
from manju.llm.prompt_templates import SCRIPT_SYSTEM
from manju.schemas.story import Story


def _build_user_prompt(story: Story) -> str:
    """将 Story 对象格式化为 user prompt 文本。"""
    parts = [
        f"标题：{story.title}",
        f"类型：{story.genre}",
        f"世界观：{story.worldview}",
        f"故事概要：{story.plot_summary}",
        f"旁白风格：{story.narration_style}",
        "",
        "【角色】",
    ]
    for ch in story.characters:
        parts.append(
            f"- {ch.name}（{ch.role}，{ch.gender}）："
            f"{ch.personality}，外观：{ch.appearance}，声线：{ch.voice_style}"
        )

    parts.extend(["", "【幕与场景】"])
    for act in story.acts:
        parts.append(f"\n第{act.act_number}幕：{act.name}")
        parts.append(f"概要：{act.summary}")
        for i, sc in enumerate(act.scenes, 1):
            parts.append(f"  场景{i}：{sc}")

    return "\n".join(parts)


class ScriptWriter:
    """根据 Story 大纲生成结构化剧本场景列表。"""

    def __init__(self) -> None:
        self._client = LLMClient()

    def write(self, story: Story) -> list[dict]:
        """生成剧本场景，每个场景包含对白、动作、转场等字段。

        Returns:
            list[dict]: 场景列表，每项结构见 SCRIPT_SYSTEM 定义。
        """
        user_prompt = _build_user_prompt(story)
        raw = self._client.chat_json(
            system=SCRIPT_SYSTEM,
            user=user_prompt,
        )
        return raw["scenes"]
