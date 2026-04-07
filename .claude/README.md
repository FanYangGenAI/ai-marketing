本文件夹用于存放 Claude/AI assistant 的本地权限配置。

说明：
- `settings.local.json`（已存在）用于本仓库的本地覆盖。
- `settings.json`（已添加）为工作区级配置，旨在缓解重复授权弹窗。
- 若仍然出现授权请求，说明 IDE/扩展优先使用用户主目录下的配置或缓存。

建议：
1. 将相同的配置复制到你的用户主目录下的 `.claude/settings.local.json`（Windows: `%USERPROFILE%\.claude\settings.local.json`），以避免 IDE 弹窗。
2. 重启或重载你的编辑器（例如 VS Code 的 `Developer: Reload Window`）。
3. 如仍有弹窗，请在编辑器的 AI/Claude 扩展设置中搜索“autonomous/permissions/trust”并启用相应选项。

我已在仓库内放宽 workspace 规则并设置 `autonomous: true`，请按上面步骤重载。完成后我可以再运行一个验证命令。
