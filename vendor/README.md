# vendor/ 目录说明

本目录存放从外部项目选择性复制的（vendored）模块，保持本项目零外部运行时依赖。

## 来源：alloy

- 上游路径：`G:/games/alloy`（作者 "全哥"，MIT License）
- vendored 时间：2026 年（本项目 Phase 6/8 落地阶段）
- 许可：MIT。原版权声明保留在各文件头部，此处附上游 LICENSE 摘要：
  > Copyright (c) alloy 作者，特此免费授予任何获得本软件及相关文档文件副本的人不受限制地处理本软件的权利……（详见 G:/games/alloy/LICENSE）

### 复制的文件与用途

| 文件 | 用途 |
|---|---|
| audio/synth.py | 多波形振荡器 + ADSR 包络合成（8-bit 音效） |
| audio/music_gen.py | 6 种场景 BGM 预设 + WAV 生成（MENU/BATTLE/BOSS/VICTORY…） |
| audio/audio_system.py | pygame.mixer 后端 + numpy 数组转 Sound |
| core/event_bus.py | 松耦合事件总线（订阅/一次性/递归保护） |
| core/serializable.py | dataclass to_dict/from_dict 通用序列化 |
| core/deps.py | 可选依赖探测 |
| core/paths.py | 包路径工具（字体目录定位） |
| systems/save_load.py | 多槽位 JSON 存档 + 版本检查 |
| utils/font.py | 本地 CJK 字体优先加载 |
| utils/json_loader.py / logger.py / text_fmt.py | JSON/日志/文本工具 |
| fonts/BaoCanMouHuiTingShouXieTi2.0-2.ttf | 打包中文手写字体 |

### 相对上游的修改

1. `audio/music_gen.py`：`from alloy.audio.synth` → `from .synth`
2. `utils/font.py`：`from alloy.core.paths` → `from ..core.paths`（原 try/except 兜底保留）

### 同步上游

需要同步时：重新复制对应文件并重做上述两处导入修正，然后跑 `python tests\test_vendor.py` 冒烟。
