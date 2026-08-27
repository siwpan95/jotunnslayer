"""
JSONLoader — 通用 JSON 数据加载器（带缓存 + UTF-8 安全）

从 hell below/shared_core/json_loader.py 提取并增强。

使用示例:
    loader = JSONLoader("data/")
    config = loader.load("config.json")
    levels = loader.load_mandatory("levels.json")
    loader.clear_cache()
"""

from __future__ import annotations

import copy
import glob
import json
import os
from typing import Any, Dict, List, Optional


class JSONLoader:
    """加载并缓存 JSON 数据文件。

    特性:
        - 自动内存缓存，避免重复 I/O
        - UTF-8 编码强制
        - 强制加载模式（缺失抛异常）
        - 缓存清除 / 重新加载
        - 文件列表检索
    """

    def __init__(self, data_dir: str = "", logger: Any = None):
        """初始化 JSON 加载器。

        参数:
            data_dir: 数据目录路径，空字符串表示使用绝对路径
            logger: 可选的 Logger 实例
        """
        self.data_dir = data_dir or ""
        self._cache: Dict[str, Any] = {}
        self._encoding = "utf-8"
        self._logger = logger

    def _log(self, msg: str) -> None:
        """记录错误信息。"""
        if self._logger:
            self._logger.warning(f"[JSONLoader] {msg}")
        else:
            import sys
            print(f"[JSONLoader] {msg}", file=sys.stderr, flush=True)

    # ── 加载方法 ──

    def load(self, filename: str) -> Optional[Any]:
        """加载 JSON 文件（带缓存）。

        参数:
            filename: 文件名（相对 data_dir）或绝对路径

        返回:
            解析后的 Python 对象，文件不存在或解析失败返回 None
        """
        # 缓存命中
        if filename in self._cache:
            return self._cache[filename]

        # 构建路径
        path = self._resolve_path(filename)
        if not os.path.exists(path):
            return None

        # 读取并解析
        try:
            with open(path, "r", encoding=self._encoding) as f:
                data = json.load(f)
            # 深拷贝后缓存：避免调用方修改返回对象污染缓存（共享可变状态）
            self._cache[filename] = copy.deepcopy(data)
            return copy.deepcopy(data)
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            self._log(f"加载失败 {path}: {e}")
            return None

    def load_mandatory(self, filename: str) -> Any:
        """必须加载 — 文件缺失或解析失败则抛出异常。

        参数:
            filename: 文件名

        返回:
            解析后的 Python 对象

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON 解析失败
        """
        data = self.load(filename)
        if data is None:
            path = self._resolve_path(filename)
            if not os.path.exists(path):
                raise FileNotFoundError(f"必需数据文件缺失: {path}")
            raise ValueError(f"JSON 解析失败: {path}")
        return data

    def reload(self, filename: str) -> Optional[Any]:
        """强制重新加载 JSON 文件（忽略缓存）。

        参数:
            filename: 文件名

        返回:
            解析后的对象
        """
        self._cache.pop(filename, None)
        return self.load(filename)

    # ── 缓存管理 ──

    def clear_cache(self) -> None:
        """清除所有缓存。"""
        self._cache.clear()

    def cache_size(self) -> int:
        """返回缓存文件数。"""
        return len(self._cache)

    def is_cached(self, filename: str) -> bool:
        """检查文件是否在缓存中。"""
        return filename in self._cache

    # ── 文件列表 ──

    def list_available(self, pattern: str = "*.json") -> List[str]:
        """列出 data_dir 下所有匹配模式的文件名。

        参数:
            pattern: glob 模式（如 "*.json", "data/*.json"）

        返回:
            文件名列表（仅文件名，不含路径前缀）
        """
        if not self.data_dir:
            return []
        if not os.path.isdir(self.data_dir):
            return []

        full_pattern = os.path.join(self.data_dir, pattern)
        return [os.path.basename(f) for f in glob.glob(full_pattern)]

    def list_all(self) -> List[str]:
        """列出 data_dir 下所有 JSON 文件。"""
        return self.list_available("*.json")

    # ── 编码 ──

    def set_encoding(self, encoding: str):
        """设置文件编码。

        参数:
            encoding: 编码名（如 "utf-8", "gbk"）
        """
        self._encoding = encoding

    # ── 内部 ──

    def _resolve_path(self, filename: str) -> str:
        """将文件名解析为完整路径。"""
        # 如果已经是绝对路径
        if os.path.isabs(filename):
            return filename

        # 相对于 data_dir
        if self.data_dir:
            return os.path.join(self.data_dir, filename)

        # 相对于当前工作目录
        return filename
