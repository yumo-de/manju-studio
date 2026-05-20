"""故事扩写引擎 — 将主题扩展为完整故事大纲。"""

from manju.llm.llm_client import LLMClient
from manju.llm.prompt_templates import STORY_EXPAND_SYSTEM, STORY_EXPAND_USER
from manju.schemas.story import Story


class StoryExpander:
    """根据主题生成漫剧故事大纲。"""

    def __init__(self) -> None:
        self._client = LLMClient()

    def expand(self, theme: str) -> Story:
        """将主题扩展为完整 Story 对象。"""
        user_prompt = STORY_EXPAND_USER.format(theme=theme)
        data = self._client.chat_json(
            system=STORY_EXPAND_SYSTEM,
            user=user_prompt,
        )
        return Story(**data)
