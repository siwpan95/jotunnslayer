"""
存档系统 — 多槽位存档与自动存档管理。

支持 10 个手动槽位 (0-9) + 自动存档槽位。
支持版本兼容检查、Base64 编码选项（仅编码，非加密，不提供安全性）。
所有存档以 UTF-8 JSON 格式存储。

使用方式:

    mgr = SaveLoadManager("saves/")
    mgr.save(state, slot=0)
    state = mgr.load(slot=0)
    info = mgr.list_saves()
"""

from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------
# SaveSlotInfo
# ---------------------------------------------------------------

@dataclass
class SaveSlotInfo:
    """存档槽位信息（元数据）。"""
    slot: int
    timestamp: float = 0.0
    time_str: str = ""
    version: int = 0
    is_auto: bool = False

    @property
    def exists(self) -> bool:
        """该槽位是否存在有效存档。"""
        return self.timestamp > 0

    @property
    def readable_time(self) -> str:
        """可读的时间字符串。"""
        return self.time_str or "未知"

    @classmethod
    def from_save_data(cls, slot: int, data: dict, is_auto: bool = False) -> "SaveSlotInfo":
        """从存档数据构建槽位信息。"""
        return cls(
            slot=slot,
            timestamp=data.get("timestamp", 0.0),
            time_str=data.get("time_str", ""),
            version=data.get("version", 0),
            is_auto=is_auto,
        )


# ---------------------------------------------------------------
# SaveLoadManager
# ---------------------------------------------------------------

