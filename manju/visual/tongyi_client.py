"""通义万相文生图 API 客户端

封装阿里云 DashScope 通义万相 (Wanx) 图像生成 API。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import requests

from manju.config import load_config


class TongyiImageClient:
    """通义万相文生图客户端

    基于阿里云 DashScope API：
      - 提交任务: POST /services/aigc/text2image/image-synthesis
      - 轮询状态: GET  /tasks/{task_id}

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
        self.model = config.get("image", {}).get("model", "wanx-v1")
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
        style: str = "<auto>",
        size: str = "1920x1080",
        n: int = 1,
        wait: bool = True,
    ) -> list[str]:
        """提交文生图任务，可选等待完成。

        Args:
            prompt:  图像描述文本。
            style:   风格，默认 ``<auto>`` 自动选择。
            size:    尺寸，格式 ``宽x高`` (e.g. ``1920x1080``)。
            n:       生成张数。
            wait:    是否等待任务完成。
                       - ``True``: 轮询至多 30 次（每次间隔 10 秒），返回图片 URL 列表。
                       - ``False``: 立即返回 ``[f"task:{task_id}"]`` 用于异步处理。

        Returns:
            图片 URL 列表，或 task ID 占位列表。
        """
        task_id = self._submit(prompt, style=style, size=size, n=n)

        if not wait:
            return [f"task:{task_id}"]

        return self._poll(task_id)

    def download(self, url: str, output_path: Path) -> Path:
        """下载图片到本地文件。

        Args:
            url:         图片下载 URL。
            output_path: 保存路径（含文件名）。

        Returns:
            保存成功的文件路径。
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        resp = self._session.get(url, stream=True, timeout=120)
        resp.raise_for_status()

        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        return output_path

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _submit(
        self,
        prompt: str,
        style: str = "<auto>",
        size: str = "1920x1080",
        n: int = 1,
    ) -> str:
        """提交生成任务，返回 task_id。"""
        payload: dict[str, Any] = {
            "model": self.model,
            "input": {"prompt": prompt},
            "parameters": {
                "size": size,
                "n": n,
                "style": style,
            },
        }

        resp = self._session.post(
            f"{self.base_url}/services/aigc/text2image/image-synthesis",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()

        task_id: str = data["output"]["task_id"]
        return task_id

    def _poll(self, task_id: str, max_attempts: int = 30, interval: float = 10.0) -> list[str]:
        """轮询任务状态，返回图片 URL 列表。"""
        url = f"{self.base_url}/tasks/{task_id}"

        for attempt in range(1, max_attempts + 1):
            resp = self._session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            output = data.get("output", {})
            status = output.get("task_status", "").upper()

            if status == "SUCCEEDED":
                results = output.get("results", [])
                return [r["url"] for r in results]

            if status in ("FAILED", "CANCELED"):
                msg = output.get("message", status)
                raise RuntimeError(
                    f"Image generation task {task_id} {status}: {msg}"
                )

            # RUNNING / PENDING — keep waiting
            if attempt < max_attempts:
                time.sleep(interval)

        raise TimeoutError(
            f"Image generation task {task_id} did not complete after "
            f"{max_attempts * interval:.0f}s"
        )
