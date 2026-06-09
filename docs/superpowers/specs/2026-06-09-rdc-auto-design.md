# rdc-auto Design

Date: 2026-06-09

## Goal

Build `rdc-auto`, a Codex Skill plus standalone Windows CLI that helps a user set up a RenderDoc capture workflow for MuMu12, capture the current emulator frame, and export textures and meshes from `.rdc` captures.

The first release targets a minimal reliable loop:

```text
setup -> attach -> capture -> export
```

The Skill is named `rdc-auto`. The CLI executable is `rdc-auto.exe`.

## Scope

In scope for the first release:

- Install or verify RenderDoc v1.44 on Windows.
- Clone or update `https://github.com/Smilexs/RenderDocMCP.git`.
- Install the RenderDoc MCP RenderDoc extension and MCP server.
- Confirm the MuMu12 root installation directory.
- Launch MuMu12 through RenderDoc using Vulkan.
- Let the user play manually in MuMu12 after launch.
- Capture the current emulator frame to an `.rdc` file when requested.
- Export textures as PNG.
- Export meshes as OBJ/MTL, using MCP mesh JSON as an intermediate format if needed.
- Provide a Codex Skill that maps user intent to the CLI commands.

Out of scope for the first release:

- Supporting emulators other than MuMu12.
- Supporting graphics APIs other than Vulkan for MuMu12 capture.
- A GUI.
- A persistent tray app or global hotkey.
- Automatic editing of unknown MuMu12 graphics configuration files.
- Full RenderDoc analysis beyond texture and mesh export.

## Delivery Model

The implementation uses Python for source development, but ordinary users run a packaged single-file Windows executable. Users should not need Python installed for the normal path.

Developer fallback:

- Source mode can run with Python.
- A `bootstrap.ps1` script can install or locate Python for developer use.
- The Skill and user-facing instructions default to the packaged exe.

Important boundary: the CLI executable itself must not require a user-installed Python, but RenderDoc MCP is a Python/uv project. `rdc-auto setup` must therefore provide or install a managed runtime for MCP when needed. This runtime should live under the tool-managed data directory and should not depend on a global Python installation.

## Commands

The first release exposes short commands:

```text
rdc-auto setup
rdc-auto attach
rdc-auto capture
rdc-auto export
```

Scriptable options remain available for advanced use:

```text
rdc-auto capture --out D:\Captures
rdc-auto export D:\Captures\a.rdc --assets textures --out D:\Exports
rdc-auto export D:\Captures\a.rdc --assets meshes --out D:\Exports
rdc-auto attach --force
```

Interactive behavior:

- `capture` asks for an output directory when `--out` is omitted.
- `export` asks for the `.rdc` file, asset type, and output directory when omitted.
- `attach` defaults to MuMu12 and takes no emulator option.

## Setup Flow

`rdc-auto setup` performs repeatable environment setup.

### RenderDoc

- Detect an existing RenderDoc installation first.
- If RenderDoc is missing, download RenderDoc v1.44 from `https://renderdoc.org/builds`.
- Use the Windows x64 installer.
- Install with default installer options.
- Save discovered paths such as `qrenderdoc.exe` and `renderdoccmd.exe`.

### RenderDoc MCP

- Use the fixed repository: `https://github.com/Smilexs/RenderDocMCP.git`.
- Clone or update into:

```text
%LOCALAPPDATA%\RdcAutomation\mcp\RenderDocMCP
```

- Install the RenderDoc extension using the repository installer script.
- Install the MCP server using the repository's supported Python/uv flow.
- If Python or uv is missing, install or unpack a tool-managed runtime instead of asking the user to install Python manually.
- The managed runtime should be stored under:

```text
%LOCALAPPDATA%\RdcAutomation\runtime\
```

- CLI-managed MCP is the default mode.
- A later command can generate MCP client configuration for external clients, but that is not a first-release blocker.

### MuMu12

- Do not install MuMu12.
- Ask the user for the MuMu12 root installation directory if it is not configured.
- The launch executable is fixed relative to that root:

```text
MuMuPlayer-12.0\nx_main\MuMuNxMain.exe
```

- Store the root directory and verify the executable exists.
- MuMu12 must be configured to use Vulkan. The first release prompts the user to verify this setting instead of modifying unknown MuMu12 config files.

## Attach Flow

`rdc-auto attach` prepares a long-lived RenderDoc-controlled MuMu12 session.

Steps:

1. Load config.
2. Ensure setup has installed or located RenderDoc and RenderDoc MCP.
3. Ensure MuMu12 root directory is configured.
4. Resolve:

```text
<MuMu12Root>\MuMuPlayer-12.0\nx_main\MuMuNxMain.exe
```

5. Check whether `MuMuNxMain.exe` is already running.
6. If it is running, prompt the user to close MuMu12.
7. Only with `--force`, terminate the MuMu12 process tree automatically.
8. Prompt the user to confirm MuMu12 is set to Vulkan.
9. Start or reuse qrenderdoc with the RenderDoc MCP bridge loaded.
10. Ask MCP to launch MuMu12 through RenderDoc and return a `session_id`.
11. Store the active `session_id`, target PID, and timestamp in local config.

