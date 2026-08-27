# -*- coding: utf-8 -*-
"""程序化音频：8-bit 音效 + 场景 BGM（Phase 8 核心，零外部资源）。

- 音效：vendored synth 合成，init() 时写 WAV 缓存到 %TEMP%/jotunnslayer_audio，
  运行时经 AudioSystem 的 Sound 缓存播放
- BGM：vendored music_gen 六预设 + 本地变奏（战斗 60s 加速版 / 战败挽歌），
  首次切换该轨道时渲染 WAV（scipy 写盘），之后直接复用
- 全部接口在未初始化（无音频设备 / 未调用 init）时静默 no-op，
  无头测试与 SMOKE（dummy 音频驱动）不受影响
"""
import os
import tempfile
import time
import wave
from dataclasses import replace

import numpy as np

from vendor.alloy.audio.audio_system import AudioSystem
from vendor.alloy.audio.synth import (
    SynthVoice, synthesize_voice, OscType, EnvShape, SR,
)
from vendor.alloy.audio.music_gen import generate_music_wav, PRESETS

_audio = None          # AudioSystem 单例；None = 不可用/未初始化
_sfx = {}              # name -> WAV 路径
_bgm_files = {}        # 轨道名 -> WAV 路径（懒渲染缓存）
_cur_bgm = None        # 当前 BGM 轨道
_last_play = {}        # 事件音效节流表


def cache_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "jotunnslayer_audio")


