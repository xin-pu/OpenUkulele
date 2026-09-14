# UkeTab CLI 原型设计

## 目标

构建一个离线 Python 命令行工具：接受 MIDI 或普通音频文件，生成默认高 G（re-entrant G4-C4-E4-A4）、15 品四弦尤克里里的简易版与困难版指弹谱。每份输出必须通过可玩性校验，并提供 ASCII tab、GP5 和 JSON 报告。

首版验证“可弹的难度分级编配”，而不承诺任意混音歌曲的准确转写。

## 范围

### 包含

- MIDI（`.mid` / `.midi`）输入；这是确定性主路径。
- 单声部或单乐器、30 秒至 5 分钟的 WAV、MP3、M4A、OGG 音频输入；通过 Basic Pitch 取得候选音符。
- 统一的音符事件中间表示。
- 4/4 优先的节拍网格和八分音符量化。
- 简易与困难两个编配预设。
- 高 G 四弦、0–15 品候选指法与动态规划选位。
- 同弦冲突、音域、和弦数量、跨度、左手手指占用等可玩性校验。
- ASCII、GP5、JSON 报告输出。
- 回归测试使用自建 MIDI fixture；用户提供的手机录音只作为本地手工验收样本，不提交到 Git。

### 不包含

- 人声/伴奏分离、任意混音转写、交互式编辑、Web UI、PDF、MusicXML、试听、低 G、Capo、版权内容分发。
- 对音频输入作“音符级 F1 ≥ 0.85”的承诺；该指标只可在有人工标注的限定数据集上另行建立。

## 技术选型

- Python 3.11+，`src/` 目录布局。
- `mido`：MIDI 解析；`basic-pitch`：可选音频转写；`pyguitarpro`：GP5 写入。
- 标准库 `dataclasses`、`argparse`、`json`；`pytest` 做测试。
- 首版不引入数据库、Web 框架、外部服务或求解器。动态规划及小规模枚举足够处理四弦、每拍至多四音的候选组合。

## 架构与数据流

```text
CLI arguments
  -> Input adapter (MIDI | audio)
  -> list[NoteEvent]
  -> timing.normalize_events()
  -> arrangement.arrange_easy() / arrange_hard()
  -> fingering.solve_measures()
  -> validation.validate_arrangement()
  -> fallback.simplify_invalid_measures()
  -> ASCII / GP5 / JSON writers
```

输入适配器只负责产生 `NoteEvent`，不做尤克里里或难度决定。编配器只决定同一时间网格中保留哪些音高及其音乐角色；指法求解器负责将音高分配为弦/品/左右手信息。校验器独立于求解器，永远对最终结果复核。任何一个阶段的失败都用结构化诊断向 CLI 返回，不能静默输出空谱或不可弹谱。

## 目录与职责

```text
pyproject.toml                         项目元数据、依赖、CLI 命令
src/uketab/models.py                   不可变领域数据模型与枚举
src/uketab/tuning.py                   高 G 调弦、音高/弦/品映射、候选指法
src/uketab/input/midi.py               MIDI -> NoteEvent
src/uketab/input/audio.py              音频 -> NoteEvent（可选依赖）
src/uketab/timing.py                   速度、量化、时间片与小节划分
src/uketab/arrangement.py              简易/困难保留音策略
src/uketab/fingering.py                每个时间片候选和弦生成、跨片 DP
src/uketab/validation.py               可玩性报告与错误码
src/uketab/fallback.py                 逐小节降级与重新求解
src/uketab/render/ascii.py             可读 ASCII tab
src/uketab/render/gp5.py               编配模型 -> GP5
src/uketab/report.py                   JSON 可玩性报告
src/uketab/cli.py                      参数解析、编排、退出码
tests/...                              单元、集成、CLI fixture 测试
```

## 领域模型与公共接口

时间一律以秒保存，量化后额外保留节拍位置，避免在导入时丢失原始时值。

