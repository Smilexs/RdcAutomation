# RdcAutomation HTML UI Prototype

这是一个纯前端交互原型，入口文件：

```text
html-ui-prototype/index.html
```

可以直接双击打开，或在浏览器里打开该文件。

## 当前范围

- 页面切换：工作台、环境设置、捕捉 RDC、资源导出、AI 助手、日志与配置。
- RenderDoc MCP 已移动到环境设置页内，作为独立卡片展示安装路径、版本、运行状态、扩展状态和启动/关闭控制。
- 顶部状态栏显示 MCP 版本，并将 MCP 状态放在最后。
- 资源导出页仍保留导出前的 MCP 状态卡，用于快速确认和控制 MCP。
- 模拟按钮响应：toast、日志、进度条、状态更新。
- 模拟流程：setup、MCP 启动/关闭/重启、attach、capture、export、指定 EID 导出、AI 对话。
- 不执行真实 `rdc-auto` 命令。
- 不读取或写入本机文件、注册表、进程、RenderDoc、MuMu12。

## 后续接入真实功能时的边界

普通浏览器静态 HTML 不能直接执行本机 exe，也不能稳定访问完整本机路径或管理进程。要接入 `rdc-auto` 的真实执行能力，需要增加一个本地执行层，例如：

- Tauri / Electron 桌面壳。
- Python 本地后端服务。
- PyWebView。

前端按钮通过 IPC 或 HTTP 调用本地执行层，本地执行层再调用现有 Python service 或 `rdc-auto.exe`。
