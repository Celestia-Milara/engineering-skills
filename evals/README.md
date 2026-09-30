# 可重放评测

这套材料把人工场景变成固定输入、隔离工作区和可追溯证据。准备成功只表示 fixture 可用，**不表示技能行为通过**。prepare / triggers / record 不启动模型；新增 run 必须由维护者明确执行，使用宿主账号运行隔离提示并采集原始证据，不修改来源仓库或发布任务。

## 包验证

验证工具使用 Python 3.10+ 与 PyYAML。使用技能本身不需要安装它们。环境尚未提供 PyYAML 时，由维护者在自己的验证环境中安装声明的依赖：

```powershell
python -m pip install -r scripts/requirements.txt
python -B -X utf8 scripts/validate.py
python -B -X utf8 scripts/validate.py --json
python -B -X utf8 scripts/validate.py --skills decision-notes,implement-work
python -B -X utf8 -m unittest discover -s tests -v
```

[validate.py](../scripts/validate.py) 检查 frontmatter、目录名、普通 Markdown 本地链接、v2 来源清单、分发哈希、许可证和必需技能依赖。Markdown 检查跳过代码块和行内代码，支持行内及引用式链接；不解析 HTML 链接、不检查远程 URL 或标题锚点。`--skills` 检查所选技能的依赖闭包和可达资源；整包来源清单及分发哈希仍会验证。

来源验证是独立步骤，不默认依赖相邻仓库：

```powershell
python -B -X utf8 scripts/validate.py --source-root decision-notes=../decision-notes-skill --source-root mattpocock=../mattpocock_skills
```

`source_files[].sha256` 对应 `git show <commit>:<path>` 的原始 blob 字节；`distributed_sha256` 对应实际分发字节。工具只报告差异，**不会更新哈希来掩盖漂移**。Windows 工作树 CRLF 不用于核对来源 blob。

本库原创的 `git-work` 文件使用 `original` 处理方式和空 `source_files`；skill 来源的保留值 `original` 映射到根 MIT 许可证。验证器核对原创文件的分发哈希、来源声明与许可证，不要求虚构源 commit。可以运行 `python -B -X utf8 scripts/validate.py --skills git-work` 检查其独立安装边界；其他技能不依赖它。

负向测试在临时副本中故意修改分发内容、制造断链、移除必需技能与许可证，并验证检查失败。测试目录离开时清理，不修改实际 skills 或来源仓库。

## 场景与隔离

[scenarios.json](scenarios.json) 有 12 个场景，每个定义 fixture、用户输入、预期能力、正向断言和禁止行为：

| ID | 观察对象 |
| --- | --- |
| feature-implicit | 明确功能的实施与真实回归 |
| debug-explicit | 空 CSV 的实际复现、修复、API/CLI 验证 |
| review-untracked-explicit | 未跟踪新文件中的金额精度问题；只评审不修改 |
| interview-multiturn-explicit | 多轮回答产生新问题，未决冲突不被代答 |
| migration-authorized-explicit | 已授权迁移，SQLite 行为与决策取代链 |
| discussion-negative | 只讨论不实施、不生成文件 |
| copy-edit-negative | 文字小改不扩展成访谈、计划或测试工程 |
| handoff-implicit | 保存有证据的交接，不顺手修代码 |
| migration-planning-explicit | 授权目标保持 proposed，未实施时不取代当前 accepted |
| interview-experiment-explicit | 明确验证动作及阻塞范围后收束访谈，不伪报假设成立 |
| git-staged-preservation-explicit | 仅提交新功能与测试，保留用户已有 staged 内容和另一文件的 unstaged 修改 |
| git-dirty-validation-explicit | 只读检查 HEAD、index 与工作目录，验证结论不混用不同快照 |

先准备一个全新工作区：

```powershell
python -B -X utf8 evals/prepare.py debug-explicit --mode full --model ACTUAL_MODEL --runtime ACTUAL_RUNNER_VERSION --loading-mode explicit-path
```

