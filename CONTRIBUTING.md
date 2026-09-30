# 贡献与试用反馈

优先报告具体任务中的可复现问题。反馈包含所用技能和版本、用户请求、项目约束、实际与预期行为，以及可公开的脱敏证据。不要上传真实项目的密钥、客户数据或未获公开授权的代码。材料不足时明确标注，未运行的检查不要写成通过。

## 本地检查

维护工具需要 Python 3.10+、Git 和 PyYAML；仅使用 skills 不需要这些工具依赖。

```text
python -m pip install -r scripts/requirements.txt
python -B -X utf8 scripts/validate.py
python -B -X utf8 -m unittest discover -s tests -v
git diff --check
```

GitHub CI 在 Windows / Ubuntu、Python 3.10 / 3.12 上执行包校验与工具测试。CI 不运行模型行为评测，也不要求维护者本机的上游仓库。固定来源 blob 的独立核验方式见[评测说明](evals/README.md)。

修改技能时保留目录内 LICENSE，检查必需依赖和参考链接；对实质行为变化选择相关场景试用。先审核内容差异，再手动更新 `sources.json` 对应的分发哈希。不要通过改源哈希接受意外漂移，也不要用上游文件直接覆盖改编内容。

仓库普通文本使用 LF 换行；`skills/` 禁用 Git 自动换行转换，以保留清单记录的精确分发字节。编辑技能时不要无意重写换行；明确调整后需核对并更新分发哈希。评测工作区和未脱敏原始轨迹放在仓库外，或使用已忽略的 `evals/runs/`、`evals/private/`；人工精选的公开记录才放进 `evals/results/`。脱敏副本须说明修改范围，重新计算公开证据哈希，并保留原始证据哈希及私有备份。

## Git 提交与协作

维护本库的提交采用 Conventional Commits：`type(scope): description`。scope 优先使用 skill 名称，或 `templates`、`validation`、`evals` 等维护范围；新增能力用 `feat`、纠正行为用 `fix`、纯文档说明用 `docs`。标题简洁描述结果，正文解释必要的原因与取舍，不强制测试清单或 AI trailer。例如 `feat(git-work): add controlled commits and integration`。

一个提交完成一个逻辑变化，相关技能、参考、许可证、来源映射和分发哈希一起交付。开始前查看工作区及完整暂存内容，保留他人已有修改；提交前审核实际候选差异，不能把路径当作内容归属证明。共享 checkout 只有一个 Git 操作负责人，最终验证与提交期间暂停其他写入；独立任务需要隔离时明确 worktree 基线。

提交、push 和合并按任务或项目的既有授权执行，不因完成维护工作默认执行。验证对应实际候选内容；局部或部分暂存的检查不能冒充另一版本的通过结果，集成后另核对实际组合。完整工作方法见 [git-work](skills/git-work/SKILL.md)。

新原创技能使用本库 MIT 许可证，在 `sources.json` 记录 `original` 处理方式、空的 `source_files` 和分发哈希；不要挂到 Matt 或 Decision Notes 的来源上。项目模板保留两种入口：[AGENTS.example.md](AGENTS.example.md) 用于新项目填写后提取，既有项目用 [AGENTS.snippet.md](templates/AGENTS.snippet.md) 增量合并。改变底线或路由时同步两者，不复制完整模板的第二份正文。