```python
@dataclass(frozen=True)
class NoteEvent:
    onset: float
    duration: float
    pitch: int                 # MIDI 0..127
    velocity: float            # 0.0..1.0
    source: str                # "midi" or "audio"

@dataclass(frozen=True)
class TimedPitch:
    beat: Fraction
    duration_beats: Fraction
    pitch: int
    velocity: float
    role: Literal["melody", "bass", "harmony"]

@dataclass(frozen=True)
class Fingering:
    string: int                # 1..4：A, E, C, G；显示时同样使用该编号
    fret: int                  # 0..15
    finger_left: int | None    # 1..4；开放弦为 None
    finger_right: Literal["p", "i", "m", "a"] | None

@dataclass(frozen=True)
class TabNote:
    note: TimedPitch
    fingering: Fingering

@dataclass(frozen=True)
class Arrangement:
    difficulty: Literal["easy", "hard"]
    tempo_bpm: float
    time_signature: tuple[int, int]
    notes: tuple[TabNote, ...]

@dataclass(frozen=True)
class ValidationReport:
    passed: bool
    errors: tuple[ValidationIssue, ...]
    shift_count: int
    max_span: int
    barre_count: int
    difficulty_score: float
```

默认高 G 开放弦 MIDI 音高为 `{4: 67, 3: 60, 2: 64, 1: 69}`，其中 4 弦 G4 是 re-entrant 高音。`enumerate_candidates(pitch, tuning, max_fret=15)` 返回所有音高相等的 `(string, fret)`，绝不能假定弦号与音高单调相关。

## 输入与规范化

### MIDI

合并轨道，累积 `set_tempo` 元消息得到秒级时间。所有 note-on/note-off 配对为事件；零时值、超出 MIDI 范围与没有音符的文件均返回明确错误。优先使用文件拍号；缺失则设置 4/4。多轨 MIDI 被合并，并在后续按时间片限制最多四音。

### 音频

使用 Basic Pitch 的本地 API。适配层仅接受已知扩展名、文件大小不超过 100 MB、时长不超过 5 分钟的普通媒体文件。推理失败、模型未安装、无法解码和没有置信音符分别返回不同错误码。CLI 在报告中标记 `source="audio"`，并加入“转写候选需要人工听辨”的警告。

音频不做静默的降噪、变调或分离。手机录音的推荐格式为单声部、安静环境、30–60 秒；这属于用户说明与手工验收约束，而不是算法保证。

### 节拍和量化

MIDI 使用其节拍与 BPM；音频初版若没有可靠节拍估计，要求 `--tempo`，否则默认 80 BPM 并附警告。将 onset 对齐至最近八分音符；简易版一律八分音符网格，困难版允许十六分音符（如实现的源事件包含该精度），但不产生三连音。量化导致时值小于一个网格时提升为一个网格。

## 编配策略

编配器的输入是按节拍时间排序的 `TimedPitch`。它不能生成输入中不存在的旋律音；低音和和声仅从当前时片的可用音及经明确和弦模板选择的音高产生。

### 简易版

- 每个时间片保留最高音作为 `melody`。
- 每个小节第一拍及第三拍（不足一小节时首拍）尝试加入最低可演奏根音作为 `bass`；未能确定根音时不补低音。
- 只允许开放弦或 0–5 品候选，允许的同一时间音数最多 2。
- 跨度上限 4 品，禁止横按；保留八分音符量化结果。
- 右手规则：低音为 `p`，旋律按 A/E/C/G 弦依次偏好 `a/m/i/i`。

### 困难版

- 每个时间片保留最高音作为 `melody`，再保留低音；可加入最多两个 `harmony` 音。
- 每拍最多 4 音，0–15 品候选，跨度上限 5 品。
- 允许相同品位、连续相邻弦的横按；初版只报告横按，不另行建模复杂半横按。
- 优先最小化旋律音丢失，其次最大化可行和声数，再最小化换把和跨度。
- campanella、自然泛音、装饰音不在首版自动生成；这避免把“困难”误做成“不可预测”。

和弦识别不独立实现。首版将每个时间片已有的低音/中音当作和声候选，无法确认和声时宁可只输出旋律+低音。

## 指法求解

一个时间片中的不同音高先各自枚举候选弦/品，再以笛卡尔组合建立和弦候选；候选生成阶段移除同弦冲突、超过弦数、超范围和不符合当前难度品位范围的组合。随后为按弦分配左手指：开放弦不占手指；同一品位连续弦可作为横按（仅困难版）；其他按弦使用不同的 1–4 指。

