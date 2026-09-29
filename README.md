# Engineering Skills

以 **decision-notes 为长期决策记录**，结合 Matt Pocock 的小步开发方法，供以 **TypeScript / Python 为主的个人项目及 3–4 人小团队**按需使用，也保留对其他技术栈的适用性。

当前处于真实项目试用阶段。静态检查和工具测试已通过；已保存的行为试用为少量样本，完整结果与限制见[验证记录](docs/validation.md)。

本版独立维护改编内容，不改两个来源仓库。无需工单系统、固定语言或包管理器，也不要求每项任务先写文档。来源、处理方式及源文件与分发文件的哈希分别记录在 `sources.json`。

## 组成

| Skill | 什么时候用 | 来源与处理 |
| --- | --- | --- |
| [decision-notes](skills/decision-notes/SKILL.md) | 改代码前检索约束；维护不能从代码推导的原因 | 改编 Decision Notes，明确已授权与已生效的区别 |
| [clarify-work](skills/clarify-work/SKILL.md) | 项目初期深入访谈、拷打需求与设计原因；局部任务也可澄清 | 改编 grilling + domain-modeling，保留多轮设计树追问 |
| [plan-work](skills/plan-work/SKILL.md) | 需求已清楚，需要可验证的实施切片 | 改编 to-spec + to-tickets，合并为按规模展开的计划 |
| [implement-work](skills/implement-work/SKILL.md) | 已授权实现功能、修复或重构 | 改编 implement，小步实现并验证 |
| [review-work](skills/review-work/SKILL.md) | 评审未提交修改、分支或 PR | 改编 code-review，需求和工程质量分别检查 |
| [debug-work](skills/debug-work/SKILL.md) | 故障原因不明、行为错误或性能回退 | 改编 diagnosing-bugs，以复现和证据推进 |
| [tdd](skills/tdd/SKILL.md) | 用户要求测试先行，或行为变化适合自动回归 | 改编入口与参考，统一行为断言、替身及集成证据的边界 |
| [codebase-design](skills/codebase-design/SKILL.md) | 模块接口、复杂性归属、可测试性需要设计 | 改编 Matt 的深模块方法，将适用条件与执行退路随技能分发 |
| [handoff-work](skills/handoff-work/SKILL.md) | 用户需要跨会话继续或交接当前工作 | 改编 handoff，把恢复入口留在项目内 |

“改编”表示独立维护的技能，不会同步覆盖来源仓库。`decision-notes`、`tdd` 和 `codebase-design` 沿用来源名称，接入时选择本版或来源版之一；切换时比较规则，避免同名入口并存。

## 怎么用

日常直接描述任务即可；也可以明确点名技能。下面的调用文字表达意图，不依赖某一种 Agent 的命令语法。

| 场景 | 使用路径 | 通常留下什么 |
| --- | --- | --- |
| 拼写、小样式、简单局部修复 | decision-notes 检索 → implement-work | 修改与必要验证，无新增文档 |
| 从模糊想法启动项目 | clarify-work 深入访谈 → plan-work（需要时） | 需求理解、设计理由、真实取舍与待验证假设 |
| 目标还模糊的新功能 | clarify-work → plan-work（需要时）→ implement-work | 可选计划、实现、验证 |
| 已有明确验收标准 | implement-work，按需使用 tdd | 行为实现及回归测试 |
| 莫名失败或变慢 | debug-work | 复现、原因证据、修复或明确的待验证结论 |
| 模块越来越难改 | codebase-design → plan-work / implement-work | 有依据的接口调整；必要时更新决策笔记 |
| 只想检查代码 | review-work | 可定位、有影响说明的发现，不自动改代码 |
| 下次继续 | handoff-work | 当前事实、验证记录、下一步与文件链接 |

这里的箭头表示可以组合，不是每次强制执行的流水线。只请求讨论或计划时，在相应产物处结束；已授权实现时不为每一步重新请求批准。

例如：

```text
用 clarify-work 拷打我这个新项目的想法，通过多轮提问梳理需求和设计原因，先不要实现。
用 clarify-work 帮我把“支持离线编辑”的行为边界想清楚，先不实现。
用 plan-work 把已经确定的导入功能拆成能逐步验证的切片。
用 implement-work 完成这个计划的第一个切片。
用 debug-work 查出重复保存的原因，再修复并验证。
用 review-work 检查当前尚未提交的所有改动，包括新增文件。
```

## 接入项目

这是技能源文件库，尚未替你安装到其他项目或全局目录。复制到目标项目后使用：

1. 将选中的 `skills/<name>/` **整个目录**复制到目标项目的 `.agents/skills/<name>/`，保留参考文件、元数据和 LICENSE。不要把本仓库根目录复制进去。
2. 已有同名 skill 时先比较内容，选择一个版本；本版 decision-notes 已调整生命周期语义，不把它当作原版的逐字节副本。
3. 把 [AGENTS.snippet.md](templates/AGENTS.snippet.md) 中与已安装技能对应的条目合并进项目 `AGENTS.md`，保留项目原有说明和命令。
4. 新项目无需创建空的 CONTEXT、计划或决策文件。现有决策笔记和已接入的校验器继续使用。

