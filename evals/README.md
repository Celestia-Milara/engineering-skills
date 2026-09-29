# 可重放评测

这套材料把人工场景变成固定输入、隔离工作区和可追溯证据。准备成功只表示 fixture 可用，**不表示技能行为通过**。脚本不会启动模型、付费 CLI、发布任务或修改来源仓库。

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

负向测试在临时副本中故意修改分发内容、制造断链、移除必需技能与许可证，并验证检查失败。测试目录离开时清理，不修改实际 skills 或来源仓库。

## 场景与隔离

[scenarios.json](scenarios.json) 有 10 个场景，每个定义 fixture、用户输入、预期能力、正向断言和禁止行为：

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

先准备一个全新工作区：

```powershell
python -B -X utf8 evals/prepare.py debug-explicit --mode full --model ACTUAL_MODEL --runtime ACTUAL_RUNNER_VERSION --loading-mode explicit-path
```

[prepare.py](prepare.py) 默认在操作系统临时目录创建 `project/`，初始化该临时 Git 仓库，写入起点 commit，并应用场景的未提交修改。仅该 fixture 的 Git commit 用于建立测试基线，不提交技能源码或用户项目。也可使用 `--output` 指定仓库外**尚不存在**的目录；不会覆盖已有运行。

每次输出包含：

- `project/`：交给执行 agent 的工作区。
- `prompt.txt`：原样交给执行 agent 的本轮请求。
- `rubric.json`：留给评估者的断言和后续用户回答，**不要预先交给执行 agent**。
- `run.json`：fixture/场景/技能包 SHA、分发清单 SHA、起点、文件快照、模型和加载方式。初始状态始终是 `not_run`。

支持 `baseline`（不安装本套技能）、`minimal`（decision-notes + implement-work）和 `full`（全部技能）。显式场景只有在技能实际安装时才给 prompt 加技能名与路径；其他模式使用相同业务请求。三种模式的共同项目说明相同。独立工作区不能自动屏蔽宿主的全局技能、系统指令或记忆；比较时必须记录并控制这些环境差异。

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

公开记录已脱敏本机用户和路径；文件头及报告 `publication` 字段说明修改范围。`evidence_sha256` 对应公开字节，`original_evidence_sha256` 对应私有备份的原始字节，不能混用。私有原件不纳入 Git。