[prepare.py](prepare.py) 默认在操作系统临时目录创建 `project/`，初始化该临时 Git 仓库，写入起点 commit，并应用场景的未提交修改。Git 场景通过 `staged_paths` 将指定文件暂存，另外保留 unstaged 修改；该字段只能指向项目内的相对路径。包含暂存设置的 fixture 使用局部合成 Git 身份，不改全局配置。仅该 fixture 的 Git commit 用于建立测试基线，不提交技能源码或用户项目。也可使用 `--output` 指定仓库外**尚不存在**的目录；不会覆盖已有运行。

每次输出包含：

- `project/`：交给执行 agent 的工作区。
- `prompt.txt`：原样交给执行 agent 的本轮请求。
- `rubric.json`：留给评估者的断言和后续用户回答，**不要预先交给执行 agent**。
- `run.json`：fixture/场景/技能包 SHA、分发清单 SHA、起点、文件快照、初始 index 条目和已跟踪差异的摘要哈希、模型和加载方式。初始状态始终是 `not_run`；index 摘要辅助核对初始状态，不代替完整 diff 或验证证据。

支持 `baseline`（不安装本套技能）、`upstream`（固定上游原版）、`minimal`（decision-notes + implement-work）和 `full`（全部技能）。显式场景只有在入口实际安装时才点名；上游 implement-work 映射到原版 implement，没有对应入口时不虚构替代。各模式共同业务请求和项目说明相同。独立工作区不能自动屏蔽全局技能、系统指令或记忆；比较时记录并控制这些差异。

`--host codex` 原样安装到 `.agents/skills/`；`--host claude` 安装到 `.claude/skills/`，并把共同项目说明另存为 `CLAUDE.md`。目录注入与目标宿主实际发现要分开，不用 Codex 目录假称 Claude 原生发现。

## 原始宿主执行层

先准备全新工作区，再显式执行 [run.py](run.py)：

```powershell
python -B -X utf8 evals/prepare.py copy-edit-negative --mode minimal --host codex --loading-mode native-discovery
python -B -X utf8 evals/run.py C:/TEMP/RUN --host codex --model ACTUAL_SUPPORTED_MODEL --loading-mode native-discovery --timeout 180
```

模型必须是该 CLI 与账号实际支持的标识。run 探测原生可执行文件的 version/help，用参数数组和 `shell=False` 启动，不接受 batch/shell 片段。Codex 使用 JSONL、`workspace-write` sandbox，忽略用户配置以避免继承其他 sandbox 设置；保留项目说明与 execpolicy。Claude 使用 stream-json、verbose、子 agent 文字及 hook 事件、项目 settings 和 `acceptEdits`；需要人工权限的操作在 no-prompt 模式被拒绝，不绕过批准。`--executable` 可提供明确的原生 exe。