最小组合：`decision-notes` + `implement-work`。需要测试先行和评审时再加 `tdd`、`review-work`；也可以一次复制全部 9 个技能。必需依赖如下，其他技能缺席时入口有直接执行相应检查的退路：

| 选择的技能 | 一并安装 |
| --- | --- |
| clarify-work、plan-work、implement-work、review-work、debug-work、tdd、handoff-work | decision-notes |
| decision-notes、codebase-design | 无其他必需 skill |

`codebase-design` 的测试保留条件与无多 agent 时的退路已在技能内定义，AGENTS 片段只提供项目级入口。

不需要为使用技能安装 Node.js。需要决策笔记自动校验时，从原 `decision-notes-skill/template/` 按原项目说明接入相应校验器，合并配置，**不要覆盖目标项目的 package.json、CI 或 AGENTS.md**。本库不复制第二套校验器，避免规则与实现分叉。

TS / Python 项目先从真实配置找到命令，参考 [TS / Python 验证入口](skills/implement-work/references/ts-python.md)。不预设每个项目都有同一套 npm、uv、pytest 或静态检查工具。

3–4 人合作时只增加几个实际需要的信息：任务负责人、前置依赖、验收标准、共享接口与迁移影响，以及交付验证。详见 [小团队协作](docs/teamwork.md)。只有多人拆分的工作才需要给切片标负责人；个人小任务不填表。

## 文档边界

| 位置 | 只保存什么 |
| --- | --- |
| 项目 `AGENTS.md` | 项目入口、真实命令和必要协作约定 |
| `.agents/decisions/` | decision-notes 定义的长期原因与约束 |
| 已有领域词汇表；没有时为 `CONTEXT.md` | 术语、业务含义、概念关系，不放技术方案 |
| 已有需求位置；没有时为 `.agents/work/<主题>/requirements.md` | 访谈形成的目标、场景、范围、验收、假设及未决问题；关键决策只引用笔记 |
| 已有计划位置；没有时为 `.agents/work/<主题>/plan.md` | 需求来源链接、实施切片及切片级验证、进度和开放问题 |
| 同任务目录的 `handoff.md` | 恢复上下文所需的当前状态与链接 |

新项目不另建 `docs/adr/`。已有 ADR 的项目先读现有内容，不批量迁移；同一决策保留一个维护位置，新决策由 decision-notes 管理。计划可以引用决策，不复制一份决策正文。

需求范围与需求级验收只有一个维护来源，优先现有 requirements 或工单；只有聊天输入时可由回复或计划保存简明要求，无需额外建文件。计划引用已有独立来源并补充切片级验证。执行中变更验收时按已有写入授权同步来源及受影响切片；暂未同步则标明差异。决策状态描述已生效范围，实施授权沿用用户指令；已授权但未实施的目标不能冒充当前事实。

`.agents/work/` 是本方案的本地文件默认值，复用项目已有位置优先。跨机器交接需要自行按项目惯例纳入版本控制；文件存在本机不代表已经提交或共享。

## 设计与维护

- [设计取舍与来源映射](docs/design.md)：为什么保留、改编或暂不引入某些技能。
- [场景检查清单](docs/scenarios.md)：含 TS、Python 和多人集成场景，供后续真实项目试用。
- [来源版本与哈希](sources.json)：固定来源版本、文件处理方式及源文件/分发文件的独立哈希。
- [验证记录](docs/validation.md)：本版实际执行的检查和限制。
- [行为评测](evals/README.md)：固定场景、隔离项目与对照运行方式。
- [GitHub 上传准备](docs/publication.md)：公开材料、暂存内容检查与待上传事项。

维护本库时使用 Python 3.10+，按 [校验依赖](scripts/requirements.txt) 准备已有环境，再执行：

```text
python scripts/validate.py
python scripts/validate.py --skills decision-notes,implement-work
python -m unittest discover -s tests -v
```

检查脚本验证格式、链接、来源清单、分发哈希、许可证和必需依赖，不证明模型实际行为。选装检查不安装技能。仅使用技能不需要安装此维护工具的依赖。

不要用上游更新直接覆盖改编技能。先对照 `sources.json` 的版本与修改说明，挑选需要的变化；原样复用的文件可逐文件比较后更新。许可证保留在各技能目录及 `licenses/` 中。

`sources.json` 的 `source_files[].sha256` 是固定 commit 的 Git blob 字节哈希，`distributed_sha256` 是当前分发文件字节哈希。修改后审核差异、确认处理方式，再更新分发哈希；源哈希只随明确的来源升级更新。`verbatim` 表示字节一致，`translated` 表示仅翻译，改变规则属于 `adapted`。校验器不会替你接受文件漂移。

## 许可证与贡献

本项目采用 [MIT 许可证](LICENSE)，保留 [上游版权与来源说明](THIRD_PARTY_NOTICES.md)。提交改进前请阅读[贡献说明](CONTRIBUTING.md)；真实项目试用反馈请提供任务范围、实际行为、预期行为及经过脱敏的证据。
