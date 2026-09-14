# ADR 0001: WPF 壳以受控子进程调用 Python CLI

- 状态：已接受
- 日期：2026-09-14
- 关联：Issue #2；`docs/design/2026-09-14-wpf-desktop-mvp.md` §3.1

## 背景

OpenUkulele 需要 Windows 桌面体验，而转写、编配、可玩性校验与导出的权威实现是 Python 包 `uketab`。需要决定桌面壳如何复用该内核。

## 决策

`OpenUkulele.Desktop`（net10.0-windows）**不重写内核、不嵌入解释器、不起本地 HTTP 服务**；通过 `ProcessStartInfo.ArgumentList` 启动 `python -m uketab arrange … --progress-json --operation-id <uuid>`，以 NDJSON 进度事件、stderr 诊断与退出码为唯一跨进程契约。

## 后果

- 正面：Python 侧崩溃/依赖问题/取消都不污染 UI 进程；未来可把入口替换为打包的 `uketab.exe`（配置项 `UkeTabExecutable`），协议不变；Python 保持唯一导出权威，无双实现漂移。
- 负面：需要进程管理与协议版本纪律（未知事件即协议错误，失败优于猜测）；分发时要带上 Python 环境与模型。
- 缓解：超时 + `Kill(entireProcessTree)` 防孤儿进程；`--progress-json` 缺省时 CLI 行为逐字节不变（回归测试锁定）；退出码→稳定 UI 错误码映射表。
