"""
Image generation cache — 相同 prompt + size 不重复调用 API。

使用逻辑：
  1. generate() 前检查缓存（hash(prompt + model + size)）
  2. 命中 → 直接返回缓存文件路径
  3. 未命中 → 调用 API → 下载 → 缓存 → 返回

缓存存于 config 中 image.cache_dir 指定目录（默认 data/image_cache）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("image_cache")


class ImageCache:
    """本地图片生成缓存。

    Args:
        cache_dir: 缓存根目录，默认为 ``data/image_cache``。
        max_entries: 最大缓存条目数（默认 500），超限时淘汰最旧条目。
    """

    def __init__(
        self,
        cache_dir: str = "data/image_cache",
        max_entries: int = 500,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_entries = max_entries
        self._index_path = self.cache_dir / "_index.json"
        self._index: dict[str, dict[str, Any]] = {}
        self._load_index()

    # ── public API ────────────────────────────────────────────────────────

    def get(
        self,
        prompt: str,
        model: str,
        size: str = "2K",
    ) -> str | None:
        """检查缓存。如果命中返回本地文件路径，否则返回 None。"""
        key = self._make_key(prompt, model, size)
        entry = self._index.get(key)
        if entry is None:
            return None

        file_path = self.cache_dir / entry["filename"]
        if not file_path.exists():
            # 缓存文件已被删除，移除索引条目
            del self._index[key]
            self._save_index()
            return None

        logger.debug("Cache HIT: %s -> %s (size=%s)", prompt[:40], file_path, size)
        return str(file_path)

    def put(
        self,
        prompt: str,
        model: str,
        size: str,
        source_path: str,
    ) -> str:
        """将下载的图片存入缓存，返回缓存内的文件路径。

        Args:
            prompt: 生成 prompt。
            model: 模型名。
            size: 规格（1K/2K/4K）。
            source_path: 已下载的图片路径。

        Returns:
            缓存文件路径。
        """
        key = self._make_key(prompt, model, size)
        ext = Path(source_path).suffix or ".png"
        filename = f"{key}{ext}"
        dest = self.cache_dir / filename

        # 如果已经存在相同 key，覆盖
        shutil.copy2(source_path, dest)

        self._index[key] = {
            "prompt": prompt,
            "model": model,
            "size": size,
            "filename": filename,
            "created_at": time.time(),
        }
        self._save_index()
        self._evict_if_needed()

        logger.debug("Cache PUT: %s -> %s", prompt[:40], dest)
        return str(dest)

    def clear(self) -> None:
        """清空缓存。"""
        self._index.clear()
        self._save_index()
        for f in self.cache_dir.iterdir():
            if f.name != "_index.json":
                f.unlink()
        logger.info("Image cache cleared.")

    def stats(self) -> dict[str, Any]:
        """返回缓存统计信息。"""
        total_size = sum(
            f.stat().st_size
            for f in self.cache_dir.iterdir()
            if f.is_file() and f.name != "_index.json"
        )
        return {
            "entries": len(self._index),
            "max_entries": self.max_entries,
            "disk_size_bytes": total_size,
            "cache_dir": str(self.cache_dir),
        }

    # ── internal ──────────────────────────────────────────────────────────

    def _make_key(self, prompt: str, model: str, size: str) -> str:
        """生成缓存 key = sha256(prompt + model + size)[:16]"""
        raw = f"{prompt}||{model}||{size}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:16]

    def _load_index(self) -> None:
        if self._index_path.exists():
            try:
                with open(self._index_path, "r") as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, OSError):
                logger.warning("缓存索引损坏，重置为空")
                self._index = {}

    def _save_index(self) -> None:
        try:
            with open(self._index_path, "w") as f:
                json.dump(self._index, f, indent=2)
        except OSError as e:
            logger.warning("缓存索引写入失败: %s", e)

    def _evict_if_needed(self) -> None:
        """如果条目超限，淘汰最旧的 10%。"""
        if len(self._index) <= self.max_entries:
            return

        sorted_items = sorted(
            self._index.items(), key=lambda x: x[1]["created_at"]
        )
        to_remove = int(self.max_entries * 0.1)
        for key, entry in sorted_items[:to_remove]:
            file_path = self.cache_dir / entry["filename"]
            if file_path.exists():
                file_path.unlink()
            del self._index[key]
        self._save_index()
        logger.info("缓存淘汰: 移除了 %d 个最旧条目", to_remove)
