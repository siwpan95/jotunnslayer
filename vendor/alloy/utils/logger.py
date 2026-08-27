"""
Logger — 轻量级文件 + 控制台日志工具

级别: DEBUG < INFO < WARNING < ERROR
特性:
    - 文件输出 + 控制台同步
    - 可选时间戳
    - 按级别过滤

从 hell below/shared_core/logger.py 提取并增强。

使用示例:
    log = Logger("logs/", level="DEBUG", filename="app.log")
    log.info("应用启动")
    log.warning("CPU 使用率过高")
    log.error("致命错误", exc_info=True)
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime
from typing import Optional, TextIO


class Logger:
    """文件 + 控制台日志器。

    级别表:
        DEBUG   = 10  详细调试信息
        INFO    = 20  常规运行信息
        WARNING = 30  警告（可能有问题）
        ERROR   = 40  错误（需要处理）
    """

    LEVELS = {
        "DEBUG": 10,
        "INFO": 20,
        "WARNING": 30,
        "ERROR": 40,
    }

    def __init__(
        self,
        log_dir: str = "",
        level: str = "INFO",
        filename: str = "app.log",
        timestamp: bool = True,
        console: bool = True,
    ):
        """初始化日志器。

        参数:
            log_dir: 日志目录，空字符串表示不写文件
            level: 最低记录级别 ("DEBUG"|"INFO"|"WARNING"|"ERROR")
            filename: 日志文件名
            timestamp: 是否记录时间戳
            console: 是否同步输出到控制台
        """
        self.level: int = self.LEVELS.get(level.upper(), 20)
        self.timestamp: bool = timestamp
        self.console: bool = console
        self._log_file: Optional[str] = None
        self._file_handle: Optional[TextIO] = None

        # 创建日志目录和文件
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            self._log_file = os.path.join(log_dir, filename)

    # ── 日志方法 ──

    def debug(self, msg: str, *args):
        """DEBUG 级别日志。"""
        self._write("DEBUG", msg, *args)

    def info(self, msg: str, *args):
        """INFO 级别日志。"""
        self._write("INFO", msg, *args)

    def warning(self, msg: str, *args):
        """WARNING 级别日志。"""
        self._write("WARNING", msg, *args)

    def error(self, msg: str, *args, exc_info: bool = False):
        """ERROR 级别日志。

        参数:
            msg: 错误消息
            *args: 格式化参数
            exc_info: 是否附带异常堆栈
        """
        formatted = msg.format(*args) if args else msg
        if exc_info:
            tb = traceback.format_exc().strip()
            if tb and tb != "NoneType: None":
                formatted += f"\n{tb}"
        self._write("ERROR", formatted)

    # ── 特殊日志 ──

    def event(self, event_type: str, detail: str):
        """记录游戏事件（使用 INFO 级别）。

        参数:
            event_type: 事件类型
            detail: 事件详情
        """
        self._write("INFO", f"[EVENT] [{event_type}] {detail}")

    def section(self, title: str):
        """记录分隔小节（使用 INFO 级别）。"""
        sep = "=" * 60
        self._write("INFO", f"{sep}\n  {title}\n{sep}")

    # ── 内部 ──

    def _write(self, level: str, message: str):
        """写入日志（按级别过滤）。"""
        if self.LEVELS.get(level, 0) < self.level:
            return

        # 构建日志行
        if self.timestamp:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] [{level:<7}] {message}\n"
        else:
            line = f"[{level:<7}] {message}\n"

        # 控制台输出
        if self.console:
            # 使用 stderr 避免与正常输出混合
            target = sys.stderr if level in ("ERROR", "WARNING") else sys.stdout
            try:
                target.write(line)
                target.flush()
            except Exception:
                pass

        # 文件输出
        if self._log_file:
            try:
                with open(self._log_file, "a", encoding="utf-8") as f:
                    f.write(line)
            except (OSError, PermissionError):
                pass

    # ── 管理 ──

    def set_level(self, level: str):
        """动态修改日志级别。

        参数:
            level: "DEBUG"|"INFO"|"WARNING"|"ERROR"
        """
        self.level = self.LEVELS.get(level.upper(), 20)

    def disable_console(self):
        """禁用控制台输出。"""
        self.console = False

    def enable_console(self):
        """启用控制台输出。"""
        self.console = True

    def get_log_path(self) -> Optional[str]:
        """获取日志文件完整路径。"""
        return self._log_file

    def clear_log(self):
        """清空日志文件内容。"""
        if self._log_file and os.path.exists(self._log_file):
            try:
                open(self._log_file, "w", encoding="utf-8").close()
            except OSError:
                pass
