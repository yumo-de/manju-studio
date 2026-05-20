"""
LLM API 客户端 — 封装 DeepSeek API 调用，支持流式/非流式输出。
"""
from __future__ import annotations

import json
from typing import Any, Iterator

import httpx

from manju.config import load_config


class LLMClient:
    """DeepSeek Chat / JSON 双模式客户端。"""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or load_config()
        llm_cfg = cfg["llm"]
        self.api_key: str = llm_cfg["api_key"]
        self.model: str = llm_cfg["model"]
        self.base_url: str = llm_cfg["base_url"]
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0),
        )

    # ── chat ──────────────────────────────────────────────────────────

    def chat(
        self,
        system: str,
        user: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> str:
        """非流式 chat — 返回完整 assistant 文本。"""
        if stream:
            return "".join(self._chat_stream(system, user, **kwargs))
        payload = self._build_payload(system, user, stream=False, **kwargs)
        resp = self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat_stream(
        self,
        system: str,
        user: str,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式 chat — 逐块产出文本片段。"""
        yield from self._chat_stream(system, user, **kwargs)

    # ── chat_json ─────────────────────────────────────────────────────

    def chat_json(
        self,
        system: str,
        user: str,
        stream: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """强制 JSON 输出，解析并返回 dict。"""
        if stream:
            raw = "".join(self._chat_stream(system, user, json_mode=True, **kwargs))
        else:
            payload = self._build_payload(
                system, user, stream=False, json_mode=True, **kwargs
            )
            resp = self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw = data["choices"][0]["message"]["content"]
        return json.loads(raw)

    def chat_json_stream(
        self,
        system: str,
        user: str,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式 JSON 输出 — 逐块产出文本片段（调用方自行 json.loads 合并）。"""
        yield from self._chat_stream(system, user, json_mode=True, **kwargs)

    # ── internal helpers ──────────────────────────────────────────────

    def _build_payload(
        self,
        system: str,
        user: str,
        stream: bool = False,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": stream,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        payload.update(kwargs)
        return payload

    def _chat_stream(
        self,
        system: str,
        user: str,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> Iterator[str]:
        payload = self._build_payload(
            system, user, stream=True, json_mode=json_mode, **kwargs
        )
        with self._client.stream("POST", "/v1/chat/completions", json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    chunk = json.loads(data_str)
                    delta = chunk["choices"][0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content

    def close(self) -> None:
        self._client.close()