The key behavior is that MuMu12 is launched by RenderDoc, not attached to an already-running emulator process.

## Capture Flow

`rdc-auto capture` captures the current frame from the active MuMu12 session.

Steps:

1. Read the active `session_id` from config.
2. If no session exists, ask whether to run `rdc-auto attach`.
3. Call MCP `get_target_status(session_id)`.
4. If the target is not alive or not capture-capable, ask the user to rerun `rdc-auto attach`.
5. Ask for an output directory if `--out` is omitted.
6. Generate a default filename:

```text
mumu12_YYYYMMDD_HHMMSS.rdc
```

7. Call MCP `trigger_capture(session_id, output_path, timeout_seconds)`.
8. Save the resulting `.rdc` path as `capture.last_rdc_path`.
9. Print the saved path.

## Export Flow

`rdc-auto export` exports assets from a capture.

Steps:

1. Ask for an `.rdc` file path if omitted. The last captured `.rdc` is offered as the default.
2. Ask which assets to export if omitted:

```text
textures
meshes
both
```

3. Ask for an output directory if omitted.
4. Launch or reuse RenderDoc with the MCP bridge.
5. Call MCP `open_capture(capture_path)`.
6. Export requested assets.
7. Write `manifest.json`.

Output layout:

```text
<export-dir>\
  textures\
    <resource-name-or-id>.png
  meshes\
    <event-id>_<draw-name>.obj
    <event-id>_<draw-name>.mtl
  raw_mesh_json\
    <event-id>_<draw-name>.json
  manifest.json
```

Texture export:

- Use MCP `get_textures`.
- Use MCP `export_texture_to_file(resource_id, output_path, file_type="PNG")`.
- Continue on individual texture failures and record them in `manifest.json`.

Mesh export:

- Use MCP draw-call discovery such as `get_draw_calls`.
- Use MCP `export_mesh_to_file(event_id, output_path)` to write JSON.
- Convert JSON to OBJ/MTL in the CLI.
- Continue on individual mesh failures and record them in `manifest.json`.

## RenderDoc MCP Interface Contract

The current RenderDoc MCP repository already provides many relevant tools, including capture opening, frame capture, resource listing, texture export, draw-call listing, and mesh export.

The first `rdc-auto` workflow needs a split launch/capture lifecycle that is not covered by a single immediate `capture_frame` call. The MCP should add the following session-oriented tools.

### `launch_application`

Purpose: launch a target executable through RenderDoc and keep a target-control session alive for later capture.

Suggested signature:

```text
launch_application(exe_path, working_dir, cmd_line, graphics_api) -> session_id, pid
```

For MuMu12, `graphics_api` is always `vulkan`.

### `get_target_status`

Purpose: query whether a previously launched target is still alive and capture-capable.

Suggested signature:

```text
get_target_status(session_id) -> status
```

Suggested response:

```json
{
  "session_id": "mumu12-20260609-001",
  "pid": 12345,
  "exe_path": "D:\\MuMu\\MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe",
  "alive": true,
  "connected": true,
  "graphics_api": "vulkan",
  "can_capture": true,
  "last_error": null
}
```

CLI use: decide whether `rdc-auto capture` can continue or must ask the user to rerun `rdc-auto attach`.

### `trigger_capture`

Purpose: trigger one capture on the already launched target without restarting MuMu12.

Suggested signature:

```text
trigger_capture(session_id, output_path, timeout_seconds) -> rdc_path
```

Suggested response:

```json
{
  "rdc_path": "D:\\Captures\\mumu12_20260609_153000.rdc",
  "pid": 12345,
  "captured": true
}
```

CLI use: implement `rdc-auto capture` after the user has manually navigated to the desired game scene.

### `close_target`

Purpose: release the RenderDoc target-control session.

Suggested signature:

```text
close_target(session_id, terminate_process=false)
```

Default behavior:

- Release the RenderDoc session.
- Do not terminate MuMu12.

With `terminate_process=true`:

- Release the RenderDoc session.
- Also terminate the target process. This should only be used for explicit cleanup or force mode.

## Configuration

Configuration is stored at:

```text
%LOCALAPPDATA%\RdcAutomation\config.json
```

Suggested shape:

```json
{
  "renderdoc": {
    "version": "1.44",
    "install_dir": "C:\\Program Files\\RenderDoc",
    "qrenderdoc_path": "C:\\Program Files\\RenderDoc\\qrenderdoc.exe",
    "renderdoccmd_path": "C:\\Program Files\\RenderDoc\\renderdoccmd.exe"
  },
  "mcp": {
    "repo": "https://github.com/Smilexs/RenderDocMCP.git",
    "path": "%LOCALAPPDATA%\\RdcAutomation\\mcp\\RenderDocMCP",
    "mode": "managed"
  },
  "emulator": {
    "type": "mumu12",
    "root_dir": "D:\\MuMu",
    "exe_relative_path": "MuMuPlayer-12.0\\nx_main\\MuMuNxMain.exe",
    "graphics_api": "vulkan"
  },
  "capture": {
    "last_output_dir": "D:\\Captures",
    "last_rdc_path": "D:\\Captures\\mumu12_20260609_153000.rdc",
    "active_session_id": null
  }
}
```

