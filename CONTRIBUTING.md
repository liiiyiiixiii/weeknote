# 参与贡献

感谢你改进 Weeknote。请让每个变更保持小而清晰，并确保公开内容不包含任何真实业务数据或基础设施信息。

## 开发环境

需要 Python 3.12、Node.js 24、npm，以及用于本地密钥扫描的 Gitleaks。

```bash
git clone https://github.com/liiiyiiixiii/weeknote.git
cd weeknote
make setup
cp backend/.env.example backend/.env
```

只有需要实际调用模型时才填写本地 `.env`；大部分测试不需要 API key。

## 分支与提交

- 从最新 `main` 创建短生命周期分支，例如 `fix/export-heading` 或 `feat/template-preview`
- 一个提交处理一个连贯问题，提交信息使用祈使语气并说明结果
- 不要提交生成的数据库、日志、缓存、归档、证书、生产配置或 `.env`
- 如果密钥曾经进入提交历史，仅删除文件不够：必须立即吊销并轮换密钥

## 格式与测试

提交前运行：

```bash
make format
make check
```

后端保持 Ruff 格式和 lint 全绿，前端使用仓库锁定版本的 Prettier。新增行为需要回归测试；总分支覆盖率不得低于 75%。API、环境变量、SQLite schema、静态资源路径或启动命令的破坏性变更必须先在 Issue 中讨论。

## Pull Request

PR 描述应包含：问题背景、实现方式、验证结果、兼容性影响，以及涉及界面时的脱敏截图。请确认 CI 全部通过，并逐项完成模板中的安全检查。

维护者可能要求拆分过大的 PR。合并即表示你同意按项目 MIT License 提供贡献。
