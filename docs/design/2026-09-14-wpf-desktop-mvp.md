# OpenUkulele WPF Desktop MVP 设计与实施计划

## 1. 目标与边界

本迭代新增一个 Windows 桌面外壳，使用户无需记忆 Python CLI 参数即可从 MIDI、普通音频和可选 LRC 歌词生成尤克里里谱。桌面端必须显示生成阶段、可取消长时间任务、预览输出并提供可行动的错误说明。

本迭代不重写 Python 编配内核，不嵌入 Python 解释器，不引入本地 HTTP 服务、账号、网络上传、音频试听或安装器。WPF 通过受控子进程调用现有 `uketab arrange`；Python 是唯一的转写、编配和文件导出权威。

## 2. 采用的标准与已知偏差

- 采用知识库：`D:\Playbook\dev-standards`，提交 `5cfb83b4295c12d94c006fb2043d33300a6ebe48`。
- .NET 规范要求：nullable、目录对应命名空间、集中包版本、构建期 `IDE0130` 错误、xUnit + Shouldly、可取消外部调用、结构化日志、版本化质量配置。
- 当前开发分支为 `feat/wpf-desktop`，未按知识库的 `<type>/<issue-number>-<title>` 命名；远程 GitHub 在创建时无法连接，尚无 Issue 编号。实施 agent 在网络可用时必须先创建或关联 `feature` Issue，并在 `docs/ledger/standards-deviations.md` 记录该一次性偏差、原因、风险、负责人和复查日期。
- 现有仓库已追踪 `docs/superpowers/`；知识库要求这些是本地工作产物。不要继续将新的工具计划写入该目录；是否移除已有历史文件须作为独立维护事项处理。

## 3. 技术决策

### 3.1 进程边界（确定）

WPF 以 `ProcessStartInfo.ArgumentList` 启动 Python，而不是采用 Python.NET。好处是 Python 模型崩溃、依赖不兼容或取消任务不会破坏 WPF UI 线程；也便于未来将开发模式的 Python 入口替换为打包后的 `uketab.exe`。

```text
OpenUkulele.Desktop (net10.0-windows)
  └─ PythonProcessArrangementService
       ├─ 读取 appsettings.json 的 PythonExecutable 与 UkeTabModule
       ├─ 启动 python -m uketab arrange ... --progress-json
       ├─ 读取 NDJSON 进度、stderr 和退出码
       └─ 返回 ArrangementJobResult
             ├─ report.json 路径和反序列化摘要
             ├─ easy/hard PNG、PDF、GP5、TXT 路径
             └─ 可显示的稳定错误代码和诊断
```

### 3.2 UI 框架（确定）