def _write_wav(path, arr):
    """float32 [-1,1] 波形写单声道 16-bit WAV（标准库，不依赖 scipy）。"""
    i16 = np.clip(arr * 32767, -32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(i16.tobytes())


# ================================================================ 音效配方
def _tone(freq, osc, dur, vol=0.4, shape=EnvShape.PERCUSSIVE, harmonics=None):
    v = SynthVoice(freq=freq, osc_type=osc, duration=dur, volume=vol,
                   env_shape=shape)
    if harmonics:
        v.harmonics = harmonics
    return synthesize_voice(v)


def _seq(*parts):
    return np.concatenate(parts)


def build_sfx():
    return {
        "hit":       _tone(180, OscType.SQUARE, 0.07, 0.30),
        "hurt":      _tone(220, OscType.SQUARE, 0.14, 0.42, harmonics=[(2.0, 0.4)]),
        "explode":   _tone(0, OscType.NOISE_BROWN, 0.5, 0.75),
        "thunder":   _seq(_tone(0, OscType.NOISE_BROWN, 0.4, 0.7),
                          _tone(55, OscType.SAW, 0.5, 0.5, harmonics=[(2.0, 0.3)])),
        "frost":     _tone(1180, OscType.SINE, 0.32, 0.3, shape=EnvShape.PLUCK,
                           harmonics=[(2.0, 0.35)]),
        "shield":    _tone(540, OscType.SQUARE, 0.16, 0.4),
        "shrine":    _tone(660, OscType.TRIANGLE, 0.35, 0.42, shape=EnvShape.PAD,
                           harmonics=[(2.0, 0.3)]),
        "boon":      _seq(_tone(523, OscType.TRIANGLE, 0.1, 0.4),
                          _tone(659, OscType.TRIANGLE, 0.1, 0.4),
                          _tone(784, OscType.TRIANGLE, 0.22, 0.4)),
        "favor":     _seq(_tone(523, OscType.SQUARE, 0.09, 0.45),
                          _tone(659, OscType.SQUARE, 0.09, 0.45),
                          _tone(784, OscType.SQUARE, 0.09, 0.45),
                          _tone(1046, OscType.SQUARE, 0.3, 0.5)),
        "combo10":   _tone(392, OscType.SQUARE, 0.09, 0.4),
        "combo25":   _seq(_tone(392, OscType.SQUARE, 0.08, 0.4),
                          _tone(494, OscType.SQUARE, 0.1, 0.4)),
        "combo50":   _seq(_tone(392, OscType.SQUARE, 0.07, 0.42),
                          _tone(494, OscType.SQUARE, 0.07, 0.42),
                          _tone(587, OscType.SQUARE, 0.12, 0.45)),
        "combo100":  _seq(_tone(392, OscType.SQUARE, 0.06, 0.45),
                          _tone(494, OscType.SQUARE, 0.06, 0.45),
                          _tone(587, OscType.SQUARE, 0.06, 0.45),
                          _tone(784, OscType.SQUARE, 0.22, 0.5)),
        "levelup":   _seq(_tone(523, OscType.TRIANGLE, 0.09, 0.45),
                          _tone(784, OscType.TRIANGLE, 0.16, 0.45)),
        "newweapon": _seq(_tone(440, OscType.TRIANGLE, 0.08, 0.4),
                          _tone(587, OscType.TRIANGLE, 0.08, 0.4),
                          _tone(740, OscType.TRIANGLE, 0.14, 0.4)),
        "evo":       _seq(_tone(392, OscType.SQUARE, 0.07, 0.45),
                          _tone(523, OscType.SQUARE, 0.07, 0.45),
                          _tone(659, OscType.SQUARE, 0.07, 0.45),
                          _tone(784, OscType.SQUARE, 0.07, 0.45),
                          _tone(1046, OscType.SQUARE, 0.3, 0.5)),
        "gold":      _tone(1568, OscType.SINE, 0.06, 0.22, shape=EnvShape.PLUCK),
        "food":      _seq(_tone(659, OscType.SINE, 0.07, 0.3, shape=EnvShape.PLUCK),
                          _tone(988, OscType.SINE, 0.1, 0.3, shape=EnvShape.PLUCK)),
        "chest":     _seq(_tone(523, OscType.TRIANGLE, 0.08, 0.4),
                          _tone(659, OscType.TRIANGLE, 0.08, 0.4),
                          _tone(784, OscType.TRIANGLE, 0.16, 0.4)),
        "death":     _seq(_tone(220, OscType.SAW, 0.3, 0.5, shape=EnvShape.PAD),
                          _tone(165, OscType.SAW, 0.35, 0.5, shape=EnvShape.PAD),
                          _tone(110, OscType.SAW, 0.6, 0.55, shape=EnvShape.PAD)),
        "boss_roar": _seq(_tone(0, OscType.NOISE_BROWN, 0.55, 0.7),
                          _tone(48, OscType.SAW, 0.7, 0.6,
                                harmonics=[(2.0, 0.4), (3.0, 0.2)])),
        "victory":   _seq(_tone(523, OscType.TRIANGLE, 0.14, 0.5),
                          _tone(659, OscType.TRIANGLE, 0.14, 0.5),
                          _tone(784, OscType.TRIANGLE, 0.14, 0.5),
                          _tone(1046, OscType.TRIANGLE, 0.5, 0.55)),
    }


# ================================================================ BGM 轨道
BATTLE_FAST = replace(PRESETS["battle"], name="battle_fast", bpm=134,
                      volume=0.17, osc_type=OscType.SQUARE)
DEFEAT = replace(PRESETS["menu"], name="defeat", bpm=58, volume=0.13)
BGMS = {
    "menu": PRESETS["menu"],
    "battle": PRESETS["battle"],
    "battle_fast": BATTLE_FAST,       # 战斗 60s 后的激昂变奏（ROADMAP Phase 8）
    "boss": PRESETS["boss"],
    "victory": PRESETS["victory"],
    "defeat": DEFEAT,
}
_BGM_SECS = {"menu": 36, "battle": 40, "battle_fast": 40,
             "boss": 32, "victory": 24, "defeat": 30}


# ================================================================ 初始化
def init(settings=None):
    """初始化 mixer + 合成音效缓存。返回是否可用。"""
    global _audio, _sfx
    if _audio is not None:
        return _audio.is_available
    settings = settings or {}
    try:
        _audio = AudioSystem(sample_rate=SR, channels=12, buffer=1024)
    except Exception:
        _audio = None
        return False
    if not _audio.is_available:
        _audio = None
        return False
    d = cache_dir()
    os.makedirs(d, exist_ok=True)
    try:
        for name, arr in build_sfx().items():
            p = os.path.join(d, f"sfx_{name}.wav")
            if not os.path.exists(p):
                _write_wav(p, arr)
            _sfx[name] = p
    except Exception:
        _sfx = {}
    _audio.set_sfx_volume(float(settings.get("sfx_vol", 0.8)))
    _audio.set_bgm_volume(float(settings.get("music_vol", 0.5)))
    return True


def is_available() -> bool:
    return _audio is not None and _audio.is_available


def set_volumes(sfx=None, music=None):
    if _audio is None:
        return
    if sfx is not None:
        _audio.set_sfx_volume(max(0.0, min(1.0, float(sfx))))
    if music is not None:
        _audio.set_bgm_volume(max(0.0, min(1.0, float(music))))


# ================================================================ 播放
def play(name, volume=1.0):
    """播放音效（未初始化则 no-op）。"""
    if _audio is None:
        return
    path = _sfx.get(name)
    if path:
        _audio.play_sfx(path, volume=volume)


def _throttled(name, min_interval):
    """高频事件音效节流（避免尸潮击杀刷爆混音器）。"""
    now = time.monotonic()
    if now - _last_play.get(name, 0.0) < min_interval:
        return
    _last_play[name] = now
    play(name)


def _bgm_path(name):
    """懒渲染 BGM WAV（首次切换该轨道时合成，之后缓存复用）。"""
    if name in _bgm_files:
        return _bgm_files[name]
    d = cache_dir()
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"bgm_{name}.wav")
    if not os.path.exists(p):
        try:
            generate_music_wav(BGMS[name], p,
                               duration_sec=_BGM_SECS.get(name, 32))
        except Exception:
            _bgm_files[name] = None
            return None
    _bgm_files[name] = p
    return p


