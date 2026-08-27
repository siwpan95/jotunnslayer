"""
资源路径工具 — 兼容开发环境、pip install 与 PyInstaller 打包环境
==================================================================

- 打包后通过 sys._MEIPASS 定位资源根目录
- pip install 后使用 importlib.resources 定位包目录
- 开发时回退到项目根目录（core/ 的父目录的父目录）
- 可写目录（saves/logs）使用用户数据目录

用法：
    from alloy.core.paths import ROOT, get_assets_dir

    sprite_path = get_assets_dir() / "sprites" / "player.png"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _get_package_root() -> Path:
    """返回 alloy 包所在的目录。

    优先级：
    1. 打包环境（PyInstaller / Nuitka）：sys._MEIPASS
    2. 环境变量 ALLIN_ROOT 覆盖
    3. importlib.resources（pip install 环境）
    4. __file__ 回退（开发环境）
    """
    # 打包环境
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)

    # 环境变量覆盖
    env_root = os.environ.get("ALLIN_ROOT")
    if env_root:
        return Path(env_root)

    # 优先使用 importlib.resources（兼容 pip install）
    try:
        from importlib.resources import files
        pkg_path = files("alloy")
        if pkg_path.is_dir():
            return Path(str(pkg_path)).parent  # 项目根（alloy 的父目录）
    except Exception:
        pass

    # 开发环境回退：core/paths.py → alloy/ → 项目根
    return Path(__file__).resolve().parent.parent.parent


def _get_user_data_dir() -> Path:
    """返回用户数据目录（跨平台）。

    - Windows: %APPDATA%/alloy
    - Linux/macOS: ~/.local/share/alloy 或 ~/.alloy
    """
    # 环境变量覆盖
    env_data = os.environ.get("ALLIN_USER_DATA")
    if env_data:
        return Path(env_data)

    if sys.platform == "win32":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "alloy"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
        return Path(xdg) / "alloy"


# ── 路径常量 ──────────────────────────────────────────

ROOT: Path = _get_package_root()
"""项目 / 资源根目录。"""

ENGINE_DIR: Path = ROOT / "alloy"
"""引擎根目录。"""

CORE_DIR: Path = ENGINE_DIR / "core"
"""核心模块目录。"""

USER_DATA_DIR: Path = _get_user_data_dir()
"""用户数据根目录（可写，跨平台）。"""


# ── 只读资源目录 ──────────────────────────────────────

def _get_readable_dir(subdir: str) -> Path:
    """获取只读资源目录，优先包内，回退 ROOT。"""
    pkg_dir = ENGINE_DIR / subdir
    if pkg_dir.exists():
        return pkg_dir
    root_dir = ROOT / subdir
    return root_dir


def get_data_dir() -> Path:
    """返回游戏数据目录（data/）。"""
    return _get_readable_dir("data")


def get_assets_dir() -> Path:
    """返回资源目录（assets/）。"""
    return _get_readable_dir("assets")


def get_fonts_dir() -> Path:
    """返回本地字体目录（fonts/）。

    用于存放随包分发的字体文件（.ttf/.otf/.ttc/.woff 等）。
    路径解析兼容开发环境、pip install 与 PyInstaller 打包：
        1. <包>/fonts    （首选，随包分发）
        2. <资源根>/fonts  （开发环境回退）
    若目录不存在也返回预期路径（调用方负责判断文件是否存在）。
    """
    return _get_readable_dir("fonts")


def get_config_dir() -> Path:
    """返回配置文件目录（config/）。"""
    return _get_readable_dir("config")


# ── 可写目录 ──────────────────────────────────────────

def _get_writable_dir(subdir: str) -> Path:
    """获取可写目录（用户数据目录下）。不存在则创建。"""
    path = USER_DATA_DIR / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_save_dir() -> Path:
    """返回存档目录（saves/）。不存在则创建。"""
    return _get_writable_dir("saves")


def get_logs_dir() -> Path:
    """返回日志目录（logs/）。不存在则创建。"""
    return _get_writable_dir("logs")


def get_resource_root() -> Path:
    """返回资源根目录（公开接口，兼容旧版 API）。

    等同于 ROOT 常量，但以函数形式提供。
    """
    return ROOT


def ensure_dirs() -> list[Path]:
    """确保所有标准子目录存在，返回创建的目录列表。"""
    dirs = [
        _get_writable_dir("saves"),
        _get_writable_dir("logs"),
    ]
    return dirs