对每小节的候选状态使用动态规划。状态是该小节上一时间片选定的组合与其最小成本；转移成本为：

```text
10000 * 不可行
+ 40 * 换把次数
+ 8 * 平均品位移动距离
+ 5 * 当前跨度
+ 3 * 非开放弦数
+ 2 * 横按数（困难版）
```

成本权重先固定在代码常量中，报告不宣称其为客观难度。`difficulty_score` 是归一化的解释性指标，不用于否决结果。

## 校验与降级

校验器独立检查每个同时发声组与相邻组，输出带小节和时间位置的 `ValidationIssue`：

- `same_string_conflict`
- `out_of_range`
- `too_many_notes`
- `span_exceeded`
- `finger_conflict`
- `barre_not_allowed`
- `unplayable_pitch`

若一个小节没有任何通过校验的候选，降级器按下列顺序操作并重新求解：移除 harmony → 移除 bass（但保留 melody）→ 保留该小节最高旋律音。仍无法映射时，命令以非零退出，不产生标为成功的谱；报告包含失败小节。

全曲输出前必须 `report.passed is True`。这定义了“可玩性通过率 100%”：已成功写出的谱都必须通过该校验，并不代表任何输入都能生成谱。

## 输出

输出目录由 `--output-dir` 给出且必须不存在或为空；写入临时目录后原子移动，避免半成品。

- `{stem}-easy.txt`、`{stem}-hard.txt`：四行 tab，包含 tempo、调弦和小节线；同一时间组纵向对齐。
- `{stem}-easy.gp5`、`{stem}-hard.gp5`：一个四弦轨道，显示调弦为 A4/E4/C4/G4。GP5 文件的兼容性以 TuxGuitar 打开为手工验收。
- `{stem}-report.json`：输入元数据、版本、量化参数、两版统计、warnings、validation issues。没有通过校验时仍可写报告，但不写该难度的 tab/GP5。

CLI 例子：

```powershell
uketab arrange .\samples\melody.mid --output-dir .\output
uketab arrange .\recording.m4a --tempo 80 --output-dir .\output
```

退出码：`0` 两版均成功；`2` 参数或格式错误；`3` 输入/转写错误；`4` 至少一版不可生成；`5` 导出错误。

## 错误处理与可观测性

不收集任何网络遥测。`--verbose` 将打印阶段、事件数、量化网格、每小节候选数量、降级操作及输出路径；默认仅打印结果或可行动的错误。异常统一转换为带建议动作的用户错误，例如“音频转写不可用：安装项目的 audio extra，或改用 MIDI”。原始堆栈仅在 `--debug` 显示。

## 测试与验收

单元测试必须覆盖：

- 高 G 映射：同一音高多候选、不可演奏音、15 品边界；不允许把 G 弦按低音处理。
- MIDI 配对、tempo 和拍号解析；坏文件、空文件与悬空 note-on。
- 量化、持续音和时间片分组。
- 简易版的 0–5 品、最多两音、无横按、最大跨度 4。
- 困难版最多四音、最大跨度 5、可报告横按。
- 同弦冲突、手指冲突、换把统计和降级顺序。
- ASCII 对齐与 JSON 模式；GP5 在成功路径写出非空文件。

集成测试使用小型、仓库内生成的 MIDI fixture：单旋律、旋律+低音、超音域、不可行和弦。音频测试只 mock Basic Pitch 的适配器输出，避免 CI 下载模型和使测试结果随模型版本漂移。

人工验收使用用户后续提供的 30–60 秒手机录音与一个已知旋律 MIDI：两版均可导出、校验通过、在 TuxGuitar 中打开、人工实际弹奏无同弦/跨度/横按违规。性能目标是这类样本在普通开发机 60 秒内完成；音频模型首次加载不计入核心指法求解性能。

## 后续演进边界

低 G 通过 `Tuning` 参数扩展；PDF/MusicXML 仅消费 `Arrangement`，不得绕过校验器。交互编辑 UI 操作 `TimedPitch` 或 `Arrangement` 的序列化 JSON，再重新调用求解/校验。独立的和弦识别、分离、试听和 Web API 都是后续独立设计，不改变本版的领域内核接口。
