"""
音乐生成器 — MusicPattern + 预设库 + WAV 导出

预设 6 种游戏场景音乐:
    MENU    — 标题/菜单
    BATTLE  — 战斗
    BOSS    — Boss 战
    DUNGEON — 地下城/探索
    AMBIENT — 氛围/环境
    VICTORY — 胜利/事件

从 bloodmusic/music/ 提取并独立化。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

from vendor.alloy.audio.synth import (
    OscType, EnvShape, ADSRParams,
    oscillator, make_envelope, note_to_freq,
    SR,
)


# ================================================================
#  MusicPattern
# ================================================================

@dataclass
class MusicPattern:
    """音乐模式数据 — 声明式定义一段旋律。

    属性:
        name: 模式名称
        notes: 音符名列表 (None=休止符)
        durations: 每音持续拍数
        octave_shifts: 八度偏移 (可选)
        bpm: 速度 (拍/分钟)
        loop: 是否循环
        osc_type: 波形类型
        volume: 音量 (0~1)
        env_shape: 包络形状
        harmonics: 泛音列表
        vibrato_rate / vibrato_depth: 颤音参数
        chords: 和弦列表 (可选)
    """
    name: str
    notes: List[Optional[str]]
    durations: List[float]
    octave_shifts: Optional[List[int]] = None
    bpm: int = 120
    loop: bool = True

    # 音色
    osc_type: OscType = OscType.SINE
    volume: float = 0.18
    env_shape: EnvShape = EnvShape.PAD
    harmonics: List[Tuple[float, float]] = field(default_factory=list)

    # 颤音
    vibrato_rate: float = 0.0
    vibrato_depth: float = 0.0

    # 混响（简化，无效果链时仅用于标记）
    reverb_mix: float = 0.15
    reverb_decay: float = 0.8
    stereo_width: float = 0.3

    # 和弦
    chords: Optional[List[List[str]]] = None


# ================================================================
#  WAV 生成
# ================================================================

def generate_music_wav(
    pattern: MusicPattern,
    output_path: str,
    duration_sec: Optional[float] = None,
    sample_rate: int = SR,
) -> str:
    """将 MusicPattern 渲染为 WAV 文件。

    参数:
        pattern: 音乐模式
        output_path: 输出 .wav 路径
        duration_sec: 总时长 (秒)，None=自动 (1 遍完整循环 × 2)
        sample_rate: 采样率

    返回:
        输出文件路径
    """
    if not HAS_NUMPY:
        raise ImportError(
            "generate_music_wav() 需要 numpy。请安装: pip install numpy"
        )

    beat_dur = 60.0 / pattern.bpm
    total_beats = sum(pattern.durations)
    one_pass_sec = total_beats * beat_dur

    if duration_sec is None:
        loops = 2 if pattern.loop else 1
    else:
        loops = max(1, int(duration_sec / one_pass_sec))

    octaves = pattern.octave_shifts or [0] * len(pattern.notes)

    # 构建完整音符序列
    all_notes: List[Tuple[Optional[str], float, int]] = []
    for _ in range(loops):
        for i, note in enumerate(pattern.notes):
            dur = pattern.durations[i] * beat_dur
            oct_v = octaves[i] if i < len(octaves) else 0
            all_notes.append((note, dur, oct_v))

    # 逐音合成
    samples_list: List[np.ndarray] = []
    for idx, (note, dur, oct_v) in enumerate(all_notes):
        n_samp = max(int(dur * sample_rate), 1)
        t = np.linspace(0, dur, n_samp, dtype=np.float64)

        if note is None:
            sig = np.zeros(n_samp, dtype=np.float64)
        else:
            f = note_to_freq(note) * (2 ** oct_v)
            sig = oscillator(t, f, pattern.osc_type).astype(np.float64)

            # 泛音
            for h_mult, h_amp in pattern.harmonics:
                sig += oscillator(t, f * h_mult, pattern.osc_type) * h_amp

            # 颤音
            if pattern.vibrato_depth > 0 and pattern.vibrato_rate > 0:
                vib_env = make_envelope(n_samp, EnvShape.PAD)
                vib = f * (1.0 + (pattern.vibrato_depth / 12) * np.sin(
                    2 * np.pi * pattern.vibrato_rate * t) * vib_env)
                sig = oscillator(t, vib, pattern.osc_type).astype(np.float64)
                for h_mult, h_amp in pattern.harmonics:
                    sig += oscillator(t, vib * h_mult, pattern.osc_type) * h_amp

            # 包络 + 音量
            env = make_envelope(n_samp, pattern.env_shape)
            sig = sig * env * pattern.volume

        # 和弦叠加
        if pattern.chords is not None:
            chord_idx = idx % len(pattern.chords)
            if 0 <= chord_idx < len(pattern.chords):
                for cn in pattern.chords[chord_idx]:
                    cf = note_to_freq(cn)
                    chord_sig = oscillator(t, cf, pattern.osc_type).astype(np.float64)
                    for h_mult, h_amp in pattern.harmonics:
                        chord_sig += oscillator(t, cf * h_mult, pattern.osc_type) * h_amp
                    env = make_envelope(n_samp, pattern.env_shape)
                    sig += chord_sig * env * pattern.volume * 0.5

        samples_list.append(sig)

    if not samples_list:
        full_signal = np.zeros(sample_rate, dtype=np.float64)
    else:
        full_signal = np.concatenate(samples_list)

    # 归一化 + 限幅
    target_amp = 10 ** (-0.2 / 20.0)  # -0.2 dBFS
    peak = np.max(np.abs(full_signal))
    if peak > 0:
        full_signal = full_signal * (target_amp / peak)
    full_signal = np.clip(full_signal, -1.0, 1.0)

    # 写入 WAV
    from scipy.io import wavfile
    final_int16 = np.clip(full_signal * 32767, -32768, 32767).astype(np.int16)
    wavfile.write(output_path, sample_rate, final_int16)

    return output_path


# ================================================================
#  游戏音乐预设
# ================================================================

MENU = MusicPattern(
    name="menu",
    notes=["C4", "Eb_4", "G4", "C5",
           "Bb4", "G4", "Eb_4", "C4",
           "Ab4", "C5", "Bb4", "G4",
           "Eb_4", "C4", None, "G4"],
    durations=[1.0, 0.5, 0.5, 1.0,
               0.5, 0.5, 1.0, 0.5,
               1.0, 0.5, 0.5, 0.5,
               1.0, 0.5, 0.5, 1.0],
    bpm=85, loop=True,
    osc_type=OscType.TRIANGLE, volume=0.16, env_shape=EnvShape.PAD,
    harmonics=[(2.0, 0.2), (3.0, 0.08)],
    vibrato_rate=4.5, vibrato_depth=1.5,
    reverb_mix=0.2, stereo_width=0.4,
)

BATTLE = MusicPattern(
    name="battle",
    notes=["C3", None, "G3", None, "Eb3", None, "Bb3", None,
           "C3", None, "G3", "Eb3", None, "C3", None, None],
    durations=[0.75, 0.25, 0.75, 0.25, 0.75, 0.25, 0.75, 0.25,
               0.5, 0.25, 0.5, 0.5, 0.5, 1.0, 0.5, 0.5],
    bpm=110, loop=True,
    osc_type=OscType.SAW, volume=0.14, env_shape=EnvShape.PAD,
    harmonics=[(0.5, 0.15), (2.0, 0.1)],
    vibrato_rate=3, vibrato_depth=1,
    reverb_mix=0.15, stereo_width=0.3,
)

BOSS = MusicPattern(
    name="boss",
    notes=["C3", "C3", "Eb3", "C3", "G2", "G2", "Bb2", "G2",
           "Ab2", "Ab2", "B2", "Ab2", "G2", "G2", "F2", "G2"],
    durations=[0.5, 0.25, 0.5, 0.25, 0.5, 0.25, 0.5, 0.25,
               0.5, 0.25, 0.5, 0.25, 0.75, 0.25, 0.5, 1.0],
    bpm=140, loop=True,
    osc_type=OscType.SAW, volume=0.18, env_shape=EnvShape.PERCUSSIVE,
    harmonics=[(0.5, 0.25), (2.0, 0.15), (3.0, 0.08)],
    reverb_mix=0.1, stereo_width=0.5,
)

DUNGEON = MusicPattern(
    name="dungeon",
    notes=["C3", None, "Eb3", None, "Ab3", None, "G3", None,
           "F3", None, "Eb3", None, "D3", "C3", None, None],
    durations=[0.75, 0.25, 0.75, 0.25, 0.75, 0.25, 1.0, 0.5,
               0.75, 0.25, 0.75, 0.25, 0.5, 1.0, 0.5, 0.5],
    bpm=80, loop=True,
    osc_type=OscType.TRIANGLE, volume=0.14, env_shape=EnvShape.PAD,
    harmonics=[(2.0, 0.15), (3.0, 0.06)],
    vibrato_rate=3.0, vibrato_depth=1.5,
    reverb_mix=0.35, reverb_decay=1.2, stereo_width=0.6,
)

AMBIENT = MusicPattern(
    name="ambient",
    notes=["G4", None, "E4", None, "C4", None, "E4", "G4",
           "A4", None, "E4", "C4", None, "D4", None, None],
    durations=[1.0, 0.5, 1.0, 0.5, 1.0, 0.5, 0.5, 0.5,
               1.0, 0.5, 0.5, 0.5, 1.0, 1.5, 0.5, 0.5],
    bpm=72, loop=True,
    osc_type=OscType.SINE, volume=0.14, env_shape=EnvShape.PAD,
    harmonics=[(2.0, 0.12), (3.0, 0.05)],
    vibrato_rate=3.5, vibrato_depth=1,
    reverb_mix=0.3, reverb_decay=1.2, stereo_width=0.5,
)

VICTORY = MusicPattern(
    name="victory",
    notes=["C5", None, "E5", "G5", "C5", "B4", "C5", None,
           "G5", "E5", "C5", "B4", "C5", None, None, None],
    durations=[0.75, 0.25, 0.5, 0.5, 0.5, 0.5, 1.0, 0.5,
               0.5, 0.5, 0.5, 0.5, 1.0, 0.5, 1.0, 0.5],
    bpm=95, loop=True,
    osc_type=OscType.TRIANGLE, volume=0.18, env_shape=EnvShape.PAD,
    harmonics=[(2.0, 0.25), (3.0, 0.1), (4.0, 0.03)],
    vibrato_rate=5, vibrato_depth=2,
    reverb_mix=0.25, stereo_width=0.5,
)

# 预设字典
PRESETS: Dict[str, MusicPattern] = {
    "menu": MENU,
    "battle": BATTLE,
    "boss": BOSS,
    "dungeon": DUNGEON,
    "ambient": AMBIENT,
    "victory": VICTORY,
}
