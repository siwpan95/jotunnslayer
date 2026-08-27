"""
事件总线 — 统一版本
=====================

融合 carimara_py 与 hell below 事件总线的核心能力：
- 递归保护、安全遍历、容错设计、调试日志
- 装饰器模式订阅、一次性监听 (once)
- EventTypes 事件类型常量类
- publish() 返回通知数量
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Set


# ─── 类型别名 ─────────────────────────────────────────

EventHandler = Callable[[Any], None]


# ─── 事件类型常量 ─────────────────────────────────────

class EventTypes:
    """
    事件类型常量 — 提供统一的字符串标识，避免硬编码拼写错误。

    用法：
        bus.subscribe(EventTypes.ROOM_ENTER, handler)
        bus.emit(EventTypes.ROOM_ENTER, data)
    """

    # ── 房间 / 地图 ──────────────────────────────────
    ROOM_ENTER: str = "room_enter"
    ROOM_EXIT: str = "room_exit"

    # ── 物品 ─────────────────────────────────────────
    ITEM_TAKE: str = "item_take"
    ITEM_DROP: str = "item_drop"
    ITEM_USE: str = "item_use"

    # ── 状态 / 剧情 ──────────────────────────────────
    FLAG_CHANGE: str = "flag_change"
    NARRATIVE_TRIGGER: str = "narrative"
    PUZZLE_SOLVED: str = "puzzle_solved"
    CHAPTER_CHANGE: str = "chapter_change"
    GAME_OVER: str = "game_over"

    # ── 故事 / 探索 ──────────────────────────────────
    IMAGERY_DISCOVER: str = "imagery_discover"
    BRANCH_TAKEN: str = "branch_taken"
    CHOICE_MADE: str = "choice_made"
    SHARD_FOUND: str = "shard_found"
    SHARD_HIDDEN: str = "shard_hidden"        # 自 dwarf_scrolls 回灌
    QUEST_COMPLETE: str = "quest_complete"    # 自 dwarf_scrolls 回灌
    DREAM_ENTER: str = "dream_enter"
    DREAM_EXIT: str = "dream_exit"

    # ── 战斗 ─────────────────────────────────────────
    COMBAT_START: str = "combat_start"
    COMBAT_END: str = "combat_end"
    CARD_PLAYED: str = "card_played"
    ENEMY_TURN: str = "enemy_turn"

    # ── 通用 ─────────────────────────────────────────
    ENTITY_CREATED: str = "entity_created"
    ENTITY_DESTROYED: str = "entity_destroyed"
    COMPONENT_ADDED: str = "component_added"
    COMPONENT_REMOVED: str = "component_removed"
    SYSTEM_ADDED: str = "system_added"
    SYSTEM_REMOVED: str = "system_removed"
    WORLD_CLEARED: str = "world_cleared"

    # ── 生存 / 沙盒游戏（来自《我的世界》实战沉淀） ──
    PLAYER_MOVED: str = "player_moved"           # 玩家移动 → 位置数据
    PLAYER_DIED: str = "player_died"             # 玩家死亡
    PLAYER_RESPAWNED: str = "player_respawned"   # 玩家重生
    MOB_SPAWNED: str = "mob_spawned"             # 生物生成 → mob_id
    MOB_DEFEATED: str = "mob_defeated"           # 生物被击败 → mob_id + drops
    ITEM_CRAFTED: str = "item_crafted"           # 合成完成 → item_id
    ITEM_SMELTED: str = "item_smelted"           # 熔炼完成 → item_id
    ITEM_EQUIPPED: str = "item_equipped"         # 装备物品 → item_id + slot
    ITEM_UNEQUIPPED: str = "item_unequipped"     # 卸下物品 → item_id + slot
    STATION_PLACED: str = "station_placed"       # 放置合成站 → station_type
    DIMENSION_CHANGED: str = "dimension_changed" # 维度切换 → from_dim + to_dim
    BIOME_CHANGED: str = "biome_changed"         # 群系切换 → from_biome + to_biome
    DAY_CHANGED: str = "day_changed"             # 日期变更 → day_number
    TIME_PHASE_CHANGED: str = "time_phase_changed"  # 时段变化 → phase
    HUNGER_CHANGED: str = "hunger_changed"       # 饥饿值变化 → old + new
    SHELTER_BUILT: str = "shelter_built"         # 建造庇护所
    PORTAL_ACTIVATED: str = "portal_activated"   # 激活传送门 → target_dimension
    BOSS_DEFEATED: str = "boss_defeated"         # Boss 被击败 → boss_id


# ─── 事件总线 ─────────────────────────────────────────

class EventBus:
    """
    事件总线 — 松耦合的系统间通信。

    核心特性：
        - 递归保护：检测并阻止事件循环爆炸
        - 安全遍历：复制监听器列表，支持动态订阅/取消订阅
        - 容错设计：单个回调失败不影响其他回调
        - 调试日志：可选记录所有事件发射历史
        - 装饰器模式：@bus.subscribe(event_type) 语法支持
        - 一次性监听：once() 自动取消订阅

    用法：
        bus = EventBus(debug=True)

        @bus.subscribe(EventTypes.ITEM_TAKE)
        def on_item_take(data):
            print(f"获得物品: {data}")

        bus.emit(EventTypes.ITEM_TAKE, {"name": "钥匙"})
        count = bus.publish(EventTypes.ITEM_TAKE, name="钥匙")
    """

    def __init__(self, debug: bool = False) -> None:
        """
        初始化事件总线。

        参数：
            debug: 是否启用事件日志（默认 False）
        """
        self.listeners: Dict[str, List[EventHandler]] = {}
        self.debug: bool = debug
        self._recursion_guard: Set[str] = set()
        self._max_recursion_depth: int = 5
        self._event_log: List[Dict[str, Any]] = []
        self._log_max_size: int = 1000

    # ── 订阅 / 取消订阅 ──────────────────────────────

    def subscribe(self, event_type: str, callback: Optional[EventHandler] = None):
        """
        订阅事件。支持两种用法：

        用法 1 - 直接调用：
            bus.subscribe("EVENT", handler)

        用法 2 - 装饰器：
            @bus.subscribe("EVENT")
            def handler(data):
                ...

        参数：
            event_type: 事件类型字符串
            callback: 事件处理函数（可选，用于装饰器模式）

        返回：
            装饰器或 callback 本身
        """
        if callback is None:
            # 装饰器模式
            def decorator(func: EventHandler) -> EventHandler:
                self.listeners.setdefault(event_type, []).append(func)
                return func
            return decorator

        # 直接调用模式
        self.listeners.setdefault(event_type, []).append(callback)
        return callback

    def once(self, event_type: str, callback: Optional[EventHandler] = None):
        """
        一次性监听 — 事件触发后自动取消订阅。

        用法 1 - 直接调用：
            bus.once("EVENT", handler)

        用法 2 - 装饰器：
            @bus.once("EVENT")
            def handler(data):
                ...

        参数：
            event_type: 事件类型字符串
            callback: 事件处理函数

        返回：
            装饰器或包装后的 callback
        """
        if callback is None:
            def decorator(func: EventHandler) -> EventHandler:
                def wrapper(data: Any) -> None:
                    func(data)
                    # wrapper 已在 listeners 中，手动移除
                    lst = self.listeners.get(event_type, [])
                    if wrapper in lst:
                        lst.remove(wrapper)
                    if not lst and event_type in self.listeners:
                        del self.listeners[event_type]
                self.listeners.setdefault(event_type, []).append(wrapper)
                return func  # 返回原始函数
            return decorator

        # 直接调用 — 包装为一次性
        def wrapper(data: Any) -> None:
            callback(data)
            lst = self.listeners.get(event_type, [])
            if wrapper in lst:
                lst.remove(wrapper)
            if not lst and event_type in self.listeners:
                del self.listeners[event_type]

        self.listeners.setdefault(event_type, []).append(wrapper)
        return callback  # type: ignore[return-value]

    def unsubscribe(self, event_type: str, callback: EventHandler) -> bool:
        """
        取消订阅。

        参数：
            event_type: 事件类型字符串
            callback: 要移除的回调函数

        返回：
            是否成功移除
        """
        if event_type in self.listeners:
            try:
                self.listeners[event_type].remove(callback)
                if not self.listeners[event_type]:
                    del self.listeners[event_type]
                return True
            except ValueError:
                pass  # 回调未注册
        return False

    # ── 事件发射 ──────────────────────────────────────

    def emit(self, event_type: str, data: Any = None) -> int:
        """
        发射事件 — 通知所有监听器。

        特性：
            - 复制监听器列表，支持动态修改
            - 单个回调失败不影响其他回调
            - 递归检测，防止事件死循环

        参数：
            event_type: 事件类型字符串
            data: 事件数据（任意类型，推荐 dict）

        返回：
            被通知的监听器数量
        """
        # 递归检测
        if event_type in self._recursion_guard:
            if self.debug:
                print(f"[EventBus] 递归检测: {event_type} 正在处理中，跳过")
            return 0

        # 记录日志
        if self.debug:
            self._log_event(event_type, data)

        # 安全复制监听器列表
        listeners = list(self.listeners.get(event_type, []))

        if not listeners:
            return 0

        # 入栈递归保护
        self._recursion_guard.add(event_type)

        count = 0
        try:
            for cb in listeners:
                try:
                    cb(data)
                    count += 1
                except Exception as e:
                    print(f"[EventBus] 事件 {event_type} 回调失败: {e}")
                    if self.debug:
                        import traceback
                        traceback.print_exc()
        finally:
            # 出栈递归保护
            self._recursion_guard.discard(event_type)

        return count

    def publish(self, event_type: str, **kwargs: Any) -> int:
        """
        以关键字参数形式发布事件，返回通知监听器数量。

        用法：
            count = bus.publish(EventTypes.ITEM_TAKE, item_name="钥匙", count=1)

        参数：
            event_type: 事件类型字符串
            **kwargs: 事件数据，以关键字参数形式传入

        返回：
            被通知的监听器数量
        """
        return self.emit(event_type, kwargs)

    # ── 分派模式（A3：emit / waterfall / serial）──────────
    #
    # 分派模式是事件的公开契约（Cordis 语义）：
    #   emit      —— 观察者模式，所有监听器各收到一次 data，无返回值（现有行为，不变）
    #   waterfall —— 中间件链：handler(value, next)，调用 next() 委托下游、可改写值、
    #                不调用 next 即短路；返回值沿链传播
    #   serial    —— 顺序投票：监听器依次执行，返回非 None 即短路并作为结果
    # 同一事件类型必须固定用一种模式订阅/分发。

    def waterfall(self, event_type: str, value: Any = None):
        """中间件链分发：监听器签名 handler(value, next)。

        - 调用 next(new_value) 把（可能改写的）值交给下一个监听器；
        - 不调用 next 即短路，当前返回值成为整条链的结果；
        - 无监听器时原样返回 value。

        用法（伤害结算示例）::

            @bus.subscribe("combat_damage")
            def double_damage(value, next):
                return next(value * 2)
        """
        listeners = list(self.listeners.get(event_type, []))

        def _dispatch(index: int, current: Any):
            if index >= len(listeners):
                return current
            handler = listeners[index]

            def _next(*new_value: Any):
                nxt = new_value[0] if new_value else current
                return _dispatch(index + 1, nxt)

            return handler(current, _next)

        return _dispatch(0, value)

    def serial(self, event_type: str, value: Any = None):
        """顺序投票分发：监听器签名 handler(value) -> 结果。

        返回非 None 的结果即短路并作为最终结果；全部返回 None 则结果为 None。

        用法（开门判定示例）::

            @bus.subscribe("can_pass")
            def locked_door(value):
                return "locked" if value.get("door") == "locked" else None
        """
        for handler in list(self.listeners.get(event_type, [])):
            result = handler(value)
            if result is not None:
                return result
        return None

    # ── 清除 ──────────────────────────────────────────

    def clear(self, event_type: Optional[str] = None) -> None:
        """
        清除监听器。

        参数：
            event_type: 指定事件类型（None 表示清除所有）
        """
        if event_type:
            self.listeners.pop(event_type, None)
        else:
            self.listeners.clear()

    # ── 查询 ──────────────────────────────────────────

    def has_listeners(self, event_type: str) -> bool:
        """检查是否有监听器订阅了指定事件。"""
        return event_type in self.listeners and len(self.listeners[event_type]) > 0

    def listener_count(self, event_type: str) -> int:
        """返回指定事件的监听器数量。"""
        return len(self.listeners.get(event_type, []))

    def total_listeners(self) -> int:
        """返回所有事件的监听器总数。"""
        return sum(len(v) for v in self.listeners.values())

    def registered_events(self) -> List[str]:
        """返回所有已注册的事件类型名称列表。"""
        return list(self.listeners.keys())

    # ── 调试日志 ──────────────────────────────────────

    def _log_event(self, event_type: str, data: Any) -> None:
        """记录事件到内部日志。"""
        entry: Dict[str, Any] = {
            "time": time.time(),
            "event_type": event_type,
            "data": repr(data) if data is not None else None,
        }
        self._event_log.append(entry)

        # 限制日志大小
        if len(self._event_log) > self._log_max_size:
            self._event_log = self._event_log[-self._log_max_size // 2:]

    def get_log(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取事件日志。

        参数：
            limit: 返回最后 N 条（None 返回全部）

        返回：
            日志记录列表
        """
        if limit is None:
            return self._event_log
        return self._event_log[-limit:]

    def clear_log(self) -> None:
        """清除事件日志。"""
        self._event_log.clear()

    def enable_debug(self) -> None:
        """启用调试日志。"""
        self.debug = True

    def disable_debug(self) -> None:
        """禁用调试日志。"""
        self.debug = False

    def __repr__(self) -> str:
        total = self.total_listeners()
        return f"EventBus({len(self.listeners)} events, {total} listeners)"
