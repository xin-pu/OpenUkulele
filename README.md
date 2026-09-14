# OpenUkulele / UkeTab

离线尤克里里指弹谱生成器：接受 MIDI 或普通音频，为高 G（re-entrant G4-C4-E4-A4）、
15 品四弦尤克里里生成**简易**与**困难**两版指弹谱。每份成功写出的谱都通过独立的
可玩性校验（同弦冲突、音域、跨度、横按、左手指法），并输出 ASCII tab、GP5 与
JSON 报告。

设计文档：[docs/superpowers/specs/2026-09-13-ukulele-tab-cli-design.md](docs/superpowers/specs/2026-09-13-ukulele-tab-cli-design.md)

## 安装

```powershell
python -m venv .venv
.venv\Scripts\pip install -e .              # MIDI 路径（mido + PyGuitarPro）
.venv\Scripts\pip install -e ".[audio]"     # 可选：音频转写（basic-pitch + onnxruntime）
.venv\Scripts\pip install -e ".[image]"     # 可选：A4 图片谱导出（matplotlib）
.venv\Scripts\pip install -e ".[dev]"       # 测试
```

要求 Python 3.11+。音频转写在 CPU 上本地推理，不联网、不收集遥测。

## 使用

```powershell
# MIDI（确定性主路径；速度与拍号取自文件）
.venv\Scripts\uketab arrange .\samples\melody.mid --output-dir .\output

# 音频（需 audio extra；--tempo 缺省时使用 80 BPM 并在报告警告）
.venv\Scripts\uketab arrange .\recording.m4a --tempo 96 --output-dir .\output

# 附带 A4 图片谱（需 image extra；--pdf 出多页 PDF，--orientation portrait 竖版）
.venv\Scripts\uketab arrange .\samples\melody.mid --output-dir .\output --png
```

输出目录必须不存在或为空；工具写入临时目录后原子移动，避免半成品。
`--verbose` 打印各阶段细节，`--debug` 显示原始堆栈。

### 输出文件

| 文件 | 内容 |
| --- | --- |
| `{stem}-easy.txt` / `{stem}-hard.txt` | 四行 ASCII tab（A/E/C/G），含速度、调弦、小节线 |
| `{stem}-easy.gp5` / `{stem}-hard.gp5` | 四弦 GP5（调弦 A4/E4/C4/G4，15 品，GM 尤克里里音色） |
| `{stem}-report.json` | 输入元数据、量化参数、两版统计、校验问题、警告 |
| `{stem}-easy.png` / `{stem}-hard.png` | （`--png`）A4 图片谱：淡雅渐变底、弦名 A/E/C/G、把位框、**标准节奏记谱（符头/符干/符杠连杠/附点/连音线，旋律朝上低音朝下）**、角色着色 |
| `{stem}-easy.pdf` / `{stem}-hard.pdf` | （`--pdf`）A4 多页 PDF |

### 退出码

| 码 | 含义 |
| --- | --- |
| 0 | 简易与困难两版均成功 |
| 2 | 参数或格式错误 |
| 3 | 输入 / 转写错误 |
| 4 | 至少一版不可生成（报告列出失败小节） |
| 5 | 导出错误 |

## 难度预设

- **简易**：只保留旋律 + 拍 1/拍 3 上的低音；开放弦或 0–5 品；同时至多 2 音；
  跨度 ≤ 4 品；禁止横按；八分音符网格。
- **困难**：旋律 + 低音 + 至多两个和声音；每拍至多 4 音；0–15 品；跨度 ≤ 5 品；
  允许同品位相邻弦横按（计入报告）；源含十六分音符精度时使用 1/16 网格。

无法求解的小节按「去和声 → 去低音 → 仅保留最高旋律音」降级重解；仍失败则该
难度不输出谱（退出码 4），报告给出失败小节。**不会**输出未通过校验的谱。

## 音频输入的现实预期

Basic Pitch 是通用转写模型：对人声/混音会漏音、错音，也常把低音声部转在
尤克里里音域（C4–C6）以下——这些小节会被如实报告为不可编配，而不是被静默
变调。最佳输入是 30–60 秒、安静环境、单声部、旋律在 C4–C6 区间的录音；
转写结果请配合人工听辨。MIDI 输入不受这些限制。

## 开发

```powershell
.venv\Scripts\python -m pytest        # 105 项单元/集成/CLI 测试
```

架构（详见设计文档）：`input`（MIDI/音频 → NoteEvent）→ `timing`（量化/小节）→
`arrangement`（难度保留策略）→ `fingering`（候选 + 每小节动态规划）→
`validation`（独立复核）→ `fallback`（逐小节降级）→ `render`（ASCII/GP5）+ `report`。

低 G 调弦、PDF/MusicXML、交互编辑与试听均为后续演进，见设计文档末节。
