# AI Desktop Mode Launchers

为 **macOS 上的 Codex Desktop 和 Claude Desktop** 提供 API / 账号模式启动菜单。不是 Claude Code 终端启动器，也不是 ChatGPT 聊天客户端的 API 插件。

功能：切换登录方式、分别配置各模式代理、强制 API 网关使用 HTTPS，并在修改配置前保存本地备份。仓库不包含任何实际网关、代理、模型、账号或密钥。

## 使用

要求：macOS、Python 3.11+，以及已安装的对应桌面客户端。使用 macOS 自带的 `osascript` 和 `pgrep`；不适用于 Windows/Linux。

```sh
cp config.example.json config.json
chmod 600 config.json
# 编辑 config.json，填写自己的配置
./codex-mode
./claude-mode
# 或直接启动
./codex-mode api
./claude-mode account
```

可通过 `AI_DESKTOP_MODE_CONFIG` 指定其他本地配置文件。配置文件含密钥，必须保留在本地；默认 `config.json` 已被 Git 忽略。请勿提交备份、日志、数据库或真实凭据。脚本需要与 `launcher.py` 放在同一目录，可把仓库目录加入 PATH。

## 配置说明

- `app`：客户端应用路径；若实际安装路径不同，请修改。
- `api_base_url` / `api_key`：自己的 HTTPS 网关与令牌。Codex 网关必须支持 Responses API；Claude 网关必须支持 Anthropic Messages 协议，base URL 的路径按网关和客户端要求填写。
- Codex `api_model` / `account_model`：模型标识；账号模型为空则交由客户端选择。`ca_certificate` 可选，用于自定义 CA。
- Claude `models`：可选模型列表，第一项为默认；`auth_scheme` 使用 `x-api-key` 或 `bearer`，按网关要求设置。
- `api_proxy` / `account_proxy`：分别填写自己的代理 URL，空字符串表示直连。使用本地 HTTP 代理并不会取消 API 网关的 HTTPS 加密。
- Claude `cowork_egress_allowed_hosts`：可选沙盒出站域名列表；空列表不覆盖客户端默认策略，`["*"]` 表示开放所有域名，请自行决定。

Codex 共用 `home` 中的本地会话和项目配置。可选 `sync_thread_provider` 将 `state_5.sqlite` 中属于 `openai` / `ai_gateway` 的会话切换到当前提供商，执行前备份数据库；默认关闭。此功能依赖数据库结构，不保证跨版本或跨模型续聊兼容。

Claude 使用客户端第三方模式的 `Claude-3p/configLibrary` 配置，并启用原生会话导入/导出入口。**不会自动合并账号云端会话和 API 本地会话**。账号模式仍需在客户端完成登录。第三方模式、Cowork 和配置键支持取决于客户端版本，API 协议兼容也不代表所有客户端功能均可用。

启动时会退出对应客户端再切换配置，请先保存正在进行的工作。备份保留在被修改文件旁；恢复时退出应用后手动还原。公开版经过脱敏整理，不会读取原机器的私有认证文件或依赖私有辅助脚本。
