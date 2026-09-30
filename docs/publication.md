# GitHub 上传准备记录

准备日期：2026-09-29；首次上传日期：2026-09-30。当前是待真实项目反馈的试用版本，尚未发布版本标签。

## 已准备

- README 面向公开读者说明用途、安装、依赖和验证限制，移除只适用于原聊天的称呼。
- 根 MIT 许可证、上游版权与来源说明、贡献和试用反馈说明已就绪；技能及归档中的原始版权声明保留。
- `.gitignore` 排除凭据文件、环境、缓存及私有评测工作区；测试 fixture 的 `.agents` 决策笔记保留在上传清单中。
- `.gitattributes` 保持普通文本 LF，技能和许可证归档保留精确字节；CRLF 行尾按正常换行检查，不屏蔽实际尾随空格。
- 公开评测记录仅脱敏本机用户与路径，原件另存仓库外；原始及公开副本的哈希分别保留，结果和评分未改。
- GitHub Actions 在 push 到 main、PR 或手动触发时，执行 Windows / Ubuntu、Python 3.10 / 3.12 的校验和工具测试。仅使用 `contents: read`，不执行模型评测或部署。

Actions 依赖经官方仓库核对后固定完整 commit SHA，参照 [GitHub 安全使用说明](https://docs.github.com/en/actions/reference/security/secure-use)。配置见 [validate.yml](../.github/workflows/validate.yml)，依赖来自 [checkout](https://github.com/actions/checkout) 和 [setup-python](https://github.com/actions/setup-python)。

## 实际检查

- 从 Git 暂存区导出干净目录，包校验通过：9 个技能、14 个分发哈希、9 个技能许可证，以及全部可检查的本地链接。
- 同一导出目录执行 17 个工具回归测试，全部通过；不依赖当前项目的未暂存文件或相邻来源仓库。
- 核查暂存区的 14 个分发哈希和 5 个公开证据哈希，均匹配。
- 对暂存文件做常见 GitHub / API 凭据、私钥头和已知本机身份字符串的模式扫描，未发现匹配。该扫描不是对任意敏感内容的完整证明。
- `git diff --cached --check` 通过，测试 fixture 未被误忽略。

本地检查环境为 Windows、Python 3.12.8。首次上传后，[GitHub Actions 托管运行](https://github.com/Celestia-Milara/engineering-skills/actions/runs/36654445317) 的 Windows / Ubuntu、Python 3.10 / 3.12 四组任务全部通过。

## 首次上传

仓库最初以私有形式创建并上传 `main` 分支。公开前复核了全部提交的文件内容与作者邮箱，以及 Actions 日志、发布物和产物；未发现凭据或本机身份信息。2026-09-30 将 [Celestia-Milara/engineering-skills](https://github.com/Celestia-Milara/engineering-skills) 设为 public，并通过匿名请求验证可访问。真实项目试用反馈和版本标签留待后续决定。
