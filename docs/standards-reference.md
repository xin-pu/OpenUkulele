# 开发标准引用

本仓库遵循 `D:\Playbook\dev-standards`。

- 采纳提交：`5cfb83b4295c12d94c006fb2043d33300a6ebe48`
- 适用范围：Python 包（`src/uketab`）与 .NET 桌面壳（`desktop/`）
- .NET 细则入口：`dev-standards/dotnet/SKILL.md`（编码风格、注释、测试、工具链质量、包管理、可观测性、运行时配置、安全依赖）
- GitHub 流程：`dev-standards/github-workflow/issue-lifecycle.md`、`pull-request-policy.md`
- 与标准的偏差必须记录在 `docs/ledger/standards-deviations.md`，合并评审前完成。

## 本仓库执行要点（摘要自标准）

- C#：nullable 启用；命名空间 = 项目根命名空间 + 相对 `.csproj` 的目录段；目录布局与 `docs/design/2026-09-14-wpf-desktop-mvp.md` §3.3 一致。
- 包版本集中在 `Directory.Packages.props`（`ManagePackageVersionsCentrally`），`.csproj` 内不得出现 `Version=`。
- 测试：xUnit + Shouldly，命名 `Member_condition_expected_result`。
- 外部调用（Python 子进程）必须可取消、有超时、走 `ArgumentList`；错误码稳定不解析中文文本。
- Issue 先行：实质性变更必须先有 GitHub Issue（见 `docs/issue-ledger.md` 与远端 issue）。
