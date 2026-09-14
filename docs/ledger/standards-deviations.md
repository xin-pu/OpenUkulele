# 标准偏差台账

登记本项目对 `docs/standards-reference.md` 所采纳标准的**一次性偏差**。每条必须有负责人与复查日期；标准若因此需要演进，转记共享改进台账，不在本文件重复。

| ID | 标准条款 | 偏差 | 原因 | 风险 | 负责人 | 复查日期 | 状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DEV-001 | `github-workflow/issue-lifecycle.md`：分支命名 `<type>/<issue-number>-<short-kebab-title>`，且 Issue 先于分支 | 分支 `feat/wpf-desktop` 无 issue 编号，且先于 GitHub Issue 创建 | 建分支时远程 GitHub 无法连接，拿不到 issue 编号（见 `docs/design/2026-09-14-wpf-desktop-mvp.md` §2） | 追溯性变差；PR 合并描述需显式 `Closes #2` 弥补关联 | xin-pu | 2026-10-15 | 已补建 Issue #2；PR 描述将以 `Closes #2` 关联 |
| DEV-002 | `issue-lifecycle.md`：新 Issue 分支应从当前默认分支拉出 | 分支基线为 `b4f0b0b`（PR #1 合并前的功能末提交），而非 master 的合并提交 `89bbd9d` | 分支开工时 PR #1 尚未合并；`b4f0b0b` 与 master 内容等价（仅缺 merge 节点，已用 merge-base 验证） | 图结构上多一个共同祖先而非直接基于 master tip；对本分支 PR diff 无影响 | xin-pu | 2026-10-15 | 已确认无内容分叉；合并本分支 PR 时正常走 GitHub merge |
