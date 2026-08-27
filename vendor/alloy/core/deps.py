"""可选依赖探测 — 补齐 "可选依赖运行时才报错" 短板。

提供统一的依赖可用性探测与干净的缺失报错，替代散落在各处的 import 期静默 +
调用期 ImportError。

纯新增模块，无硬依赖（仅用标准库 importlib）。
"""

from __future__ import annotations

import importlib.util
from typing import Any, Dict, List


class MissingDependencyError(ImportError):
    """缺少可选依赖时抛出，附安装提示。"""

    def __init__(self, module: str, hint: str = ""):
        self.module = module
        self.hint = hint
        msg = f"缺少可选依赖 '{module}'，该功能不可用。"
        if hint:
            msg += f" 安装：{hint}"
        super().__init__(msg)


_PIP_HINTS = {
    "numpy": "pip install numpy",
    "scipy": "pip install scipy",
    "pygame": "pip install pygame-ce",
    "asteval": "pip install asteval",
}

_OPTIONAL = ("numpy", "scipy", "pygame", "asteval")


def _has(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def has(mod: str) -> bool:
    """某可选依赖是否可用。"""
    return _has(mod)


def feature_flags() -> Dict[str, bool]:
    """返回各可选依赖是否可用的字典。"""
    return {m: _has(m) for m in _OPTIONAL}


def require(mod: str, hint: str = "") -> Any:
    """要求某可选依赖；缺失则抛 MissingDependencyError（带安装提示）。"""
    if not _has(mod):
        raise MissingDependencyError(mod, hint or _PIP_HINTS.get(mod, f"pip install {mod}"))
    return importlib.import_module(mod)


def report() -> str:
    """可读的依赖状态报告。"""
    flags = feature_flags()
    lines = ["可选依赖状态："]
    for m, ok in flags.items():
        mark = "OK" if ok else "缺失"
        extra = "" if ok else f"  (安装: {_PIP_HINTS.get(m, '')})"
        lines.append(f"  [{mark}] {m}{extra}")
    return "\n".join(lines)
