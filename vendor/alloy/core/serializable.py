"""
Serializable / Snapshotable — 为 dataclass 提供通用 to_dict() / from_dict() 支持，
以及为需要运行时依赖重建的领域对象提供 to_snapshot() / from_snapshot() 模式。

Serializable 子类只需标记需要特殊处理的字段，即可自动序列化/反序列化。

使用方式：

    from core.serializable import Serializable

    @dataclass
    class MyData(Serializable):
        name: str
        value: int = 0

        # 需要自定义序列化的字段在此覆盖
        def _to_dict_extra(self, d: dict) -> dict:
            d["custom"] = self._serialize_custom()
            return d

        @classmethod
        def _from_dict_extra(cls, data: dict) -> dict:
            data["custom_val"] = cls._deserialize_custom(data.get("custom"))
            return data
"""

from __future__ import annotations

import dataclasses
import typing
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T", bound="Serializable")

# 类型注解解析缓存：避免每次反序列化都重新 get_type_hints
_HINTS_CACHE: dict[type, dict] = {}


def _get_type_hints(cls: type) -> dict:
    """解析类的真实类型注解（缓存结果）。

    修复 ``from __future__ import annotations`` 下 ``field.type`` 退化为字符串，
    导致嵌套 dataclass / ``list[Dataclass]`` 反序列化失效的问题。

    解析失败（前向引用无法解析等）时返回空 dict，回退到字符串注解，保持既有行为。
    """
    if cls not in _HINTS_CACHE:
        try:
            _HINTS_CACHE[cls] = typing.get_type_hints(cls)
        except Exception:
            _HINTS_CACHE[cls] = {}
    return _HINTS_CACHE[cls]


class Serializable:
    """为 dataclass 子类提供通用序列化能力。

    基于 dataclasses.fields() 自动收集字段值。
    特殊类型（Enum）自动处理，嵌套对象调用其 to_dict()/from_dict()。

    子类可覆盖：
        _to_dict_extra(d: dict) -> dict   — 在 to_dict() 末尾添加自定义逻辑
        _from_dict_extra(data: dict) -> dict — 在 from_dict() 开头预处理数据
        _serialize_field_value(name, value) -> Any — 自定义单个字段的序列化
        _deserialize_field_value(field, value) -> Any — 自定义单个字段的反序列化
    """

    def to_dict(self) -> dict[str, Any]:
        """基于 dataclass 字段自动序列化为字典。"""
        d: dict[str, Any] = {}
        for f in dataclasses.fields(self):
            val = getattr(self, f.name)
            d[f.name] = self._serialize_field_value(f.name, val)
        return self._to_dict_extra(d)

    @classmethod
    def from_dict(cls: type[T], data: dict[str, Any]) -> T:
        """从字典反序列化（基于 dataclass 字段）。

        通过 typing.get_type_hints 解析字段真实类型，修复
        ``from __future__ import annotations`` 下 ``field.type`` 为字符串、
        导致嵌套 dataclass / ``list[Dataclass]`` 无法正确反序列化的问题。
        """
        data = cls._from_dict_extra(data)
        field_map = {f.name: f for f in dataclasses.fields(cls)}
        hints = _get_type_hints(cls)
        kwargs: dict[str, Any] = {}
        for fname, fdef in field_map.items():
            raw = data.get(fname)
            ftype = hints.get(fname, fdef.type)
            kwargs[fname] = cls._deserialize_field_value(ftype, fdef, raw)
        return cls(**kwargs)

    # ── 可覆盖的钩子 ──

    def _to_dict_extra(self, d: dict[str, Any]) -> dict[str, Any]:
        """子类覆盖以添加额外序列化逻辑。"""
        return d

    @classmethod
    def _from_dict_extra(cls, data: dict[str, Any]) -> dict[str, Any]:
        """子类覆盖以预处理反序列化数据。"""
        return data

    @staticmethod
    def _serialize_field_value(name: str, val: Any) -> Any:
        """序列化单个字段值。"""
        if val is None:
            return None
        if isinstance(val, Enum):
            return val.value
        if hasattr(val, "to_dict"):
            return val.to_dict()
        if isinstance(val, list):
            return [
                item.to_dict() if hasattr(item, "to_dict")
                else item.value if isinstance(item, Enum)
                else item
                for item in val
            ]
        return val

    @staticmethod
    def _deserialize_field_value(ftype: Any, field_def: dataclasses.Field, raw: Any) -> Any:
        """反序列化单个字段值（子类可覆盖以处理特殊类型）。

        :param ftype: 经 get_type_hints 解析后的真实类型（失败时为字符串注解回退值）
        :param field_def: dataclass 字段定义（用于读取默认值）
        :param raw: 原始数据
        """
        if raw is None:
            default = field_def.default
            return None if default is dataclasses.MISSING else default
        # 如果字段类型是 dataclass 且有 from_dict
        if hasattr(ftype, "from_dict") and isinstance(raw, dict):
            return ftype.from_dict(raw)
        # 如果字段类型是 list[SomeDataclass]
        if _is_list_of_serializable(ftype) and isinstance(raw, list):
            item_type = _extract_list_item_type(ftype)
            if item_type and hasattr(item_type, "from_dict"):
                return [item_type.from_dict(i) if isinstance(i, dict) else i for i in raw]
        return raw


def _is_list_of_serializable(type_hint: Any) -> bool:
    """检查类型注解是否为 list[SomeSerializable]。"""
    origin = getattr(type_hint, "__origin__", None)
    return origin is list


def _extract_list_item_type(type_hint: Any) -> Any:
    """从 list[T] 中提取 T。"""
    args = getattr(type_hint, "__args__", None)
    if args:
        return args[0]
    return None


# ─────────────────────────────────────────────────────────────────────────
# Snapshotable — 需要运行时依赖重建的领域对象快照接口
# （自 dwarf_scrolls 内联副本回灌：P2 双副本整合"保留最新版"）
# ─────────────────────────────────────────────────────────────────────────

S = TypeVar("S", bound="Snapshotable")


class Snapshotable:
    """为需要运行时依赖重建的领域对象提供快照/还原模式。

    与 Serializable 的区别：
      - Serializable 基于 dataclass 自动序列化字段；适用于简单数据容器。
      - Snapshotable 为手动实现的快照接口；适用于需要在重建时传入运行时依赖
        （如 world, player, registry, event_bus 等）的领域对象。

    子类必须实现：
        to_snapshot(self) -> dict
        from_snapshot(cls, data: dict, **deps) -> Snapshotable   (classmethod)
    """

    def to_snapshot(self) -> dict[str, Any]:
        """返回对象当前运行态的可序列化快照 dict。

        子类必须覆盖此方法，返回仅含标量/列表/dict 的快照数据，
        确保 json.dumps() 可直接序列化。
        """
        raise NotImplementedError(
            f"{type(self).__name__} 必须实现 to_snapshot()")

    @classmethod
    def from_snapshot(cls: type[S], data: dict[str, Any], **deps: Any) -> S:
        """由快照 dict + 运行时依赖重建对象。

        子类必须覆盖此方法。**deps 用于传入运行时依赖
        （如 world, player, registry, event_bus 等），
        这些依赖不在快照中持久化，而是由调用方提供。
        """
        raise NotImplementedError(
            f"{cls.__name__} 必须实现 from_snapshot(data, **deps)")
