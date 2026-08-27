"""
统一音频系统 — BGM + SFX 播放接口

后端: pygame.mixer（主要）/ numpy 数组（bloodmusic 兼容）

特性:
    - BGM 播放/停止/淡入淡出
    - SFX 多重同时播放
    - 音量控制
    - 音频数据缓冲区（用于实时合成音频播放）

使用示例:
    audio = AudioSystem(sample_rate=44100)
    audio.play_bgm("menu_theme.wav", volume=0.5)
    audio.play_sfx("explosion.wav", volume=0.8)
    audio.stop_bgm(fadeout_ms=1000)
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None  # type: ignore


class AudioSystem:
    """统一音频播放系统。

    支持两种工作模式:
    1. Pygame mixer 模式 (默认): 从文件加载和播放
    2. 缓冲模式: 直接播放 numpy 数组（用于实时合成）
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        channels: int = 8,
        buffer_size: int = 1024,
        master_volume: float = 0.7,
    ):
        """初始化音频系统。

        参数:
            sample_rate: 采样率 (Hz)
            channels: SFX 最大同时播放数
            buffer_size: 缓冲区大小
            master_volume: 总音量 (0~1)
        """
        self.sample_rate = sample_rate
        self.master_volume = max(0.0, min(1.0, master_volume))
        self._bgm_volume: float = 1.0
        self._sfx_volume: float = 1.0
        self._bgm_playing: bool = False
        self._bgm_path: Optional[str] = None

        # 音频缓存
        self._sound_cache: Dict[str, Any] = {}
        self._buffer_cache: Dict[str, np.ndarray] = {}

        # 初始化 pygame mixer
        self._pygame_available: bool = False
        self._init_pygame(channels, buffer_size)

    # ── 初始化 ──

    def _init_pygame(self, channels: int, buffer_size: int):
        """初始化 pygame.mixer。"""
        try:
            import pygame
            pygame.mixer.init(
                frequency=self.sample_rate,
                size=-16,
                channels=channels,
                buffer=buffer_size,
            )
            self._pygame_available = True
            self._pygame = pygame
        except Exception:
            self._pygame_available = False

    # ── BGM 控制 ──

    def play_bgm(
        self,
        file_path: str,
        volume: float = 1.0,
        loops: int = -1,
        fadein_ms: int = 500,
    ) -> bool:
        """播放背景音乐。

        参数:
            file_path: 音乐文件路径 (.wav / .ogg / .mp3)
            volume: 音量 (0~1)
            loops: 循环次数 (-1=无限)
            fadein_ms: 淡入时间 (毫秒)

        返回:
            True=成功, False=失败
        """
        if not self._pygame_available:
            return False

        try:
            self._pygame.mixer.music.load(file_path)
            self._pygame.mixer.music.set_volume(volume * self.master_volume)
            self._pygame.mixer.music.play(loops=loops, fade_ms=fadein_ms)
            self._bgm_volume = volume
            self._bgm_path = file_path
            self._bgm_playing = True
            return True
        except Exception:
            return False

    def play_bgm_from_array(
        self,
        audio_data: np.ndarray,
        volume: float = 1.0,
        loops: int = -1,
        sample_rate: int = 44100,
    ) -> bool:
        """从 numpy 数组播放 BGM（实时合成）。

        参数:
            audio_data: float32/float64 数组，范围 [-1, 1]
            volume: 音量
            loops: 循环次数
            sample_rate: 采样率

        返回:
            True=成功
        """
        if not HAS_NUMPY:
            return False

        if not self._pygame_available:
            return False

        try:
            # 转 int16
            audio_int16 = np.clip(audio_data * 32767, -32768, 32767).astype(np.int16)

            # 构建 pygame Sound
            sound = self._array_to_sound(audio_int16, sample_rate)

            if sound is None:
                return False

            channel = self._pygame.mixer.find_channel()
            if channel:
                channel.set_volume(volume * self.master_volume)
                channel.play(sound, loops=loops)
                self._bgm_playing = True
                self._bgm_volume = volume
            return True
        except Exception:
            return False

    def stop_bgm(self, fadeout_ms: int = 500):
        """停止 BGM 播放。

        参数:
            fadeout_ms: 淡出时间 (毫秒)
        """
        if not self._pygame_available:
            return

        try:
            self._pygame.mixer.music.fadeout(fadeout_ms)
        except Exception:
            pass
        self._bgm_playing = False

    def pause_bgm(self):
        """暂停 BGM。"""
        if self._pygame_available:
            try:
                self._pygame.mixer.music.pause()
            except Exception:
                pass

    def unpause_bgm(self):
        """恢复 BGM。"""
        if self._pygame_available:
            try:
                self._pygame.mixer.music.unpause()
            except Exception:
                pass

    # ── SFX 控制 ──

    def play_sfx(
        self,
        file_path: str,
        volume: float = 1.0,
        loops: int = 0,
    ) -> Optional[int]:
        """播放音效文件。

        参数:
            file_path: 音效文件路径
            volume: 音量 (0~1)
            loops: 循环次数 (0=播放一次)

        返回:
            播放通道 ID（None=失败）
        """
        if not self._pygame_available:
            return None

        try:
            sound = self._load_sound(file_path)
            if sound is None:
                return None

            channel = self._pygame.mixer.find_channel()
            if channel is None:
                return None

            channel.set_volume(volume * self.master_volume * self._sfx_volume)
            channel.play(sound, loops=loops)
            return channel.get_id()
        except Exception:
            return None

    def play_sfx_from_array(
        self,
        audio_data: np.ndarray,
        volume: float = 1.0,
        sample_rate: int = 44100,
    ) -> Optional[int]:
        """从 numpy 数组播放 SFX。

        参数:
            audio_data: float32/float64 数组，范围 [-1, 1]
            volume: 音量
            sample_rate: 采样率

        返回:
            播放通道 ID
        """
        if not HAS_NUMPY:
            return None

        if not self._pygame_available:
            return None

        try:
            audio_int16 = np.clip(audio_data * 32767, -32768, 32767).astype(np.int16)
            sound = self._array_to_sound(audio_int16, sample_rate)
            if sound is None:
                return None

            channel = self._pygame.mixer.find_channel()
            if channel is None:
                return None

            channel.set_volume(volume * self.master_volume * self._sfx_volume)
            channel.play(sound)
            return channel.get_id()
        except Exception:
            return None

    def stop_all_sfx(self):
        """停止所有 SFX。"""
        if self._pygame_available:
            try:
                self._pygame.mixer.stop()
            except Exception:
                pass

    # ── 音量控制 ──

    def set_master_volume(self, volume: float):
        """设置总音量。

        参数:
            volume: 0~1
        """
        self.master_volume = max(0.0, min(1.0, volume))
        if self._pygame_available:
            try:
                self._pygame.mixer.music.set_volume(self._bgm_volume * self.master_volume)
            except Exception:
                pass

    def set_bgm_volume(self, volume: float):
        """设置 BGM 音量。

        参数:
            volume: 0~1
        """
        self._bgm_volume = max(0.0, min(1.0, volume))
        if self._pygame_available:
            try:
                self._pygame.mixer.music.set_volume(volume * self.master_volume)
            except Exception:
                pass

    def set_sfx_volume(self, volume: float):
        """设置 SFX 音量。

        参数:
            volume: 0~1
        """
        self._sfx_volume = max(0.0, min(1.0, volume))

    # ── 缓存管理 ──

    def preload(self, file_path: str):
        """预加载音频文件到缓存。

        参数:
            file_path: 音频文件路径
        """
        if self._pygame_available:
            self._load_sound(file_path)

    def clear_cache(self):
        """清除音频缓存。"""
        self._sound_cache.clear()
        self._buffer_cache.clear()

    # ── 查询 ──

    @property
    def is_bgm_playing(self) -> bool:
        """BGM 是否正在播放。"""
        if self._pygame_available:
            try:
                return self._pygame.mixer.music.get_busy()
            except Exception:
                pass
        return self._bgm_playing

    @property
    def is_available(self) -> bool:
        """pygame.mixer 是否可用。"""
        return self._pygame_available

    def get_audio_data(self, file_path: str) -> Optional[np.ndarray]:
        """读取音频文件为 numpy 数组（float32 [-1,1]）。

        参数:
            file_path: 音频文件路径

        返回:
            float32 数组，或 None
        """
        if not HAS_NUMPY:
            return None

        if file_path in self._buffer_cache:
            return self._buffer_cache[file_path]

        try:
            from scipy.io import wavfile
            sr, data = wavfile.read(file_path)
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            else:
                data = data.astype(np.float32)

            # 转单声道（如果需要）
            if data.ndim > 1:
                data = data.mean(axis=1).astype(np.float32)

            self._buffer_cache[file_path] = data
            return data
        except Exception:
            return None

    def get_rms(self, audio_data: Optional[np.ndarray] = None) -> float:
        """计算音频 RMS（均方根）能量。

        参数:
            audio_data: 音频数组，None=返回 0

        返回:
            RMS 值
        """
        if audio_data is not None and HAS_NUMPY and len(audio_data) > 0:
            return float(np.sqrt(np.mean(audio_data.astype(np.float64) ** 2)))
        return 0.0

    # ── 内部 ──

    def _load_sound(self, file_path: str) -> Any:
        """加载音效文件（带缓存）。"""
        if file_path in self._sound_cache:
            return self._sound_cache[file_path]

        if not os.path.exists(file_path):
            return None

        try:
            sound = self._pygame.mixer.Sound(file_path)
            self._sound_cache[file_path] = sound
            return sound
        except Exception:
            return None

    def _array_to_sound(self, data: np.ndarray, sample_rate: int) -> Any:
        """将 int16 numpy 数组转为 pygame.Sound。"""
        if not self._pygame_available or not HAS_NUMPY:
            return None

        try:
            import pygame.sndarray
            return pygame.sndarray.make_sound(data)
        except Exception:
            # 回退：尝试用 sampling 创建
            try:
                if data.ndim == 1:
                    stereo = np.column_stack((data, data))
                else:
                    stereo = data
                return self._pygame.sndarray.make_sound(stereo)
            except Exception:
                return None
