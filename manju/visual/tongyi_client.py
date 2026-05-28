"""万相2.7 文生图 API 客户端

封装阿里云 DashScope 万相2.7 图像生成 API。
支持同步和异步两种调用方式。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

from manju.config import load_config


class TongyiImageClient:
    """万相2.7 文生图客户端

    基于阿里云 DashScope 万相2.7 API：
      同步调用: POST /services/aigc/multimodal-generation/generation
      异步创建: POST /services/aigc/image-generation/generation (+ X-DashScope-Async: enable)
      轮询状态: GET  /tasks/{task_id}

    Args:
        api_key: 可选，直接传入 API Key，不传则从配置读取。
        base_url: API 基础地址。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
    ) -> None:
        config = load_config()
        self.api_key = api_key or config.get("image", {}).get("api_key", "")
        self.model = config.get("image", {}).get("model", "wan2.7-image-pro")
        self.base_url = base_url.rstrip("/")

        if not self.api_key:
            raise ValueError(
                "Image API key not found. Either pass api_key=... or set "
                "TONYI_API_KEY in environment / config.yaml"
            )

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        style: str = "",  # 保留兼容，wan2.7 不使用 style
        size: str = "2K",
        n: int = 1,
        wait: bool = True,
    ) -> list[str]:
        """提交文生图任务，返回图片 URL 列表。

        使用异步调用（提交任务 + 轮询结果）。

        Args:
            prompt:  图像描述文本（最多5000字符）。
            style:   保留兼容，wan2.7 不使用此参数。
            size:    分辨率规格。可选: "1K"、"2K"（默认）、"4K"（仅 pro 模型）。
            n:       生成张数，取值范围 1-4。
            wait:    是否等待任务完成。
                       - ``True``: 轮询至多 60 次（每次间隔 5 秒），返回图片 URL 列表。
                       - ``False``: 立即返回 ``[f"task:{task_id}"]`` 用于异步处理。

        Returns:
            图片 URL 列表。
        """
        # 构建万相2.7 消息格式
        payload = self._build_payload(prompt, size, n)

        if wait:
            return self._async_call(payload)
        else:
            return [f"task:{self._submit_async(payload)}"]

    def download(self, url: str, output_path: Path) -> Path:
        """下载图片到本地文件。

        Args:
            url:         图片下载 URL。
            output_path: 保存路径（含文件名）。

        Returns:
            保存成功的文件路径。
        """
        import urllib.request

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://dashscope.aliyuncs.com",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            with open(output_path, "wb") as f:
                f.write(resp.read())

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, prompt: str, size: str, n: int) -> dict[str, Any]:
        """构建万相2.7 API 请求体。"""
        return {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"text": prompt},
                        ],
                    }
                ],
            },
            "parameters": {
                "size": size,
                "n": n,
                "watermark": False,
            },
        }

    def _submit_async(self, payload: dict[str, Any]) -> str:
        """提交异步任务，返回 task_id。"""
        endpoint = f"{self.base_url}/services/aigc/image-generation/generation"

        # 万相2.7 异步调用需要 X-DashScope-Async: enable 请求头
        headers = dict(self._session.headers)
        headers["X-DashScope-Async"] = "enable"

        resp = self._session.post(
            endpoint,
            data=json.dumps(payload),
            headers=headers,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        task_id: str = data["output"]["task_id"]
        return task_id

    def _async_call(self, payload: dict[str, Any]) -> list[str]:
        """提交异步任务并轮询直到完成，返回图片 URL 列表。"""
        task_id = self._submit_async(payload)
        return self._poll(task_id)

    def _poll(self, task_id: str, max_attempts: int = 60, interval: float = 5.0) -> list[str]:
        """轮询任务状态，返回图片 URL 列表。

        Args:
            task_id:      任务ID。
            max_attempts: 最大轮询次数（默认60次=5分钟）。
            interval:     轮询间隔秒数（默认5秒）。

        Returns:
            图片 URL 列表。

        Raises:
            RuntimeError: 任务失败或被取消。
            TimeoutError: 超时未完成。
        """
        url = f"{self.base_url}/tasks/{task_id}"

        for attempt in range(1, max_attempts + 1):
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            output = data.get("output", {})
            status = output.get("task_status", "").upper()

            if status == "SUCCEEDED":
                # 万相2.7 成功响应格式
                choices = output.get("choices", [])
                urls: list[str] = []
                for choice in choices:
                    msg = choice.get("message", {})
                    contents = msg.get("content", [])
                    for content in contents:
                        if content.get("type") == "image":
                            urls.append(content["image"])
                if urls:
                    return urls
                # 兼容旧格式
                results = output.get("results", [])
                if results:
                    return [r["url"] for r in results]
                raise RuntimeError(
                    f"Task {task_id} SUCCEEDED but no image found in response"
                )

            if status in ("FAILED", "CANCELED"):
                msg = output.get("message", status)
                raise RuntimeError(
                    f"Image generation task {task_id} {status}: {msg}"
                )

            # PENDING / RUNNING — keep waiting
            if attempt < max_attempts:
                time.sleep(interval)

        raise TimeoutError(
            f"Image generation task {task_id} did not complete after "
            f"{max_attempts * interval:.0f}s"
        )
