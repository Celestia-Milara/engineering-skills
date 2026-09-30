# 维护技能包

维护工具使用 Python 3.10+、Git 和 [PyYAML](../scripts/requirements.txt)。仅使用技能无需安装这些工具或 Node.js。

```text
python -B -X utf8 scripts/validate.py
python -B -X utf8 scripts/validate.py --skills decision-notes,implement-work
python -B -X utf8 -m unittest discover -s tests -v
git diff --check
```

包检查验证格式、链接、来源、分发哈希、许可证、依赖与共享条款，不证明模型行为。固定提交的来源 blob 独立核验和真实宿主评测见 [evals/README.md](../evals/README.md)；实际结果见 [validation.md](validation.md)。

## 来源与哈希

[sources.json](../sources.json) 的 `source_files[].sha256` 是固定 commit 的 Git blob 字节哈希，`distributed_sha256` 是当前分发文件字节哈希。先审核修改差异与处理方式，再更新分发哈希；源哈希只随明确的来源升级更新。校验器不自动接受漂移。

`verbatim` 表示字节一致，`translated` 表示仅翻译，改变上游规则属于 `adapted`。本库原创文件标为 `original`，`source_files` 为空数组；原创 skill 的 `skill_sources` 使用 `original` 并映射到根 MIT 许可证。原创参考文件可以随改编技能分发，不虚构上游来源。

不要用上游更新直接覆盖改编技能。按清单固定版本比较源文件，判断哪些变化应吸收，保留各技能目录和 `licenses/` 的版权与许可证。

## 共享规则

Git 底线只在 [git-safety.md](../skills/git-work/references/git-safety.md) 维护。为保留技能独立安装与无技能项目模板的能力，五个入口和两个 AGENTS 模板各自携带必要副本；不增加 `git-work` 必需依赖。

清单 `shared_rules` 登记 canonical 和 copies。成对的 `shared-rule: git-safety` HTML 标记圈定全文；验证器逐字节检查所有块，并拒绝缺标记、未登记副本或内容漂移。即使刷新某副本的分发哈希，差异仍会失败。

修改底线时先改 canonical，审核后同步登记的块，保留模板外的项目占位字段，再更新受影响分发哈希并验证。仅修改入口流程或项目字段时不重写共享块。复制到目标项目后的约定由目标项目维护，不受本仓库检查自动更新。

多人条件参考保存在 [implement-work/references/team.md](../skills/implement-work/references/team.md)，入口按情境读取。资源拆分只降低入口体积；是否减少 token 或交互必须通过同宿主、同模型的小任务对照测量。

## 调用与试用

本库仍允许宿主自动选择全部技能；入口型与纪律型描述工作角色，不代表禁用模型调用。明确点名和自然语言发现分别评测，不能用显式加载结果证明自动触发有效。

Codex 的显式调用政策位于 `agents/openai.yaml` 的 `policy.allow_implicit_invocation`；Claude Code 使用 frontmatter 的 `disable-model-invocation`，不是通用 YAML 字段。需要改变调用政策时分别适配目标宿主并更新触发标签，不把某宿主字段直接塞入所有分发入口。[Codex 技能文档](https://learn.chatgpt.com/docs/skills)、[Claude Code 技能文档](https://code.claude.com/docs/en/skills)。

原始模型输出与宿主会话日志保存在仓库外，人工审核和脱敏后才精选到 `evals/results/`。缺失过程证据时保留 `not_observed`；模型退出成功、工具回归测试或准备 fixture 均不算技能行为通过。贡献流程见 [CONTRIBUTING.md](../CONTRIBUTING.md)。