这些宿主能力已对照 [Codex 非交互文档](https://learn.chatgpt.com/docs/non-interactive-mode) 与 [Claude headless 文档](https://code.claude.com/docs/en/headless)。版本变化时以实际 help 为准；不支持必需采集参数时拒绝启动，不能退回静默运行。

`execution/` 保存 prompt、argv、version/help 原件、stdout JSONL、stderr、耗时、退出状态、已知全局输入哈希和最终状态。按实际 session ID 查找会话，再核验 ID 与 cwd，仅复制唯一匹配的原始 session 字节和哈希；内部 schema 不稳定，找不到时记录缺口。token/工具事件只是可取得观测，累计与增量 usage 不可相加。

执行摘要还比较请求模型、sandbox 与原始 turn_context 的实际设置；匹配、不同或无法观察分别标注。请求 `workspace-write` 不证明实际可写，权限不一致的样本不进入实现成本对照。原生 Windows 已有沙箱但本次运行缺少选择时，可显式加 `--windows-sandbox elevated`（或已获准的 `unelevated`）；只覆盖当次配置，不安装、修改全局配置或自动重试。模式说明见 [Windows sandbox 文档](https://learn.chatgpt.com/docs/windows/windows-sandbox)。

执行前核对 fixture、HEAD/index、prompt 和 rubric 是否仍与准备记录一致；执行目录独占创建，既有证据不覆盖。超时或取消时终止本次进程树再取最终快照，失败也保留取得的原始输出。多轮场景暂不由这个单轮执行器启动，不一次性发送未来回答；沿用人工多轮流程或增加有录制能力的宿主驱动。

run 的执行状态和人工评分分开：CLI 成功退出仍保留 run.json 的 `not_run` / `not_observed`，评估者审核原始证据后再用 record 评分。只读最终快照不能排除写后删，sandbox 拦截不能直接算技能自觉守约；授权顺序需要相应消息/工具或 app-server 审批请求与响应的完整覆盖。

## 自动触发测试

[triggers.json](triggers.json) 固定 **28 条提示，中文/英文各 14 条**，覆盖十个入口、上下文检索和邻近负例：只规划、只评审、只讨论、文案小改，以及含“下次/计划”等词的普通翻译与一般解释。[triggers.py](triggers.py) 可列出提示或准备原生发现的全包工作区：

```powershell
python -B -X utf8 evals/triggers.py
python -B -X utf8 evals/triggers.py trigger-copy-en --host codex
python -B -X utf8 evals/run.py C:/TEMP/TRIGGER_RUN --host codex --model ACTUAL_SUPPORTED_MODEL --loading-mode native-discovery --timeout 180
```

期待、可选及禁止技能集合互斥且覆盖全部入口。标签只适用于本库 `full` 包，不用未安装入口给 baseline/minimal/upstream 打触发失败分；业务收益比较使用 scenarios。rubric 与选择标签在 actor 项目外，prompt 不注入技能名、路径或预期答案。使用 [官方技能评测分类](https://developers.openai.com/blog/eval-skills) 区分显式、隐式、上下文与负例。

触发证据需要目标宿主的实际技能可见性与原始工具加载记录，例如 Claude Skill 调用或 Codex 读取对应 SKILL.md。仅目录存在、目录清单暴露或最终自称使用不算加载；覆盖不足的选择判据保持 `not_observed`。加载成功也不证明范围守约，另评分实际行为。完整采样后才统计每技能 precision/recall、误触发和未观察比例，不把 prepared corpus 当作触发通过率。

本库暂保留正常自动选择。clarify/plan/implement 等是工作入口，decision-notes/tdd 等是可组合纪律；这一区分不等于禁用隐式调用。宿主的政策字段与维护方法见 [maintenance.md](../docs/maintenance.md)。

## 固定上游对照

```powershell
python -B -X utf8 evals/prepare.py migration-authorized-explicit --mode upstream --upstream-source ../mattpocock_skills --host codex --loading-mode explicit-path
```

从 sources.json 固定 commit 导出原版 `implement` + `tdd`，包括全部目录资源、UI 政策与许可证，并提供它们引用的 `code-review` / `codebase-design`。使用 `git show` 的源 blob，记录各 blob 哈希，不复制来源仓库当前未提交文件、不升级到 latest。额外项目 issue-tracker/setup 条件仍需披露，不擅自运行 setup。

固定上游 implement 禁止隐式调用且要求提交；tdd 的用户确认流程也与本版不同。保持原文，业务请求的“不提交”和既有授权优先。显式工作流收益与自动发现选择分开比较，不能把原版禁用隐式调用算作实现质量低。没有对应入口的上游场景只比较业务结果，不评价本版入口名召回率。

## 执行与记录

在隔离工作区执行 prompt，保存完整用户/agent/tool 轨迹。多轮访谈需由评估者在 agent 回答后依次发送 `user_turns`，不得一次性泄露未来回答。若需要额外用户回答，逐字记录并将其视为新运行条件。

宿主无法完整导出轨迹时，只保存实际取得的最终回复、产物或工具日志，并在 notes 说明缺口；受影响的过程判据标为 `not_observed`，不能把摘要改称完整轨迹。精确模型版本无法取得时如实标注该限制，该样本不用于模型或成本比较。

完成后，评估者结合 trace、实际代码、输出和文件差异逐项评分。`kind: forbidden` 的条目也用 `pass` 表示约束得到遵守。未观察到或无法判断记 `not_observed`，不能猜测为通过。可用以下命令写入一次性记录：

```powershell
python -B -X utf8 evals/record.py C:/TEMP/RUN --trace C:/TEMP/trace.txt --model ACTUAL_MODEL --runtime ACTUAL_RUNNER_VERSION --loading-mode explicit-path --criterion reproduction=pass --criterion regression=pass --criterion claim-boundary=pass --notes "逐项证据见 trace 的实际失败运行、修复后 API/CLI 检查及最终回复。"
```

[record.py](record.py) 要求每条 rubric 都被显式评分，并保留 trace 和最终文件快照；所有项通过才标为 `pass`，任何项失败标为 `fail`，其余为 `inconclusive`。它只记录人工评判，不自动证明 trace 真实或结论正确。模型名与运行器应填实际版本，不能用示例占位值。保留原始 trace；再次运行请创建新目录，不覆盖既有证据。

记录时必须保留该运行的 `project/`、可读取的基线 commit 和初始文件证据。HEAD 可以变化，便于把误提交行为记录为失败；丢失或搬迁工作区会报错。已有 `trace.txt` 只有在内容相同时才可复用，内容不同时拒绝覆盖。结果写入使用临时文件和原子替换，失败时保留先前记录；并发记录会被锁拒绝。

明确区分两类结论：显式路径或人工目录注入的独立 agent 测试只能验证**加载后的执行行为**，不能证明宿主会自动发现技能或按 description 隐式触发。只有在目标宿主真实发现技能、未人工点名或注入入口的运行，才可以评价自动选择；即便场景 ID 带 `implicit`，使用路径注入的那次运行也不属于隐式触发证据。

少量 forward 样本用于发现具体问题，不能证明整套方法优于基线。收益比较需同宿主、同模型、同提示、同 fixture 的 baseline/minimal/full 多次运行，记录选择准确率、行为通过率、误写入、验证真实性、交互轮次以及实际可取得的耗时/token。未运行的场景保持 `not_run`，不将准备成功或静态校验通过计为行为通过。

## 已保存的试用

[2026-09-29 记录](results/2026-09-29-smoke.json) 包含 5 个 full 模式、显式路径加载的单次试用：2 个 `pass`，3 个因原始过程证据不完整而为 `inconclusive`；另 5 个场景未运行。记录附实际证据文件、哈希、产物和可取得的测试输出。解读与限制见[验证记录](../docs/validation.md)，不能视作整套评测或对照实验已经通过。

[2026-09-30 Git 记录](results/2026-09-30-git-smoke.json) 包含两个新增场景的同类单次试用。父级核查提交范围、已有修改与暂存状态，并在最终提交快照复跑 8 个测试；只读场景的最终状态和验证对象说明也已核查。两例均缺少完整原始交互或工具轨迹，受影响的过程判据保留 `not_observed`，正式状态为 `inconclusive`，不把已核查的产物结果扩为整例通过。

公开记录已脱敏本机用户和路径；文件头及报告 `publication` 字段说明修改范围。`evidence_sha256` 对应公开字节，`original_evidence_sha256` 对应私有备份的原始字节，不能混用。私有原件不纳入 Git。

[宿主采集 smoke](results/2026-09-30-harness-smoke.json) 保存本轮真实 CLI 的精选摘要与原始字节哈希。原始 stdout/session 保留在私有临时目录，公开摘要本身不是完整轨迹。配置模型被 CLI 拒绝的样本不评分；另一次捕获完整工具调用并正式判为宿主只读限制导致的文字小改失败，不纳入技能质量或成本对照。28 条触发集尚未运行，记录保持 `not_run`。