def update_bgm(game):
    """每帧调用：按游戏状态切换 BGM 轨道（标题/战斗/60s 变奏/Boss/结算）。"""
    global _cur_bgm
    if _audio is None or not _audio.is_available:
        return
    name = None
    if game.state == "title":
        name = "menu"
    elif game.state == "play":
        if game.boss is not None:
            name = "boss"
        elif game.time >= 60.0:
            name = "battle_fast"
        else:
            name = "battle"
    elif game.state == "gameover":
        name = "victory" if game.victory else "defeat"
    if name and name != _cur_bgm:
        p = _bgm_path(name)
        if p and _audio.play_bgm(p):
            _cur_bgm = name


# ================================================================ 事件订阅
def _on_kill(d):
    _throttled("hit", 0.07)


def _on_combo_tier(d):
    play(f"combo{d['tier']}")


def _on_gold(d):
    if d["amount"] >= 10:
        _throttled("gold", 0.08)


def _on_levelup(d):
    play("levelup")


def _on_hurt(d):
    play("hurt")


def _on_shrine(d):
    play("shrine")


def _on_reroll(d):
    play("shrine", 0.7)


def _on_boon(d):
    play("favor" if d["favor_on"] else "boon")


def _on_new(d):
    play("newweapon")


def _on_evo(d):
    play("evo")


def _on_bossspawn(d):
    play("boss_roar")


def _on_bosskill(d):
    play("explode")


def _on_death(d):
    play("death")


def _on_gameover(d):
    # 战败时 player_death 已播死亡音，这里只补胜利号角
    if d["victory"]:
        play("victory")


def attach(bus):
    """订阅游戏事件（bus 跨 reset 存活，只需 attach 一次）。"""
    bus.subscribe("kill", _on_kill)
    bus.subscribe("combo_tier", _on_combo_tier)
    bus.subscribe("gold_gain", _on_gold)
    bus.subscribe("level_up", _on_levelup)
    bus.subscribe("player_hurt", _on_hurt)
    bus.subscribe("shrine_open", _on_shrine)
    bus.subscribe("boon_reroll", _on_reroll)
    bus.subscribe("boon_taken", _on_boon)
    bus.subscribe("weapon_new", _on_new)
    bus.subscribe("weapon_evo", _on_evo)
    bus.subscribe("boss_spawn", _on_bossspawn)
    bus.subscribe("boss_kill", _on_bosskill)
    bus.subscribe("player_death", _on_death)
    bus.subscribe("game_over", _on_gameover)
    # Phase 5 事件
    bus.subscribe("quest_start", lambda d: play("shrine"))
    bus.subscribe("quest_done", lambda d: play("levelup"))
    bus.subscribe("quest_failed", lambda d: play("hurt"))
    bus.subscribe("chest_open", lambda d: play("chest"))
    bus.subscribe("chest_loot", lambda d: play("gold"))
    bus.subscribe("food_eat", lambda d: play("food"))
    bus.subscribe("mimic_wake", lambda d: play("explode", 0.6))
    bus.subscribe("upgrade_reroll", lambda d: play("shrine", 0.7))
    bus.subscribe("upgrade_banish", lambda d: play("shield"))
