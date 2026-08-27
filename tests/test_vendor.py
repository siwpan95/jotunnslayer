# -*- coding: utf-8 -*-
"""定向验证：vendored alloy 子集（音频合成/存档/事件总线/CJK 字体）。

无头运行，覆盖四个冒烟点：
  1. synth 合成波形 -> pygame.Sound（dummy 音频驱动）
  2. SaveLoadManager 存档 roundtrip + 版本字段
  3. EventBus 订阅/一次性/取消
  4. 本地 CJK 字体加载并渲染中文
"""
import os
import sys

# 从项目根执行 python tests\xxx.py 时，把根目录加进 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pygame
import pygame.sndarray

from vendor.alloy.audio.synth import (
    SynthVoice, synthesize_voice, OscType, EnvShape, SR,
)
from vendor.alloy.audio.music_gen import generate_music_wav, PRESETS
from vendor.alloy.core.event_bus import EventBus
from vendor.alloy.core.serializable import Serializable
from vendor.alloy.systems.save_load import SaveLoadManager
from vendor.alloy.utils.font import load_local_font


def test_synth():
    v = SynthVoice(freq=220.0, osc_type=OscType.SAW, duration=0.15,
                   env_shape=EnvShape.PERCUSSIVE, volume=0.8)
    sig = synthesize_voice(v)
    assert len(sig) > 0 and sig.dtype == np.float32
    assert float(np.max(np.abs(sig))) <= 1.0
    pygame.init()
    pygame.mixer.init(frequency=SR, size=-16, channels=8, buffer=1024)
    i16 = np.clip(sig * 32767, -32768, 32767).astype(np.int16)
    stereo = np.column_stack((i16, i16))
    snd = pygame.sndarray.make_sound(stereo)
    assert snd.get_length() > 0.0
    print("PASS 合成波形 -> pygame.Sound")


def test_music():
    out = os.path.join(tempfile.gettempdir(), "vendor_smoke_bgm.wav")
    p = generate_music_wav(PRESETS["battle"], out, duration_sec=2.0)
    assert os.path.exists(p) and os.path.getsize(p) > 1000
    os.remove(p)
    print("PASS BGM 预设渲染 WAV")


def test_save():
    from dataclasses import dataclass, field

    @dataclass
    class SaveData(Serializable):
        gold: int = 0
        best_level: int = 1
        runs: int = 0
        flags: list = field(default_factory=list)

    d = tempfile.mkdtemp()
    mgr = SaveLoadManager(d, version=1)
    s = SaveData(gold=777, best_level=42, runs=5, flags=["a", "b"])
    assert mgr.save(s, slot=0)
    raw = open(os.path.join(d, "save_00.json"), encoding="utf-8").read()
    assert '"version": 1' in raw
    got = mgr.load(slot=0)
    assert isinstance(got, dict) and got["gold"] == 777 and got["best_level"] == 42
    assert got["flags"] == ["a", "b"]
    print("PASS 存档 roundtrip + version 字段")


def test_bus():
    bus = EventBus()
    hits = []
    bus.subscribe("kill", lambda d: hits.append(d))
    bus.subscribe("kill", lambda d: hits.append("again"))
    bus.emit("kill", {"n": 1})
    assert hits == [{"n": 1}, "again"]
    once = []
    bus.once("levelup", lambda d: once.append(d))
    bus.emit("levelup", 3)
    bus.emit("levelup", 4)
    assert once == [3]
    assert bus.publish("none", data=0) == 0
    print("PASS 事件总线 订阅/一次性/计数")


def test_font():
    pygame.init()
    pygame.font.init()
    f = load_local_font(26)
    assert f is not None
    surf = f.render("巨人之怒", True, (255, 255, 255))
    assert surf.get_width() > 20 and surf.get_height() > 10
    print("PASS 本地 CJK 字体渲染中文")


if __name__ == "__main__":
    test_synth()
    test_music()
    test_save()
    test_bus()
    test_font()
    print("VENDOR_TEST_OK")
