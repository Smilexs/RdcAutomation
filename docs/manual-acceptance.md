# rdc-auto 手动验收

请在已安装 MuMu12 的 Windows 机器上执行以下验收步骤。

## 构建命令exe
```
cd E:\ZSGame\AIProjects\RdcAutomation

python -m pytest -v
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

## 手动测试

```
.\dist\rdc-auto.exe setup

.\dist\rdc-auto.exe attach

.\dist\rdc-auto.exe capture --out D:\RdcCaptures

.\dist\rdc-auto.exe export D:\RdcCaptures\<你的文件>.rdc --assets both --out D:\RdcExports


.\rdc-auto.exe export C:\Users\zhengzs22120506\Downloads\Test\mumu12_20260617_160827.rdc --assets textures --out C:\Users\zhengzs22120506\Downloads\Test\outputs


```

### 环境设置

1. 运行 `rdc-auto setup`。
2. 确认 RenderDoc v1.44 已被检测到，或已由安装流程安装。
3. 确认 RenderDocMCP 安装程序是从 GitHub 最新 release 下载的 `RenderDocMCP-Setup-*.exe`。
4. 确认 RenderDocMCP 已安装，并且 `config.json` 记录了已安装的可执行文件路径。
5. 按提示输入 MuMu12 根目录；该目录必须直接包含 `nx_main`。
6. 确认 `<MuMu12Root>\nx_main\MuMuNxMain.exe` 存在。

### 启动捕获环境

1. 如果 MuMu12 正在运行，先关闭它。
2. 将 MuMu12 图形 API 设置为 Vulkan。
3. 运行 `rdc-auto attach`。
4. 确认 MuMu12 是通过 RenderDoc 启动的。
5. 确认 CLI 输出了有效的 active session id。

### 截帧

1. 在 MuMu12 中手动进入需要截帧的游戏画面。
2. 运行 `rdc-auto capture`。
3. 选择捕获文件输出目录。
4. 确认已生成 `.rdc` 文件。

### 导出资源

1. 运行 `rdc-auto export`。
2. 选择前面捕获到的 `.rdc` 文件。
3. 资源类型选择 `both`。
4. 选择导出目录。
5. 确认已写出 `textures`、`meshes`、`raw_mesh_json` 和 `manifest.json`。
6. 确认导出的 PNG 文件可以正常打开。
7. 确认导出的 OBJ/MTL 文件可以导入到 DCC 工具或模型查看器中。

### 负向检查

1. 临时配置或安装非 v1.44 的 RenderDoc，确认 `rdc-auto setup` 不会把它当作 v1.44 接受。
2. 在 `config.json` 中写入过期的或手动构建的 RenderDocMCP 可执行文件路径，确认 `rdc-auto setup` 会重新从最新 `RenderDocMCP-Setup-*.exe` release 资源安装。
3. 手动启动 MuMu12 后，在不带 `--force` 的情况下运行 `rdc-auto attach`，确认 CLI 会要求你关闭 MuMu12，而不是直接终止进程。
4. 清空或让 `config.json` 中的 active session 失效后运行 `rdc-auto capture`，确认 CLI 会提示是否执行 attach。
5. 在 capture 过程中断开或停止 RenderDocMCP，确认 CLI 会输出可操作的超时或 MCP 错误，并且不会使用 `Unexpected error` 前缀。
6. 使用一个至少有一个贴图或模型导出失败的 `.rdc` 文件，确认 `manifest.json` 会记录失败资源，同时其他资源仍会继续导出。
