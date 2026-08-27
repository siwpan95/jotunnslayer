"""
合成核心 — 多波形振荡器 + ADSR 包络 + 单音合成引擎

波形类型:
    SAW         锯齿波 — 丰富谐波，金属感/弦乐
    SQUARE      方波   — 8-bit 复古 / 芯片音乐
    SINE        正弦波 — 纯净
    TRIANGLE    三角波 — 柔和泛音
    NOISE_WHITE 白噪声 — 全频段，冲击声
    NOISE_PINK  粉红噪声 — 自然环境音
    NOISE_BROWN 棕噪声 — 低频主导

包络形状:
    PERCUSSIVE  打击乐
    PAD         铺底
    PLUCK       拨弦
    SWELL       渐强
    REVERSE     反转

从 bloodmusic/core/ 提取并独立化。
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore

# 默认采样率
SR: int = 44100


# ================================================================
#  振荡器
# ================================================================

class OscType(Enum):
    """振荡器波形类型。"""
    SAW = "saw"
    SQUARE = "square"
    SINE = "sine"
    TRIANGLE = "triangle"
    NOISE_WHITE = "noise_white"
    NOISE_PINK = "noise_pink"
    NOISE_BROWN = "noise_brown"


def _osc_saw(t: np.ndarray, freq: float) -> np.ndarray:
    """锯齿波。"""
    return 2.0 * ((t * freq) % 1.0) - 1.0


def _osc_square(t: np.ndarray, freq: float, duty: float = 0.5) -> np.ndarray:
    """方波，duty 控制占空比。"""
    return np.where(((t * freq) % 1.0) < duty, 1.0, -1.0)


def _osc_sine(t: np.ndarray, freq: float) -> np.ndarray:
    """正弦波。"""
    return np.sin(2.0 * np.pi * t * freq)


def _osc_triangle(t: np.ndarray, freq: float) -> np.ndarray:
    """三角波。"""
    phase = (t * freq) % 1.0
    return 4.0 * np.abs(phase - 0.5) - 1.0


def _osc_noise_white(n: int) -> np.ndarray:
    """白噪声。"""
    rng = np.random.default_rng()
    return 2.0 * rng.random(n) - 1.0


def _osc_noise_pink(n: int) -> np.ndarray:
    """粉红噪声（Voss-McCarthy 算法）。"""
    out = np.zeros(n)
    states = np.zeros(12)
    rng = np.random.default_rng()
    for i in range(n):
        inc = rng.standard_normal()
        idx = i & (len(states) - 1)
        states[idx] = 0.998 * states[idx] + inc
        out[i] = states.mean() + inc * 0.05
    return out * 3.0


def _osc_noise_brown(n: int) -> np.ndarray:
    """棕噪声（随机游走）。"""
    rng = np.random.default_rng()
    out = np.cumsum(2.0 * rng.random(n) - 1.0)
    peak = np.max(np.abs(out))
    if peak > 0:
        out = out / (peak + 1e-8)
    return out


_OSC_MAP = {
    OscType.SAW:      _osc_saw,
    OscType.SQUARE:   _osc_square,
    OscType.SINE:     _osc_sine,
    OscType.TRIANGLE: _osc_triangle,
}


def oscillator(
    t: np.ndarray,
    freq: float,
    osc_type: OscType = OscType.SINE,
    duty: float = 0.5,
) -> np.ndarray:
    """统一振荡器接口。

    参数:
        t: 时间数组 (秒)
        freq: 基频 (Hz)，噪声类型忽略此参数
        osc_type: 波形类型
        duty: 方波占空比 (0.0~1.0)

    返回:
        归一化 [-1, 1] 波形数组 (float64)
    """
    if osc_type == OscType.NOISE_WHITE:
        return _osc_noise_white(len(t))
    if osc_type == OscType.NOISE_PINK:
        return _osc_noise_pink(len(t))
    if osc_type == OscType.NOISE_BROWN:
        return _osc_noise_brown(len(t))

    fn = _OSC_MAP.get(osc_type, _osc_saw)
    if osc_type == OscType.SQUARE:
        return fn(t, freq, duty)
    return fn(t, freq)


# ================================================================
#  包络
# ================================================================

class EnvShape(Enum):
    """包络形状。"""
    PERCUSSIVE = "percussive"
    PAD = "pad"
    PLUCK = "pluck"
    SWELL = "swell"
    REVERSE = "reverse"


@dataclass
class ADSRParams:
    """ADSR 参数 — 所有时间单位为秒。"""
    attack: float = 0.01
    decay: float = 0.1
    sustain: float = 0.7
    release: float = 0.3


def make_envelope(
    length: int,
    shape: EnvShape = EnvShape.PERCUSSIVE,
    adsr: Optional[ADSRParams] = None,
) -> np.ndarray:
    """生成包络数组。

    参数:
        length: 样本数
        shape: 包络形状
        adsr: 自定义 ADSR（仅 PERCUSSIVE 时生效）

    返回:
        float64 包络数组，范围 [0, 1]
    """
    t = np.linspace(0, 1, length, dtype=np.float64)

    if shape == EnvShape.PERCUSSIVE:
        if adsr is not None:
            a_len = int(length * adsr.attack)
            d_end = int(length * (adsr.attack + adsr.decay))
            env = np.ones(length, dtype=np.float64)
            if a_len > 0:
                env[:a_len] = np.linspace(0, 1, a_len)
            if d_end > a_len:
                env[a_len:d_end] = np.linspace(1, adsr.sustain, d_end - a_len)
            if d_end < length:
                env[d_end:] = adsr.sustain * np.linspace(1, 0, length - d_end)
            return env

        attack_samples = max(1, int(length * 0.02))
        env = np.exp(-t * 15).astype(np.float64)
        env[:attack_samples] = np.linspace(0, 1, attack_samples)
        return env

    elif shape == EnvShape.PAD:
        attack_samples = int(length * 0.3)
        release_start = int(length * 0.8)
        env = np.ones(length, dtype=np.float64)
        if attack_samples > 0:
            env[:attack_samples] = np.linspace(0, 1, attack_samples)
        if release_start < length:
            env[release_start:] = np.linspace(1, 0, length - release_start)
        return env

    elif shape == EnvShape.PLUCK:
        attack_samples = max(1, int(length * 0.01))
        env = (np.exp(-t * 25) * 0.9).astype(np.float64)
        env[:attack_samples] = np.linspace(0, 1, attack_samples)
        return env

    elif shape == EnvShape.SWELL:
        crescendo_end = int(length * 0.7)
        release_start = int(length * 0.9)
        env = np.ones(length, dtype=np.float64)
        env[:crescendo_end] = np.linspace(0.05, 0.95, crescendo_end)
        env[crescendo_end:release_start] = 0.95
        if release_start < length:
            env[release_start:] = np.linspace(0.95, 0, length - release_start)
        return env

    elif shape == EnvShape.REVERSE:
        reverse_sustain = int(length * 0.7)
        env = np.ones(length, dtype=np.float64)
        env[:reverse_sustain] = np.linspace(0.05, 1.0, reverse_sustain)
        env[reverse_sustain:] = 0.0
        return env

    else:
        return np.ones(length, dtype=np.float64)


# ================================================================
#  SynthVoice + 合成引擎
# ================================================================

@dataclass
class SynthVoice:
    """单音合成参数。

    属性:
        freq: 基频 (Hz)
        osc_type: 波形类型
        duration: 持续时间 (秒)
        volume: 音量 (0~1)
        env_shape: 包络形状
        adsr: 自定义 ADSR 参数
        pitch_mod: 音高偏移 (半音)
        vibrato_rate: 颤音频率 (Hz)
        vibrato_depth: 颤音深度 (半音)
        detune: Unison 不协和度 (半音)
        harmonics: 泛音列表 [(倍频, 相对振幅), ...]
    """
    freq: float = 440.0
    osc_type: OscType = OscType.SINE
    duration: float = 0.15
    volume: float = 1.0
    env_shape: EnvShape = EnvShape.PERCUSSIVE
    adsr: Optional[ADSRParams] = None
    pitch_mod: float = 0.0
    vibrato_rate: float = 0.0
    vibrato_depth: float = 0.0
    detune: float = 0.0
    harmonics: List[Tuple[float, float]] = field(default_factory=list)


def synthesize_voice(voice: SynthVoice, sample_rate: int = SR) -> np.ndarray:
    """合成单个 SynthVoice 为 float32 波形。

    参数:
        voice: SynthVoice 参数
        sample_rate: 采样率 (默认 44100)

    返回:
        float32 波形数组，范围约 [-1, 1]
    """
    if not HAS_NUMPY:
        raise ImportError(
            "synthesize_voice() 需要 numpy。请安装: pip install numpy"
        )

    n_samples = max(int(voice.duration * sample_rate), 1)
    t = np.linspace(0, voice.duration, n_samples, dtype=np.float64)

    # 基础频率 + 音高偏移
    base_freq = voice.freq * (2 ** (voice.pitch_mod / 12))

    # 颤音调制
    if voice.vibrato_depth > 0 and voice.vibrato_rate > 0:
        vib_env = make_envelope(n_samples, EnvShape.PAD)
        vib = 1.0 + (voice.vibrato_depth / 12) * np.sin(
            2 * np.pi * voice.vibrato_rate * t
        ) * vib_env
        mod_freq = base_freq * vib
    else:
        mod_freq = np.full(n_samples, base_freq, dtype=np.float64)

    # 主振荡器
    main_sig = oscillator(t, mod_freq, voice.osc_type).astype(np.float64)

    # 泛音叠加
    for harmonic_mult, harmonic_amp in voice.harmonics:
        h_sig = oscillator(t, mod_freq * harmonic_mult, voice.osc_type)
        main_sig += h_sig * harmonic_amp

    # Unison detune
    if abs(voice.detune) > 0.001:
        detune_freq = mod_freq * (2 ** (voice.detune / 12))
        detune_sig = oscillator(t, detune_freq, voice.osc_type) * 0.6
        main_sig += detune_sig

    # 包络
    env = make_envelope(n_samples, voice.env_shape, voice.adsr)
    sig = main_sig * env * voice.volume

    # 安全限幅
    peak = np.max(np.abs(sig))
    if peak > 1.0:
        sig = sig / peak * 0.98

    return sig.astype(np.float32)


# ================================================================
#  音符 → 频率
# ================================================================

# 音符名到半音编号（C4=60）
_NOTE_TO_SEMITONE: dict = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3,
    "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8,
    "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11,
}

# 正确的音名 -> 半音（C4 = 60）。按"字母 + 升降号计数"推算，
# 使自然 B / 降 B(b) / 重降(bb) / 重升(##) 都能正确解析，
# 根治旧实现 `.replace("B","b")` 把自然音 B 与降 B 都改坏、查表键不存在而崩溃的缺陷。
_BASE_SEMITONE: dict = {
    "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
}
_ACC = {"#": 1, "b": -1}
# 匹配：字母 + 可选升降号 + 可选分隔符 + 八度数
_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]*)[_ ]*(\d)$")

# 支持带下划线的音符表示（如 Eb_4 表示 E♭_4）
_NOTE_REGEX_IMPORT: bool = False


def note_to_freq(note: str, a4_freq: float = 440.0) -> float:
    """将音符名转换为频率。

    参数:
        note: 音符名，如 "C4", "A4", "Eb_4", "F#5"
        a4_freq: A4 基准频率 (Hz)

    返回:
        频率 (Hz)

    Raises:
        ValueError: 无效音符格式
    """
    # 标准化：处理下划线分隔 (Eb_4 → Eb 4)
    note = note.strip()

    # 按"字母 + 升降号计数"推算半音：先取自然音半音，再累加升降号，
    # 不再使用 .replace("B","b")，从而正确区分自然音 B 与降 B(b)/重降(bb)。
    m = _NOTE_RE.match(note)
    if not m:
        raise ValueError(f"无效音符格式: '{note}'，期望格式如 'C4', 'Eb_4'")

    letter = m.group(1).upper()
    acc = m.group(2)
    octave = int(m.group(3))

    if letter not in _BASE_SEMITONE:
        raise ValueError(f"未知音符名: '{letter}'")

    semitone = _BASE_SEMITONE[letter]
    for ch in acc:
        semitone += _ACC.get(ch, 0)

    # 计算与 A4 (MIDI 69) 的半音差
    midi_number = 12 * (octave + 1) + semitone
    semitone_diff = midi_number - 69  # A4 = MIDI 69

    return a4_freq * (2 ** (semitone_diff / 12))