- 目标框架：`net10.0-windows`，`UseWPF=true`。
- UI：NuGet `WPF-UI` 4.3.0，提供 Fluent 主题、`NavigationView`、按钮、信息栏和文件夹选择体验。版本依据 [WPF UI 官方发布页](https://github.com/lepoco/wpfui/releases)。
- MVVM：`CommunityToolkit.Mvvm` 8.4.2，使用 `[ObservableProperty]`、`[RelayCommand]`、`[NotifyCanExecuteChangedFor]`。版本依据 [NuGet](https://www.nuget.org/packages/CommunityToolkit.Mvvm/)。
- 不在 ViewModel 中直接访问 `Process`、文件系统、`OpenFileDialog`、WPF 控件或静态服务；这些都经服务接口注入。

### 3.3 包与解决方案边界（确定）

创建 `desktop/OpenUkulele.Desktop.sln`，包含两个项目：

```text
desktop/
├─ OpenUkulele.Desktop/
│  ├─ Views/
│  ├─ ViewModels/
│  ├─ Models/
│  ├─ Services/
│  ├─ Converters/
│  ├─ Resources/
│  ├─ App.xaml
│  └─ appsettings.json
└─ OpenUkulele.Desktop.Tests/
```

这是知识库建议的 WPF 六目录布局。每个非生成的 C# 文件命名空间必须是 `OpenUkulele.Desktop` 或 `OpenUkulele.Desktop.Tests` 加上相对于各自 `.csproj` 的目录片段；例如 `Services/PythonProcessArrangementService.cs` 的命名空间为 `OpenUkulele.Desktop.Services`。

解决方案根目录新增：

```text
global.json
Directory.Build.props
Directory.Packages.props
.editorconfig
nuget.config
docs/standards-reference.md
docs/ledger/standards-deviations.md
docs/adr/0001-wpf-shell-invokes-python-cli.md
```

`Directory.Packages.props` 启用 `ManagePackageVersionsCentrally=true`。直接包为 `WPF-UI`、`CommunityToolkit.Mvvm`、`Microsoft.Extensions.Configuration.Json`、`Microsoft.Extensions.DependencyInjection`、`Microsoft.Extensions.Logging.Debug`；测试项目为 `Microsoft.NET.Test.Sdk`、`xunit`、`xunit.runner.visualstudio`、`Shouldly`。实施时在可联网环境执行 `dotnet restore`，审查每个包的许可证、漏洞审计与 .NET 10 兼容性后，把最终精确版本集中写入该文件；不得在 `.csproj` 写 `Version=`。

## 4. Python 与桌面端协议

### 4.1 新增 CLI 选项

在 Python `uketab arrange` 增加 `--progress-json`，默认行为完全不变。该模式下 stdout 只能输出一行一个 JSON 对象，禁止混入现有中文完成文本；stderr 保留人为可读的诊断。

事件契约：

```json
{"event":"started","operationId":"uuid","inputPath":"C:\\song.mid"}
{"event":"progress","operationId":"uuid","stage":"input","percent":5,"message":"正在读取输入"}
{"event":"progress","operationId":"uuid","stage":"normalize","percent":20,"message":"正在量化"}
{"event":"progress","operationId":"uuid","stage":"arrange","percent":50,"message":"正在编配"}
{"event":"progress","operationId":"uuid","stage":"export","percent":85,"message":"正在导出"}
{"event":"completed","operationId":"uuid","outputDirectory":"C:\\out","reportPath":"C:\\out\\song-report.json","exitCode":0}
```

失败事件为：

```json
{"event":"failed","operationId":"uuid","code":"input_error","message":"...","suggestion":"...","exitCode":3}
```

`operationId` 由 WPF 在每次执行前生成并作为 `--operation-id` 传入；Python 回显它，便于跨进程关联日志。阶段只能为 `input`、`transcribe`、`normalize`、`arrange`、`lyrics`、`export`；`percent` 为 0–100 且同一任务内不倒退。旧调用者不传这两个参数时不得受影响。

### 4.2 WPF 进程服务接口

```csharp
public interface IArrangementService
{
    Task<ArrangementJobResult> ArrangeAsync(
        ArrangementRequest request,
        IProgress<ArrangementProgress> progress,
        CancellationToken cancellationToken);
}
```

- 参数使用 `ProcessStartInfo.ArgumentList`，不可拼接 shell 命令字符串。
- `UseShellExecute=false`，重定向 stdout/stderr；stdout 逐行反序列化为 `ArrangementProgressEvent`，未知或损坏 JSON 作为协议错误处理。
- 每个进程都有配置的 `ProcessTimeoutSeconds`（默认 300，范围 30–900）；超时、取消或窗口关闭时调用 `Kill(entireProcessTree: true)`，等待退出并返回 `Cancelled` 或 `TimedOut` 结果。
- 正常退出时读取 JSON 报告，不根据中文文本推断结果。退出码映射为稳定 UI 错误代码：`usage_error`、`input_error`、`arrangement_partial`、`export_error`、`process_protocol_error`、`timeout`、`cancelled`。
- 日志必须带 `OperationId`、`Stage`、`ExitCode` 和耗时，不记录完整歌词、音频内容或私有文件的外发数据；本 MVP 日志目标为 Debug 输出与应用本地滚动文件，文件路径仅用于本地诊断。

## 5. UI 与交互

### 5.1 主窗口

`Views/MainWindow.xaml` 使用 WPF UI 的 `FluentWindow` 和单项 `NavigationView`，应用名称为 **OpenUkulele**。首版只有 `Views/ArrangeView.xaml`；导航保留“关于”占位但不创建不可用页面。

### 5.2 生成页

页面分为三段：

1. **输入卡片**：选择 MIDI/音频文件（必填）、LRC/TXT（可选）、输出文件夹（必填）；输入旁显示扩展名与基础校验提示。
2. **选项卡片**：Tempo 可选数值（40–240 BPM）、PNG、PDF、横/竖版、可选水印。生成按钮只有在路径、扩展名、输出目录和未运行状态均有效时可用。
3. **任务卡片**：阶段名称、进度条、当前消息、取消按钮；结束后显示摘要、警告数量和结果操作。

生成过程中禁用会改变请求的字段，保留“取消”。失败时在 `InfoBar` 展示稳定错误代码对应的中文说明、原始消息（可复制）和建议；不展示 Python 堆栈，除非用户启用后续的开发模式。

### 5.3 结果区

完成后用两个 `TabItem` 展示简易与困难版本。若 PNG 存在，使用 `Image` 加载本地文件；否则显示“未生成图片谱”的提示并保留 ASCII/GP5/PDF 打开操作。每个版本展示换把次数、最大跨度、横按数、难度分、警告和按钮：打开 PNG/PDF、在默认应用打开 GP5、打开输出文件夹。所有打开动作仅允许位于已确认输出目录下的文件。

## 6. ViewModel、模型与服务清单

| 文件 | 职责 |
| --- | --- |
| `Models/ArrangementRequest.cs` | 不可变请求：输入、歌词、输出目录、tempo、导出选项、水印。 |
| `Models/ArrangementProgress.cs` | 阶段、百分比、消息、OperationId。 |
| `Models/ArrangementJobResult.cs` | 成功/失败/取消状态、报告、输出文件、警告、错误信息。 |
| `Models/DesktopOptions.cs` | Python 可执行路径、模块、超时；由 `appsettings.json` 绑定并校验。 |
| `Services/IArrangementService.cs` | 进程执行边界。 |
| `Services/PythonProcessArrangementService.cs` | 子进程、NDJSON、超时、取消和报告读取。 |
| `Services/IFileDialogService.cs` | 文件/目录选择边界。 |
| `Services/FileDialogService.cs` | WPF UI 对话框实现。 |
| `Services/IFileLauncher.cs` | 已验证路径的默认应用/资源管理器打开。 |
| `Services/FileLauncher.cs` | `Process.Start` 的受控封装。 |
| `ViewModels/ArrangeViewModel.cs` | 输入状态、验证、异步生成/取消命令、结果状态。 |
| `ViewModels/MainWindowViewModel.cs` | 窗口标题和导航根状态。 |
| `Views/ArrangeView.xaml` | 绑定控件，不包含业务逻辑。 |
| `Views/ArrangeView.xaml.cs` | 只保留 `InitializeComponent()`。 |

## 7. 配置、开发与部署

`appsettings.json` 提供无秘密开发默认值：

```json
{
  "UkeTab": {
    "PythonExecutable": "..\\.venv\\Scripts\\python.exe",
    "Module": "uketab",
    "ProcessTimeoutSeconds": 300
  }
}
```

应用启动时验证可执行路径存在、模块名非空、超时范围合法；无效时禁用生成并说明如何修正配置。发布时改为 `UkeTabExecutable` 模式，指向随安装包带出的 `uketab.exe`；该打包工作不属于 MVP。

## 8. 测试与验收

### 单元测试

使用 xUnit 与 Shouldly。测试名称遵循 `Member_condition_expected_result`：

- `ArrangeViewModel_MissingInput_DisablesGenerate`。
- `ArrangeViewModel_RunningJob_DisablesInputAndEnablesCancel`。
- `ArrangeViewModel_CancelledJob_SetsCancelledStatus`。
- `PythonProcessArrangementService_ProgressJson_ReportsMappedStage`。
- `PythonProcessArrangementService_MalformedProgress_ReturnsProtocolError`。
- `PythonProcessArrangementService_Cancellation_KillsProcessTree`。
- `DesktopOptions_TimeoutOutsideRange_IsInvalid`。
- `FileLauncher_PathOutsideOutputDirectory_RejectsLaunch`。

进程服务通过 `IProcessRunner` 抽象做确定性测试；至少一个集成测试以一个临时的、受控 Python 脚本验证真实 stdout NDJSON 和退出码读取。不得为测试调用真实转写模型。

### Python 协议测试

Python pytest 新增：未传 `--progress-json` 保持现有文本行为；传入该参数时 stdout 每行均为可解析 JSON；成功、编配部分失败、输入失败均带 `operationId`、正确 exit code 和终结事件；百分比单调不降。

### 本地验收

1. 从 WPF 选择 `samples/melody.mid`，成功生成两版并在结果页显示。
2. 选择有效 LRC，歌词出现在 ASCII/PNG；无 LRC 时现有输出不改变。
3. 用一个睡眠测试脚本验证取消和 30 秒超时，不留孤儿 Python 进程。
4. 输入无效扩展名、不可写输出路径和缺失 Python 路径，显示可操作错误且应用不崩溃。
5. 验证没有显式 `--watermark` 时图片中无个人水印。

## 9. 实施顺序

1. 创建 GitHub feature Issue，修正分支命名或在偏差台账记录原因；建立 .NET 解决方案、集中包配置、构建风格门禁、标准引用和 ADR。
2. 实现并测试 Python `--progress-json` / `--operation-id` 协议，先确保现有 CLI 回归通过。
3. 建立 WPF UI 壳、DI、Options 验证、服务接口与不依赖 WPF 的模型测试。
4. 实现 `PythonProcessArrangementService`、进度解析、超时和取消；完成受控脚本集成测试。
5. 实现生成页 ViewModel、文件选择和基础输入验证。
6. 完成 WPF UI 页面、WPF UI 主题、进度与错误展示。
7. 接入结果预览、报告摘要与受控文件打开。
8. 更新 README，执行 restore、build、test、`dotnet format --verify-no-changes`、Python pytest；在 PR 写入所有命令结果、风险和回滚方式。

## 10. 风险与回滚

- Python 环境缺失或音频模型未安装：启动前配置校验，错误提示改用 MIDI 或安装 audio extra。
- 子进程协议漂移：协议测试与终结事件校验；WPF 遇未知事件失败而非猜测。
- 长音频卡住：可取消进程树和 300 秒超时。
- NuGet/模型打包体积：MVP 不做安装器；发布阶段单独评估 PyInstaller 与模型分发。
- 回滚：桌面端是独立 `desktop/` 目录，不改变 Python 正常 CLI 参数；移除桌面项目不会影响现有命令行用户。
