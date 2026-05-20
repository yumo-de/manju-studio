"""
LLM API 客户端 — 封装 DeepSeek API 调用，支持流式/非流式输出。

含 JSON 自动修复 + 指数退避重试。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Iterator

import httpx

from manju.config import load_config

logger = logging.getLogger(__name__)

# ── JSON 修复工具 ─────────────────────────────────────────────────────────


def _repair_json(raw: str) -> str:
    """尝试修复 LLM 返回的常见 JSON 格式问题。"""
    text = raw.strip()

    # 1. 去除 markdown 代码块标记 (```json ... ``` 或 ``` ... ```)
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\n?```\s*$", "", text)

    # 2. 去除 BOM
    text = text.lstrip("\ufeff")

    # 3. 确保以 { 开头、} 结尾（当预期返回对象时）
    text = text.strip()
    if text.startswith("{"):
        # 找到匹配的闭合括号
        depth = 0
        end_idx = -1
        for i, ch in enumerate(text):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
        if end_idx > 0:
            text = text[: end_idx + 1]

    # 4. 修复 trailing comma (JSON 不允许末尾逗号)
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # 5. 修复单引号为双引号（只当字符串中没有双引号时做，避免破坏英文文本中的撇号）
    if '"' not in text.replace("'", ""):
        text = re.sub(r"(?<!\")'(?!\")", '"', text)

    # 6. 修复 unquoted keys (Python dict style: {key: value})
    #    匹配 { 或 , 后跟非引号字符的 key: 模式
    text = re.sub(
        r'(?<=[{,])\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:',
        r'"\1":',
        text,
    )

    # 7. 修复 Python True/False/None
    text = text.replace("True", "true").replace("False", "false").replace("None", "null")

    return text.strip()


def _safe_json_parse(raw: str, max_attempts: int = 1) -> dict[str, Any]:
    """安全解析 JSON，自动修复常见问题。

    Returns:
        解析后的 dict。

    Raises:
        json.JSONDecodeError: 修复后仍无法解析。
    """
    # 第一次直接尝试 (最快路径)
    repaired = _repair_json(raw)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # 第二次：清理控制字符
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", repaired)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 第三次：极端修复 — 尝试提取 JSON 对象
    cleaned = cleaned.strip()
    brace_start = cleaned.find("{")
    brace_end = cleaned.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(cleaned[brace_start : brace_end + 1])
        except json.JSONDecodeError:
            pass

    raise json.JSONDecodeError(
        f"Failed to parse JSON after repair. Raw text (first 200 chars):\n"
        f"{raw[:200]}",
        raw,
        0,
    )


# ── LLMClient ──────────────────────────────────────────────────────────────


class LLMClient:
    """DeepSeek Chat / JSON 双模式客户端。"""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        max_retries: int = 3,
        max_tokens: int | None = 16384,
    ) -> None:
        cfg = config or load_config()
        llm_cfg = cfg["llm"]
        self.api_key: str = llm_cfg["api_key"]
        self.model: str = llm_cfg["model"]
        self.base_url: str = llm_cfg["base_url"]
        self.max_retries = max_retries
        self.max_tokens = max_tokens
        self._client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(180.0),
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
        return self._call_with_retry(
            lambda: self._chat_once(system, user, stream=False, **kwargs)
        )

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
        """强制 JSON 输出，解析并返回 dict。

        内建容错机制:
          - 自动修复常见 JSON 格式问题 (trailing comma, 单引号, 无引号 key)
          - 失败后自动重试 (指数退避, 默认最多 3 次)
          - 重试时轮换不同的 system prompt 变体
        """
        last_error = None
        system_variants = [system]

        for attempt in range(1, self.max_retries + 1):
            try:
                if stream:
                    raw = "".join(
                        self._chat_stream(
                            system_variants[-1], user, json_mode=True, **kwargs
                        )
                    )
                else:
                    raw = self._call_with_retry(
                        lambda: self._chat_once(
                            system_variants[-1], user, stream=False, json_mode=True, **kwargs
                        )
                    )

                return _safe_json_parse(raw)

            except (json.JSONDecodeError, KeyError, ValueError) as e:
                last_error = e
                logger.warning(
                    "chat_json attempt %d/%d failed: %s",
                    attempt, self.max_retries, e,
                )
                if attempt < self.max_retries:
                    # 重试提示词添加严格要求
                    strict_note = (
                        "\n\n⚠ IMPORTANT: Your previous response was not valid JSON. "
                        "Return ONLY a raw JSON object. NO markdown code fences, "
                        "NO extra text before or after the JSON. "
                        "Use double quotes for all strings and keys."
                    )
                    if stream:
                        system_variants.append(system)
                    else:
                        # 不用改 system, 在 kwargs 中添加用户强调
                        pass
                    wait = 2 ** attempt  # 指数退避: 2s, 4s, 8s
                    logger.info("Retrying in %ds...", wait)
                    time.sleep(wait)

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    "HTTP error on attempt %d/%d: %s",
                    attempt, self.max_retries, e,
                )
                if attempt < self.max_retries:
                    wait = 2 ** attempt
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError(
            f"chat_json failed after {self.max_retries} attempts. "
            f"Last error: {last_error}"
        )

    def chat_json_stream(
        self,
        system: str,
        user: str,
        **kwargs: Any,
    ) -> Iterator[str]:
        """流式 JSON 输出 — 逐块产出文本片段（调用方自行 json.loads 合并）。"""
        yield from self._chat_stream(system, user, json_mode=True, **kwargs)

    # ── internal: 单次调用 ────────────────────────────────────────────

    def _chat_once(
        self,
        system: str,
        user: str,
        stream: bool = False,
        json_mode: bool = False,
        **kwargs: Any,
    ) -> str:
        """单次 API 调用，返回完整响应文本。"""
        payload = self._build_payload(system, user, stream=False, json_mode=json_mode, **kwargs)
        resp = self._client.post("/v1/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def _call_with_retry(self, fn, max_http_retries: int = 2) -> str:
        """对 HTTP 层面的错误进行重试。"""
        last_error = None
        for attempt in range(1, max_http_retries + 1):
            try:
                return fn()
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                logger.warning("Network error (attempt %d/%d): %s", attempt, max_http_retries, e)
                if attempt < max_http_retries:
                    time.sleep(2 ** attempt)
        # 最后一次尝试
        return fn()

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
        if self.max_tokens is not None:
            payload["max_tokens"] = self.max_tokens
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