Logs are stored under:

```text
%LOCALAPPDATA%\RdcAutomation\logs\
```

## CLI Module Plan

```text
rdc_auto/
  cli.py                  # setup / attach / capture / export command entry
  config.py               # config read/write
  paths.py                # RenderDoc, MuMu12, and workspace path discovery
  renderdoc_installer.py  # RenderDoc v1.44 download and default install
  mcp_installer.py        # clone/update RenderDocMCP and install extension/server
  mcp_client.py           # managed MCP process and tool calls
  emulator.py             # MuMu12 path validation and process checks
  capture.py              # attach/capture orchestration
  export_assets.py        # texture and mesh export orchestration
  mesh_convert.py         # MCP mesh JSON -> OBJ/MTL
  prompts.py              # interactive path and option prompts
  logging.py              # log setup
```

## Skill Behavior

The Codex Skill is named `rdc-auto`.

It should trigger on phrases like:

```text
deploy RenderDoc capture environment
install RenderDoc automation
attach emulator
start MuMu12 capture
capture current frame
save current emulator frame
analyze rdc
export textures
export meshes
extract rdc assets
部署 RenderDoc 截帧环境
安装 RenderDoc 自动化
attach 模拟器
启动 MuMu12 截帧
现在截一帧
保存当前模拟器画面
分析 rdc
导出贴图
导出模型
提取 rdc 资源
```

Intent mapping:

```text
environment setup -> rdc-auto setup
start capture environment -> rdc-auto attach
capture current frame -> rdc-auto capture
analyze/export assets -> rdc-auto export
```

The Skill should keep logic thin:

- Ask only for missing path or asset-selection information.
- Prefer CLI commands for execution.
- Explain destructive actions before using `--force`.
- Reuse config and last captured `.rdc` when available.

## Error Handling

Expected failures and responses:

- RenderDoc missing: run `rdc-auto setup`, download and install v1.44.
- RenderDoc MCP unavailable: rerun setup, reinstall extension/server, and ask the user to restart RenderDoc if needed.
- MuMu12 root invalid: ask for the root directory again and validate the fixed relative executable.
- MuMu12 already running: ask user to close it; use `--force` only after explicit confirmation.
- Vulkan not confirmed: tell the user to switch MuMu12 to Vulkan before continuing.
- Session expired: ask the user to rerun `rdc-auto attach`.
- Capture timeout: preserve logs and show the qrenderdoc/MCP log paths.
- Texture export failure: continue with other textures and record failure.
- Mesh export failure: continue with other draw calls and record failure.
- OBJ conversion failure: preserve raw mesh JSON and record failure.

## Testing Strategy

### Unit Tests

- Config read/write and default migration.
- MuMu12 executable path resolution.
- RenderDoc v1.44 installer URL selection and installer invocation construction.
- Process-detection logic for MuMu12.
- Mesh JSON to OBJ/MTL conversion.
- Export manifest generation.

### Integration Tests With Fake MCP

- `setup` installs or skips based on mocked dependency state.
- `attach` refuses an already-running MuMu12 unless force is set.
- `attach` stores a fake session after MCP `launch_application`.
- `capture` calls `get_target_status` and `trigger_capture`.
- `capture` records `last_rdc_path`.
- `export` opens an `.rdc`, exports fake textures, exports fake mesh JSON, converts OBJ/MTL, and writes `manifest.json`.

### Manual Acceptance

On a Windows machine:

1. Run `rdc-auto setup` in a clean user environment.
2. Confirm MuMu12 root directory.
3. Confirm RenderDoc v1.44 is installed with defaults.
4. Confirm RenderDoc MCP bridge loads in qrenderdoc.
5. Run `rdc-auto attach`.
6. Confirm MuMu12 launches through RenderDoc using Vulkan.
7. Play manually until the desired frame is visible.
8. Run `rdc-auto capture` and save an `.rdc`.
9. Run `rdc-auto export`.
10. Confirm PNG textures, OBJ/MTL meshes, raw mesh JSON, and `manifest.json` are written.

## Open Implementation Notes

- The exact RenderDoc v1.44 installer filename should be resolved from the official builds page or a pinned URL during implementation.
- If RenderDoc MCP adds native OBJ export, the CLI can bypass `mesh_convert.py`.
- If MuMu12 Vulkan config file location becomes reliable, auto-detection can be added later. First release should prompt only.
- The first release should keep capture lifecycle state local and simple; a richer daemon or hotkey mode can be added after the session-oriented MCP lifecycle is proven.