class SaveLoadManager:
    """统一存档管理器。

    特性：
    - 10 个手动槽位 (0-9) + 1 个自动存档槽位
    - save / load / auto_save / load_auto / delete
    - list_saves / get_slot_info
    - 版本兼容检查
    - Base64 编码加密选项（可选）

    使用方式:

        mgr = SaveLoadManager("saves/", version=1)
        mgr.save(game_state, slot=0)
        loaded = mgr.load(slot=0)
    """

    SAVE_PREFIX = "save_"
    AUTO_NAME = "autosave"
    EXT = ".json"
    MAX_SLOTS = 10

    def __init__(
        self,
        save_dir: str,
        version: int = 1,
        b64_encode: bool = False,
        logger: Any = None,
    ):
        """
        :param save_dir: 存档目录路径
        :param version: 存档格式版本号
        :param b64_encode: 是否启用 Base64 编码。**注意：这只是编码（便于单行存储），
                            并非加密，不提供任何安全性，切勿用于敏感数据。**
        :param logger: 可选的 Logger 实例
        """
        self.save_dir = save_dir
        self.version = version
        self.b64_encode = b64_encode
        self._logger = logger
        os.makedirs(save_dir, exist_ok=True)

    def _log(self, msg: str) -> None:
        """记录警告信息。"""
        if self._logger:
            self._logger.warning(f"[SaveLoad] {msg}")
        else:
            print(f"[SaveLoad] {msg}")

    # ---- 路径 ----

    def _slot_path(self, slot: int) -> str:
        """获取手动存档路径。"""
        return os.path.join(self.save_dir, f"{self.SAVE_PREFIX}{slot:02d}{self.EXT}")

    def _auto_path(self) -> str:
        """获取自动存档路径。"""
        return os.path.join(self.save_dir, f"{self.AUTO_NAME}{self.EXT}")

    # ---- 编码/解码 ----

    def _encode(self, data: dict) -> str:
        """将字典序列化为 JSON 字符串（可选 Base64）。"""
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        if self.b64_encode:
            json_bytes = json_str.encode("utf-8")
            return base64.b64encode(json_bytes).decode("ascii")
        return json_str

    def _decode(self, raw: str) -> Optional[dict]:
        """从文件内容反序列化为字典。"""
        try:
            if self.b64_encode and not raw.strip().startswith("{"):
                # Base64 编码的内容
                json_bytes = base64.b64decode(raw.strip())
                raw = json_bytes.decode("utf-8")
            return json.loads(raw)
        except (json.JSONDecodeError, base64.binascii.Error, ValueError) as e:
            self._log(f"解码失败: {e}")
            return None

    # ---- 保存 ----

    def save(self, state: Any, slot: int = 0) -> bool:
        """保存游戏到指定槽位 (0-9)。

        :param state: 游戏状态对象，需实现 to_dict() 方法
        :param slot: 槽位编号
        :returns: 是否保存成功
        """
        if not 0 <= slot < self.MAX_SLOTS:
            self._log(f"无效槽位: {slot}")
            return False
        return self._write_save(self._slot_path(slot), state)

    def auto_save(self, state: Any) -> bool:
        """自动存档。

        :param state: 游戏状态对象
        :returns: 是否保存成功
        """
        return self._write_save(self._auto_path(), state)

    def _write_save(self, path: str, state: Any) -> bool:
        """内部：写入存档文件。"""
        try:
            data = {
                "version": self.version,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "state_data": state.to_dict() if hasattr(state, "to_dict") else state,
            }
            encoded = self._encode(data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(encoded)
            return True
        except (OSError, TypeError, AttributeError) as e:
            self._log(f"保存失败: {e}")
            return False

    # ---- 加载 ----

    def load(self, slot: int = 0) -> Optional[Any]:
        """从指定槽位加载。

        :param slot: 槽位编号
        :returns: 状态数据字典或 None
        """
        if not 0 <= slot < self.MAX_SLOTS:
            return None
        return self._read_save(self._slot_path(slot))

    def load_auto(self) -> Optional[Any]:
        """加载自动存档。"""
        return self._read_save(self._auto_path())

    def _read_save(self, path: str) -> Optional[Any]:
        """内部：读取存档文件。"""
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = self._decode(raw)
            if data is None:
                return None
            # 版本兼容检查
            file_version = data.get("version", 0)
            if file_version != self.version:
                self._log(
                    f"版本不匹配: 文件 v{file_version}，"
                    f"当前 v{self.version}"
                )
            return data.get("state_data", data)
        except OSError as e:
            self._log(f"读取失败: {e}")
            return None

    # ---- 快照 + 日志增量模式（P3：日志即事实源） ----

    def save_with_log(self, state: Any, slot: int = 0, log: Any = None) -> bool:
        """存档 = 快照 + 日志偏移：快照写入存档文件，日志另行落盘。

        :param state: 游戏状态对象（需 to_dict()）
        :param slot: 槽位编号
        :param log: WorldLog 实例（可选；提供则把当前 seq 记为 log_offset，
                    并把日志写入同名 .log 文件）
        :returns: 是否保存成功
        """
        path = self._slot_path(slot)
        try:
            data = {
                "version": self.version,
                "timestamp": time.time(),
                "time_str": time.strftime("%Y-%m-%d %H:%M:%S"),
                "state_data": state.to_dict() if hasattr(state, "to_dict") else state,
                "mode": "snapshot+log",
                "log_offset": getattr(log, "seq", 0),
            }
            encoded = self._encode(data)
            with open(path, "w", encoding="utf-8") as f:
                f.write(encoded)
            if log is not None and hasattr(log, "save_to"):
                log.save_to(path + ".log")
            return True
        except (OSError, TypeError, AttributeError) as e:
            self._log(f"保存失败: {e}")
            return False

    def load_with_log(self, slot: int = 0, log: Any = None) -> Optional[dict]:
        """读取快照+日志存档，返回 dict：{snapshot, log_offset, events_after}。

        events_after 为快照之后的世界事实事件（可供投影折叠重建状态）。
        旧格式存档（无 mode 字段）照常返回 {"snapshot": ..., "log_offset": 0, "events_after": []}。
        """
        path = self._slot_path(slot)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = self._decode(raw)
        except OSError:
            return None
        if data is None:
            return None
        snapshot = data.get("state_data", data)
        offset = int(data.get("log_offset", 0))
        events_after: list = []
        if data.get("mode") == "snapshot+log" and log is not None:
            log_path = path + ".log"
            if os.path.exists(log_path) and hasattr(log, "load_from"):
                try:
                    loaded = log.load_from(log_path)
                    events_after = loaded.entries_since(offset)
                except (OSError, ValueError):
                    events_after = []
        return {"snapshot": snapshot, "log_offset": offset, "events_after": events_after}

    # ---- 删除 ----

    def delete(self, slot: int) -> bool:
        """删除指定槽位的存档。

        :param slot: 槽位编号
        :returns: 是否成功删除
        """
        if not 0 <= slot < self.MAX_SLOTS:
            return False
        path = self._slot_path(slot)
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False

    def delete_auto(self) -> bool:
        """删除自动存档。"""
        path = self._auto_path()
        if os.path.exists(path):
            try:
                os.remove(path)
                return True
            except OSError:
                return False
        return False

    # ---- 查询 ----

    def get_slot_info(self, slot: int) -> Optional[SaveSlotInfo]:
        """获取槽位的存档信息。

        :returns: SaveSlotInfo 或 None（槽位无效或空）
        """
        if not 0 <= slot < self.MAX_SLOTS:
            return None
        return self._read_slot_info(self._slot_path(slot), slot, is_auto=False)

    def get_auto_info(self) -> Optional[SaveSlotInfo]:
        """获取自动存档信息。"""
        return self._read_slot_info(self._auto_path(), -1, is_auto=True)

    def _read_slot_info(self, path: str, slot: int, is_auto: bool = False) -> Optional[SaveSlotInfo]:
        """读取单个存档文件的元信息。"""
        if not os.path.exists(path):
            return SaveSlotInfo(slot=slot, is_auto=is_auto)
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
            data = self._decode(raw)
            if data is None:
                return None
            return SaveSlotInfo.from_save_data(slot, data, is_auto)
        except OSError:
            return None

    def list_saves(self) -> list[SaveSlotInfo]:
        """列出所有有效存档（含自动存档）。"""
        saves: list[SaveSlotInfo] = []

        # 自动存档
        auto_info = self.get_auto_info()
        if auto_info and auto_info.exists:
            saves.append(auto_info)

        # 手动槽位
        for i in range(self.MAX_SLOTS):
            info = self.get_slot_info(i)
            if info and info.exists:
                saves.append(info)

        # 按时间降序排列
        saves.sort(key=lambda s: s.timestamp, reverse=True)
        return saves

    def has_saves(self) -> bool:
        """是否存在任何存档。"""
        return len(self.list_saves()) > 0

    def get_latest_save(self) -> Optional[SaveSlotInfo]:
        """获取最新的存档信息。"""
        saves = self.list_saves()
        return saves[0] if saves else None

    def get_latest_state(self) -> Optional[Any]:
        """加载最新的存档状态。"""
        latest = self.get_latest_save()
        if latest is None:
            return None
        if latest.is_auto:
            return self.load_auto()
        return self.load(latest.slot)
