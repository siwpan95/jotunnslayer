"""
字体加载工具 — 本地字体优先 + 多平台 CJK 兜底

本地字体（从包内 fonts/ 目录加载）：
    - 随包分发的字体文件（.ttf/.otf/.ttc/.woff/.woff2）
    - 通过 register_local_font() 手动注册的别名字体
    - 通过 ALLIN_FONT_PATH 环境变量指定的单个字体

加载策略（load_cjk_font / load_local_font）：
    1. ALLIN_FONT_PATH 环境变量（单个字体文件）
    2. 本地 fonts/ 目录（local_first=True 时优先；或显式按 name 指定）
    3. 平台默认系统字体（Windows/macOS/Linux）
    4. pygame.font.SysFont / pygame.font.Font(None) 兜底

从 carimara_py/core/utils.py 和 shared/font_utils 融合，并新增本地字体子系统。

使用示例：
    # 加载包内打包字体（默认第一个发现的本地字体）
    font = load_local_font(32, bold=True)            # pygame.Font
    tk_font = load_local_tk_font(16)                 # tkinter.font.Font

    # 按名字加载（别名 = 文件名 stem，大小写不敏感）
    font = load_local_font(32, name="baocanmou")

    # 让 load_cjk_font 优先使用本地字体
    font = load_cjk_font(16, local_first=True)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union


# ================================================================
#  本地字体目录
# ================================================================

try:
    from vendor.alloy.core.paths import get_fonts_dir
except Exception:  # pragma: no cover - 防御性兜底
    def get_fonts_dir() -> Path:  # type: ignore
        return Path(__file__).resolve().parent.parent / "fonts"


# 支持的字体扩展名
FONT_EXTENSIONS: Tuple[str, ...] = (".ttf", ".otf", ".ttc", ".woff", ".woff2")

# 本地字体缓存（按 key 复用，避免重复加载大体积 TTF）
_FONT_CACHE: Dict[Tuple[str, int, bool, int], object] = {}
# 别名注册表：alias(小写) -> 字体路径
_LOCAL_FONT_REGISTRY: Dict[str, Path] = {}
_DISCOVERY_DONE: bool = False


# ================================================================
#  平台字体路径映射
# ================================================================

# Windows 常用中文字体
_WIN_FONT_PATHS: List[str] = [
    "C:/Windows/Fonts/msyh.ttc",       # 微软雅黑
    "C:/Windows/Fonts/msyhbd.ttc",     # 微软雅黑 粗体
    "C:/Windows/Fonts/simsun.ttc",     # 宋体
    "C:/Windows/Fonts/simhei.ttf",     # 黑体
    "C:/Windows/Fonts/kaiu.ttf",       # 楷体
    "C:/Windows/Fonts/msgothic.ttc",   # MS Gothic (日语备选)
]

# macOS 常用中文字体
_MAC_FONT_PATHS: List[str] = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",  # 韩语备选
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
]

# Linux 常用中文字体
_LINUX_FONT_PATHS: List[str] = [
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    "/usr/share/fonts/truetype/arphic/ukai.ttc",
]


def _get_platform_font_paths() -> List[str]:
    """获取当前平台的字体搜索路径列表。"""
    if sys.platform == "win32":
        return _WIN_FONT_PATHS
    elif sys.platform == "darwin":
        return _MAC_FONT_PATHS
    else:
        return _LINUX_FONT_PATHS


# ================================================================
#  本地字体发现 / 注册
# ================================================================

def get_local_fonts_dir() -> Path:
    """返回本地字体目录（core.paths.get_fonts_dir 的便捷封装）。"""
    return get_fonts_dir()


def discover_local_fonts(
    fonts_dir: Optional[Union[str, Path]] = None,
) -> List[Tuple[str, Path]]:
    """扫描本地字体目录，返回 [(小写别名, 路径), ...] 并注册进别名表。

    别名 = 字体文件名（不含扩展名），统一转小写，便于按名加载。
    后续调用 load_local_font(name="xxx") 即可命中。

    参数：
        fonts_dir: 自定义扫描目录；省略则使用包内 fonts/ 目录。

    返回：
        [(alias, path), ...]，按文件名排序。
    """
    global _DISCOVERY_DONE
    base = Path(fonts_dir) if fonts_dir else get_local_fonts_dir()
    found: List[Tuple[str, Path]] = []
    if base.exists() and base.is_dir():
        for p in sorted(base.iterdir()):
            if p.is_file() and p.suffix.lower() in FONT_EXTENSIONS:
                alias = p.stem.lower()
                _LOCAL_FONT_REGISTRY[alias] = p
                found.append((alias, p))
    _DISCOVERY_DONE = True
    return found


def register_local_font(alias: str, path: Union[str, Path]) -> None:
    """手动注册一个本地字体别名（覆盖自动发现结果）。

    参数：
        alias: 字体别名（如 "baocanmou" / "我的手写体"）
        path:  字体文件路径
    """
    global _DISCOVERY_DONE
    _LOCAL_FONT_REGISTRY[alias.lower()] = Path(path)
    _DISCOVERY_DONE = True


def _ensure_discovered() -> None:
    """确保至少执行过一次本地字体扫描。"""
    global _DISCOVERY_DONE
    if not _DISCOVERY_DONE:
        discover_local_fonts()


def _resolve_local_font_path(name: Optional[str] = None) -> Optional[Path]:
    """解析本地字体路径。

    参数：
        name: 字体别名 / 文件名 stem / 完整路径；省略则返回第一个发现的本地字体。

    返回：
        字体路径，或 None（未找到）。
    """
    _ensure_discovered()
    if name:
        key = name.lower()
        if key in _LOCAL_FONT_REGISTRY:
            return _LOCAL_FONT_REGISTRY[key]
        # 模糊匹配：别名包含或包含于关键词
        for alias, p in _LOCAL_FONT_REGISTRY.items():
            if key in alias or alias in key:
                return p
        # 当作完整路径兜底
        cand = Path(name)
        if cand.exists():
            return cand
        return None
    # 无 name：返回注册表中第一个（稳定顺序，字典保序）
    if _LOCAL_FONT_REGISTRY:
        return next(iter(_LOCAL_FONT_REGISTRY.values()))
    return None


#: 引擎随包分发的默认字体文件名 stem（大小写不敏感），
#: 保证各项目即使往 fonts/ 目录添加自己的字体，默认字体也保持稳定。
BUNDLED_FONT_STEM: str = "baocanmou"


def get_default_local_font_name() -> Optional[str]:
    """返回默认本地字体别名。

    优先引擎随包分发的字体（BUNDLED_FONT_STEM，跨项目稳定）；
    否则返回第一个发现的本地字体；无则 None。
    """
    _ensure_discovered()
    if not _LOCAL_FONT_REGISTRY:
        return None
    for alias in _LOCAL_FONT_REGISTRY:
        if BUNDLED_FONT_STEM in alias:
            return alias
    return next(iter(_LOCAL_FONT_REGISTRY.keys()))


def list_local_fonts() -> List[Tuple[str, str]]:
    """列出已发现的本地字体 [(别名, 绝对路径), ...]。"""
    _ensure_discovered()
    return [(alias, str(p)) for alias, p in _LOCAL_FONT_REGISTRY.items()]


def clear_font_cache() -> None:
    """清空字体缓存（测试 / 热重载用）。"""
    _FONT_CACHE.clear()
    _LOCAL_FONT_REGISTRY.clear()
    global _DISCOVERY_DONE
    _DISCOVERY_DONE = False


# ================================================================
#  Pygame 字体加载
# ================================================================

def _load_pygame_font_any(
    pygame, path: Path, size: int, face_index: int = 0
) -> Optional["pygame.font.Font"]:
    """尝试用 pygame 加载字体文件，失败返回 None。

    - .ttc 多字脸字体使用 (path, face_index) 形式
    - .woff/.woff2 交由 pygame 自行处理（部分构建支持），失败则 None
    """
    # 防御性初始化字体子系统（无显示环境 / 未调用 pygame.init 时也能用）
    try:
        pygame.font.init()
    except Exception:
        pass
    path_str = str(path)
    ext = path.suffix.lower()
    try:
        if ext == ".ttc":
            return pygame.font.Font((path_str, face_index), size)
        return pygame.font.Font(path_str, size)
    except Exception:
        return None


def _try_load_pygame_font(
    pygame, path: str, size: int, face_index: int = 0
) -> Optional["pygame.font.Font"]:
    """尝试加载 pygame 字体，失败返回 None。"""
    p = Path(path)
    return _load_pygame_font_any(pygame, p, size, face_index)


def load_local_font(
    size: int,
    name: Optional[str] = None,
    bold: bool = False,
    face_index: int = 0,
) -> Optional["pygame.font.Font"]:
    """从本地 fonts/ 目录加载字体（返回 pygame.font.Font 或 None）。

    参数：
        size:       字号
        name:       字体别名 / 文件名 stem（如 "baocanmou"）；省略则用默认本地字体
        bold:       是否粗体（通过 set_bold 实现）
        face_index: .ttc 多字脸索引（默认 0）

    返回：
        pygame.font.Font 实例，或 None（未找到 / 加载失败）
    """
    try:
        import pygame
    except ImportError:
        raise ImportError("pygame 不可用，无法加载本地字体")

    path = _resolve_local_font_path(name)
    if path is None:
        return None

    cache_key = (str(path.resolve()), size, bold, face_index)
    if cache_key in _FONT_CACHE:
        return _FONT_CACHE[cache_key]  # type: ignore[return-value]

    font = _load_pygame_font_any(pygame, path, size, face_index)
    if font is not None and bold:
        try:
            font.set_bold(True)
        except Exception:
            pass
    if font is not None:
        _FONT_CACHE[cache_key] = font
    return font


def load_cjk_font(
    size: int,
    bold: bool = False,
    font_paths: Optional[List[str]] = None,
    name: Optional[str] = None,
    local_first: bool = False,
) -> "pygame.font.Font":
    """加载 CJK 字体（返回 pygame.Font）。

    搜索策略：
        1. ALLIN_FONT_PATH 环境变量（单个字体文件）
        2. name 指定的本地字体（若存在）
        3. local_first=True 时，包内 fonts/ 目录的所有本地字体
        4. 额外传入的 font_paths
        5. 平台系统字体目录
        6. pygame.font.SysFont 兜底
        7. pygame.font.Font(None) 最后兜底

    参数：
        size:        字号
        bold:        是否粗体
        font_paths:  额外的字体路径列表
        name:        指定字体别名 / 文件名（优先于系统字体）
        local_first: True 时优先使用包内 fonts/ 目录的本地字体

    返回：
        pygame.font.Font 实例

    Raises：
        ImportError: pygame 不可用
    """
    try:
        import pygame
    except ImportError:
        raise ImportError("pygame 不可用，无法加载字体")

    # 确保字体子系统已初始化（无显示环境下必要）
    try:
        pygame.font.init()
    except Exception:
        pass

    # 1. 环境变量
    env_path = os.environ.get("ALLIN_FONT_PATH", "")
    if env_path and os.path.exists(env_path):
        f = _try_load_pygame_font(pygame, env_path, size)
        if f is not None:
            return f

    # 2. 按 name 指定的本地 / 任意字体
    if name:
        named = _resolve_local_font_path(name)
        if named is not None and os.path.exists(str(named)):
            f = _try_load_pygame_font(pygame, str(named), size)
            if f is not None:
                return f

    # 收集搜索路径
    paths: List[str] = []

    # 3. 本地 fonts/ 目录（local_first 时优先）
    if local_first:
        _ensure_discovered()
        paths.extend(str(p) for p in _LOCAL_FONT_REGISTRY.values())

    # 4. 额外路径
    paths.extend(font_paths or [])

    # 5. 平台系统字体
    paths.extend(_get_platform_font_paths())

    # 粗体优先匹配
    if bold:
        bold_paths = [p for p in paths if "bd" in Path(p).stem.lower() or "bold" in p.lower()]
        paths = bold_paths + [p for p in paths if p not in bold_paths]

    for path in paths:
        if os.path.exists(path):
            font = _try_load_pygame_font(pygame, path, size)
            if font is not None:
                return font

    # 6. 兜底：SysFont
    try:
        return pygame.font.SysFont(
            "simhei" if sys.platform == "win32" else "notosanscjk", size, bold=bold
        )
    except Exception:
        pass

    # 7. 最后兜底
    return pygame.font.Font(None, size)


# ================================================================
#  Tkinter 字体加载
# ================================================================

def load_local_tk_font(
    size: int,
    name: Optional[str] = None,
    bold: bool = False,
) -> Optional["tkinter.font.Font"]:
    """从本地 fonts/ 目录加载字体（返回 tkinter.font.Font 或 None）。

    注意：tkinter 对 .woff/.woff2 支持有限，仅处理 .ttf/.ttc/.otf。
    需在一个 Tk 根窗口已存在的环境下调用（GUI 装配后）。

    参数：
        size: 字号
        name: 字体别名 / 文件名 stem；省略则用默认本地字体
        bold: 是否粗体

    返回：
        tkinter.font.Font 实例，或 None
    """
    import tkinter as tk  # noqa: F401
    import tkinter.font as tkfont

    path = _resolve_local_font_path(name)
    if path is None:
        return None
    ext = path.suffix.lower()
    if ext not in (".ttf", ".ttc", ".otf"):
        return None
    try:
        return tkfont.Font(
            file=str(path), size=size, weight="bold" if bold else "normal"
        )
    except Exception:
        return None


def load_cjk_tk_font(
    size: int,
    bold: bool = False,
    name: Optional[str] = None,
    local_first: bool = False,
) -> "tkinter.font.Font":
    """加载 CJK 字体（返回 tkinter.font.Font）。

    优先顺序：
        1. name 指定的本地字体（若存在）
        2. local_first=True 时包内 fonts/ 目录字体
        3. 平台字体系列（Microsoft YaHei / PingFang / Noto ...）
        4. tkinter 默认字体兜底

    参数：
        size:        字号
        bold:        是否粗体
        name:        指定字体别名 / 文件名
        local_first: True 时优先使用本地 fonts/ 目录字体

    返回：
        tkinter.font.Font 实例
    """
    import tkinter as tk
    import tkinter.font as tkfont

    # 1. 指定本地字体
    if name:
        lf = load_local_tk_font(size, name=name, bold=bold)
        if lf is not None:
            return lf

    # 2. 本地优先
    if local_first:
        lf = load_local_tk_font(size, bold=bold)
        if lf is not None:
            return lf

    # 3. 平台字体系列
    families = []
    if sys.platform == "win32":
        families = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong"]
    elif sys.platform == "darwin":
        families = ["PingFang SC", "STHeiti", "Heiti SC", "Hiragino Sans GB"]
    else:
        families = ["Noto Sans CJK", "WenQuanYi Micro Hei", "WenQuanYi Zen Hei", "Droid Sans"]

    weight = "bold" if bold else "normal"

    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        for family in families:
            font = tkfont.Font(family=family, size=size, weight=weight)
            actual = font.actual("family")
            if actual.lower() in [f.lower() for f in families]:
                return font
    except tk.TclError:
        pass
    finally:
        if root:
            try:
                root.destroy()
            except tk.TclError:
                pass

    # 4. 兜底
    return tkfont.Font(size=size, weight=weight)


# ================================================================
#  字体可用性检测
# ================================================================

def list_available_cjk_fonts() -> List[Tuple[str, bool]]:
    """列出可用 CJK 字体（含本地字体）。

    返回：
        [(路径, 是否存在), ...]
    """
    results: List[Tuple[str, bool]] = []

    env_path = os.environ.get("ALLIN_FONT_PATH", "")
    if env_path:
        results.append((env_path, os.path.exists(env_path)))

    for alias, p in list_local_fonts():
        results.append((f"{alias} @ {p}", os.path.exists(p)))

    for path in _get_platform_font_paths():
        results.append((path, os.path.exists(path)))

    return results


def is_cjk_supported(font_path: Optional[str] = None) -> bool:
    """检测指定字体（或默认字体）是否支持 CJK。

    参数：
        font_path: 字体路径；None=自动搜索

    返回：
        是否支持 CJK
    """
    try:
        import pygame
        if font_path and os.path.exists(font_path):
            font = pygame.font.Font(font_path, 16)
        elif font_path:
            return False
        else:
            font = load_cjk_font(16)
        font.render("中文", True, (255, 255, 255))
        return True
    except Exception:
        return False
