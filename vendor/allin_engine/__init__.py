"""
兼容 shim：allin_engine → alloy（引擎改名过渡期，2026-08-23）。
把旧名导入重定向到本项目的 alloy 内联副本，模块身份保持一致。
"""
from __future__ import annotations
import importlib, importlib.util, sys, warnings

_PREFIX, _REAL = "allin_engine", "alloy"

warnings.warn(
    f"'{_PREFIX}' 已改名为 '{_REAL}'，请迁移导入。",
    DeprecationWarning, stacklevel=2)

class _L:
    def __init__(self, real): self._real = real
    def create_module(self, spec):
        m = importlib.import_module(self._real)
        sys.modules[spec.name] = m
        return m
    def exec_module(self, module): pass

class _F:
    def find_spec(self, fullname, path=None, target=None):
        if fullname != _PREFIX and not fullname.startswith(_PREFIX + "."):
            return None
        real = _REAL + fullname[len(_PREFIX):]
        if real in sys.modules:
            return importlib.util.spec_from_loader(fullname, _L(real))
        try:
            rs = importlib.util.find_spec(real)
        except (ImportError, AttributeError, ValueError):
            return None
        if rs is None:
            return None
        # 不带 origin/submodule_search_locations：子模块同样由本 finder 拦截。
        return importlib.util.spec_from_loader(fullname, _L(real))

if not any(isinstance(f, _F) for f in sys.meta_path):
    sys.meta_path.insert(0, _F())
try:
    sys.modules[__name__] = importlib.import_module(_REAL)
except Exception:
    pass
