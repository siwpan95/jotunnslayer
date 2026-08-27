# -*- coding: utf-8 -*-
"""Meta 存档 + 金币（Phase 6 核心子集）。

save.json 结构（version=1，字段随版本演进，旧档缺字段走默认值）：
    gold      累计金币（跨局货币，供 Phase 6 技能树消费）
    best_run  历史最佳一局 {level, kills, time}
    stats     终身统计 {runs, wins, total_kills, total_damage}
    settings  全局设置 {sfx_vol, music_vol}

底层文件读写借用 vendored SaveLoadManager（多槽位/版本字段/元数据），
本模块只负责 schema 定义与默认值迁移。
"""
import os
from dataclasses import dataclass, field

from vendor.alloy.core.serializable import Serializable
from vendor.alloy.systems.save_load import SaveLoadManager

SAVE_VERSION = 1
SLOT = 0

DEFAULT_SETTINGS = dict(sfx_vol=0.8, music_vol=0.5)


@dataclass
class BestRun(Serializable):
    level: int = 1
    kills: int = 0
    time: float = 0.0


@dataclass
class Stats(Serializable):
    runs: int = 0
    wins: int = 0
    total_kills: int = 0
    total_damage: int = 0


@dataclass
class SaveData(Serializable):
    gold: int = 0
    best_run: BestRun = field(default_factory=BestRun)
    stats: Stats = field(default_factory=Stats)
    settings: dict = field(default_factory=lambda: dict(DEFAULT_SETTINGS))
    # 跨局技能树（Phase 6 剩余）：{char/god: [各节点等级]}
    char_levels: dict = field(default_factory=dict)
    god_levels: dict = field(default_factory=dict)


def save_dir() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "saves")


_mgr = None


def manager() -> SaveLoadManager:
    global _mgr
    if _mgr is None:
        _mgr = SaveLoadManager(save_dir(), version=SAVE_VERSION)
    return _mgr


def load_data() -> SaveData:
    """读取存档；缺失/损坏/版本不符一律回退全新默认档。"""
    raw = manager().load(slot=SLOT)
    if not isinstance(raw, dict):
        return SaveData()
    try:
        sd = SaveData.from_dict(raw)
        # 旧档缺字段防御（Serializable 对 default_factory 缺失字段返回 None）
        if not isinstance(sd.best_run, BestRun):
            sd.best_run = BestRun()
        if not isinstance(sd.stats, Stats):
            sd.stats = Stats()
        if not isinstance(sd.settings, dict):
            sd.settings = dict(DEFAULT_SETTINGS)
        for k, v in DEFAULT_SETTINGS.items():
            sd.settings.setdefault(k, v)
        if not isinstance(sd.char_levels, dict):
            sd.char_levels = {}
        if not isinstance(sd.god_levels, dict):
            sd.god_levels = {}
        return sd
    except Exception:
        return SaveData()


def save_data(sd: SaveData) -> bool:
    return manager().save(sd, slot=SLOT)
