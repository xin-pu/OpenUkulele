# OpenUkulele / UkeTab

一个离线运行的尤克里里指弹谱生成器。给它一份 MIDI，或一段普通手机录音，UkeTab 会为
默认高 G（re-entrant G4-C4-E4-A4）、15 品四弦尤克里里生成**简易**与**困难**两版可编辑指弹谱。

它的重点不是逐音还原一首复杂混音歌曲，而是把旋律转换成“能在琴上弹出来”的版本：核心引擎会枚举弦/品候选、选择换把成本更低的指法，并在输出前独立检查同弦冲突、音域、左手跨度、横按和手指占用。无法满足约束时，会按“去和声 → 去低音 → 仅保留旋律”的顺序自动简化，而不会输出明知不可弹的谱。

## 当前成果

- 支持 `.mid` / `.midi`，以及可选的 `.wav`、`.mp3`、`.m4a`、`.ogg` 音频输入。
- 输出两档难度：简易版限制在 0–5 品、最多两音且无横按；困难版支持 0–15 品、至多四音与横按。
- 使用高 G re-entrant 调弦模型，而非复用吉他的线性调弦假设。
- 导出 ASCII tab、Guitar Pro 5（GP5）、JSON 可玩性报告，以及可选 PNG/PDF 图片谱。
- 支持 `.lrc` 时间轴歌词或纯文本歌词，仅对齐旋律音并显示在 ASCII/图片谱中。
- 默认不写入任何个人水印；传入 `--watermark "文字"` 才添加水印。
- 本地测试套件目前收集 120 项单元、集成与 CLI 测试。

## 适合与不适合的输入

**最适合**：有明确节拍的 MIDI，或 30–60 秒、安静环境、单声部/单乐器、旋律主要在 C4–C6 的手机录音。

**暂不适合**：带大量人声、鼓、贝斯和效果器的完整商业混音。音频转写使用 Basic Pitch，可能漏音、错音或无法识别低音；工具会将超出尤克里里音域或不可编配的小节记录到报告中。需要稳定结果时，请优先使用 MIDI。

设计文档：[docs/superpowers/specs/2026-09-13-ukulele-tab-cli-design.md](docs/superpowers/specs/2026-09-13-ukulele-tab-cli-design.md)

问题与后续改进：[docs/issue-ledger.md](docs/issue-ledger.md)

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

# 附带 A4 图片谱（需 image extra；--pdf 出多页 PDF，--orientation portrait 竖版，
# --watermark "你的名字" 可选自定义水印；默认不添加水印）
.venv\Scripts\uketab arrange .\samples\melody.mid --output-dir .\output --png

# 歌词对齐到旋律音，渲染在谱面上方（.lrc 带时间轴最准；纯文本按音节顺序贴）
.venv\Scripts\uketab arrange .\recording.m4a --tempo 80 --output-dir .\output --png --lyrics .\song.lrc
```

输出目录必须不存在或为空；工具写入临时目录后原子移动，避免半成品。
`--verbose` 打印各阶段细节，`--debug` 显示原始堆栈。

### 输出文件

| 文件 | 内容 |
| --- | --- |
| `{stem}-easy.txt` / `{stem}-hard.txt` | 四行 ASCII tab（A/E/C/G），含速度、调弦、小节线 |
| `{stem}-easy.gp5` / `{stem}-hard.gp5` | 四弦 GP5（调弦 A4/E4/C4/G4，15 品，GM 尤克里里音色） |
| `{stem}-report.json` | 输入元数据、量化参数、两版统计、校验问题、警告 |
| `{stem}-easy.png` / `{stem}-hard.png` | （`--png`）A4 图片谱：淡雅渐变底、可选水印、**歌词行（`--lyrics`）**、弦名 A/E/C/G、把位框、**标准节奏记谱（符头/符干/符杠连杠/附点/连音线，旋律朝上低音朝下）**、角色着色 |
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
.venv\Scripts\python -m pytest        # 运行全部单元、集成与 CLI 测试
```

架构（详见设计文档）：`input`（MIDI/音频 → NoteEvent）→ `timing`（量化/小节）→
`arrangement`（难度保留策略）→ `fingering`（候选 + 每小节动态规划）→
`validation`（独立复核）→ `fallback`（逐小节降级）→ `render`（ASCII/GP5）+ `report`。

低 G 调弦、PDF/MusicXML、交互编辑与试听均为后续演进，见设计文档末节。
