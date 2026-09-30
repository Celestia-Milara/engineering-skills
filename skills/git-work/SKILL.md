---
name: git-work
description: "处理已授权提交、并行工作区、分支集成、冲突或恢复（git commit / worktree / merge / conflict / recovery），保护变更归属与暂存状态并绑定验证对象。普通任务完成不自动触发提交；可独立安装。"
---

# Git Work

让本任务的变化、实际交付内容和验证证据对应起来。读取目标项目的协作说明、提交约定和相关既有决策；已安装 decision-notes 时可按需使用，不要求安装其他技能或工具。

## 工作区与授权

按 [Git 底线](references/git-safety.md) 的工作区保护、提交与授权章节确认本次动作，并检查正在进行的 merge / rebase 等操作。这份资源是跨技能规则的唯一维护源，其他入口分发一致副本，不要求它们安装 git-work。

## 构造提交

按 [Git 底线的提交章节](references/git-safety.md#提交与授权) 构造候选变化；无关重构或全局格式化另行处理。需要并行隔离或集成时读取 [parallel-and-integration.md](references/parallel-and-integration.md)。

## 验证与交付

按 [Git 底线](references/git-safety.md#验证对象) 的验证对象与并行集成章节完成检查、关联证据和安全清理。交付说明变化、实际检查及其对象、未解决限制和当前 Git 状态。

仅在用户询问 AgentGit / Git AI 或任务确需评估这些工具时读取 [tools.md](references/tools.md)。普通 Git 操作不加载工具调研，也不自动安装依赖。
