"""
TextFormatter — 文本格式化工具集

工具方法:
    - wrap(text, width, indent):     文本折行
    - highlight(text, keyword):      关键词高亮标记
    - truncate(text, max_len):       文本截断
    - title_case(text):              标题大小写转换
    - progress_bar(current, total):  进度条渲染
    - center(text, width):           居中文本

从 hell below/shared_core/text_fmt.py 提取并增强。

使用示例:
    fmt = TextFormatter
    print(fmt.progress_bar(75, 100))
    # [███████████████░░░░░] 75%
"""

from __future__ import annotations

import re
import textwrap
from typing import Optional


class TextFormatter:
    """文本格式化静态工具类。"""

    @staticmethod
    def wrap(text: str, width: int = 80, indent: str = "") -> str:
        """将文本按指定宽度折行。

        参数:
            text: 原始文本
            width: 行宽
            indent: 每行缩进字符串

        返回:
            折行后的文本
        """
        lines = text.split("\n")
        result = []
        for line in lines:
            if line.strip():
                indent_len = len(indent)
                wrapped = textwrap.wrap(line, width=max(1, width - indent_len))
                for wline in wrapped or [""]:
                    result.append(indent + wline)
            else:
                result.append("")
        return "\n".join(result)

    @staticmethod
    def highlight(text: str, keyword: str, mark: str = "[]") -> str:
        """高亮标注文本中的关键词。

        参数:
            text: 原始文本
            keyword: 要高亮的关键词
            mark: 包裹符号（默认 []，即 [keyword]）

        返回:
            标注后的文本
        """
        if not keyword:
            return text
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)
        return pattern.sub(f"{mark}{keyword}{mark}", text)

    @staticmethod
    def truncate(text: str, max_len: int = 200, ellipsis: str = "...") -> str:
        """截断长文本，添加省略号。

        参数:
            text: 原始文本
            max_len: 最大长度（含省略号）
            ellipsis: 省略号字符串

        返回:
            截断后的文本
        """
        if len(text) <= max_len:
            return text
        return text[:max(0, max_len - len(ellipsis))] + ellipsis

    @staticmethod
    def title_case(text: str) -> str:
        """转换为标题大小写。

        参数:
            text: 原始文本

        返回:
            每个单词首字母大写的文本
        """
        return text.title()

    @staticmethod
    def progress_bar(
        current: int,
        total: int,
        width: int = 20,
        filled: str = "█",
        empty: str = "░",
        show_percent: bool = True,
    ) -> str:
        """生成 ASCII 进度条。

        参数:
            current: 当前值
            total: 最大值
            width: 进度条字符宽度
            filled: 填充字符
            empty: 空白字符
            show_percent: 是否显示百分比

        返回:
            进度条字符串，如 "[████████░░░░░░] 67%"
        """
        if total <= 0:
            bar = empty * width
            return f"[{bar}]" if not show_percent else f"[{bar}]"

        ratio = max(0.0, min(1.0, current / total))
        filled_count = int(width * ratio)
        bar = filled * filled_count + empty * (width - filled_count)

        if show_percent:
            percent = int(ratio * 100)
            return f"[{bar}] {percent:3d}%"
        return f"[{bar}]"

    @staticmethod
    def center(text: str, width: int = 80, fill: str = " ") -> str:
        """将文本居中。

        参数:
            text: 文本
            width: 总宽度
            fill: 填充字符

        返回:
            居中后的文本
        """
        return text.center(width, fill)

    @staticmethod
    def pad_left(text: str, width: int, fill: str = " ") -> str:
        """左对齐填充。

        参数:
            text: 文本
            width: 最小宽度
            fill: 填充字符

        返回:
            填充后的文本
        """
        return text.ljust(width, fill)

    @staticmethod
    def pad_right(text: str, width: int, fill: str = " ") -> str:
        """右对齐填充。

        参数:
            text: 文本
            width: 最小宽度
            fill: 填充字符

        返回:
            填充后的文本
        """
        return text.rjust(width, fill)

    @staticmethod
    def format_ratio(
        current: int,
        total: int,
        label: str = "",
        width: int = 30,
        high_color: str = "green",
        mid_color: str = "yellow",
        low_color: str = "red",
    ) -> Tuple[str, str]:
        """格式化比率并返回颜色标签。

        参数:
            current: 当前值
            total: 最大值
            label: 标签（如 "HP", "SANITY"）
            width: 进度条宽度
            high_color: >60% 时颜色
            mid_color: 30~60% 时颜色
            low_color: <30% 时颜色

        返回:
            (格式化字符串, 颜色标签)
        """
        if total <= 0:
            return (f"{label}: {current}/{total}" if label else f"{current}/{total}", "white")

        ratio = current / total
        if ratio > 0.6:
            color = high_color
        elif ratio > 0.3:
            color = mid_color
        else:
            color = low_color

        bar = TextFormatter.progress_bar(current, total, width)
        text = f"{bar}" if not label else f"{label}: {bar}"
        return (text, color)

    @staticmethod
    def format_number(n: int, sep: str = ",") -> str:
        """格式化数字（添加千分位分隔符）。

        参数:
            n: 数字
            sep: 分隔符

        返回:
            格式化后的字符串
        """
        return f"{n:{sep}}"

    @staticmethod
    def dedent(text: str) -> str:
        """移除公共前导空白。

        参数:
            text: 多行文本

        返回:
            去除公共缩进后的文本
        """
        return textwrap.dedent(text).strip()

    @staticmethod
    def word_count(text: str) -> int:
        """统计单词数（以空白分隔）。

        参数:
            text: 文本

        返回:
            单词数
        """
        return len(text.split())

    @staticmethod
    def char_count(text: str, exclude_whitespace: bool = False) -> int:
        """统计字符数。

        参数:
            text: 文本
            exclude_whitespace: 是否排除空白字符

        返回:
            字符数
        """
        if exclude_whitespace:
            return len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        return len(text)
