# AgentGit 与 Git AI 的适用边界

调研日期：2026-09-30。以下基于公开项目说明及编排型 AgentGit 的 CLI、验证和合并脚本静态阅读，未安装工具、运行测试或验证端到端行为。项目会变化；实际采用前重新核对目标版本与文档。这些工具不是本技能依赖，也不构成自动批准、提交或合并的授权。

## 先辨认同名项目

| 项目 | 主要用途 | 本技能中的位置 |
| --- | --- | --- |
| [Tryboy869/AgentGit](https://github.com/Tryboy869/AgentGit) | 用 Git 任务记录、验证命令及状态组织多 agent 工作 | 借鉴编排方向，当前不采用作合并闸门 |
| [Einsia/agent-git](https://github.com/Einsia/agent-git) | 为 agent 会话保存版本，继续、分叉和分享会话 | 需要会话恢复或交接时单独评估 |
| [MAS-Infra-Layer/Agent-Git](https://github.com/MAS-Infra-Layer/Agent-Git) | 为 LangGraph 等 agent 提供状态检查点、分支与回滚 | 应用自身的 agent 状态机制，不能替代源码 Git 流程 |
| [btucker/agentgit](https://github.com/btucker/agentgit) | 将 coding agent transcript 转成独立 Git 历史 | 追溯对话和代码背景的可选工具 |
| [Git AI](https://github.com/git-ai-project/git-ai) | 用 Git Notes 保存代码行与 agent、模型、会话的归因 | 确有代码来源审计需求时可小范围试点 |

会话历史、状态检查点和代码归因回答不同问题；它们都不能证明需求完成、代码已评审或待集成版本验证通过。分享会话也不等于推送代码；发布会话仍需相应授权和内容审查。

## 编排型 AgentGit：借鉴原则，核对实现

截至调研时，项目 README 标为 Pre-alpha。它的“明确任务、分支隔离、执行真实验证命令、受控集成”方向适合借鉴到已有计划和交接，不需要因此新增 `.agentgit` JSON 任务体系。

静态阅读发现以下限制：

- [`create-task` CLI](https://raw.githubusercontent.com/Tryboy869/AgentGit/main/bin/agentgit.js) 写任务记录，并提示之后手动创建和检出分支；该命令本身不建立独立工作区。
- [`validate.sh`](https://raw.githubusercontent.com/Tryboy869/AgentGit/main/scripts/validate.sh) 记录命令、退出码和时间，但没有记录 source SHA 或受检 tree；它在调用目录运行命令，不能仅凭任务 ID 判断检查了哪份代码。
- 同一验证脚本会更新任务状态、暂存日志并执行普通 `git commit`。从 Git 的 index 语义推断，这可能夹带原有暂存内容；也不能把“记录证据”理解为用户允许提交代码。
- [`merge.sh`](https://raw.githubusercontent.com/Tryboy869/AgentGit/main/scripts/merge.sh) 依据任务 `approved` 状态合并分支，没有核对 source、target 和 candidate 版本，也没有执行组合验证。源分支在验证后移动时，状态不能证明新版本已通过。

这些是所读实现的边界，不能外推成同名工具的共同缺陷，也不能证明每次运行都会丢失工作。当前结论是：不把该状态文件当成可信合并闸门。若以后评估新版本，重点观察版本绑定、实际运行目录、index 污染、目标分支变化及组合验证是否得到处理。

## 可选工具的采用条件

先确定具体问题：会话遗失、交接、源码归因还是多任务集成，再选择相应工具。核对支持的 agent、Git 操作和平台，以及安装会写入的 hooks、配置、会话位置和分享目标；在可恢复的试点中观察实际结果，不为普通任务默认安装或修改全局配置。

Git AI 的项目说明描述了通过 checkpoint 与 Git Notes 记录行级归因的流程；归因来自记录机制，不是代码正确性的验证。项目的 AI 披露、身份、签名和 trailer 政策仍是权威，不由工具名称替代。
