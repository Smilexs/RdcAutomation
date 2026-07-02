# rdc-auto Manual Acceptance

Run these checks on a Windows machine with MuMu12 available.

## Build CLI exe

```powershell
cd E:\ZSGame\AIProjects\RdcAutomation
python -m pytest -v
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

## Environment Setup

1. Run `rdc-auto setup`.
2. Confirm RenderDoc v1.44 is detected or installed.
3. Confirm RenderDocMCP is installed from the embedded `renderdoc_mcp` source, not from `RenderDocMCP-Setup-*.exe` or GitHub.
4. Confirm `config.json` records `mcp.source_path` and `mcp.extension_dir`.
5. Confirm the installed extension directory contains `extension.json`.
6. Confirm RenderDoc `UI.config` includes `renderdoc_mcp_bridge` in `AlwaysLoad_Extensions`.
7. Enter the MuMu12 root directory when prompted; it must directly contain `nx_main`.
8. Confirm `<MuMu12Root>\nx_main\MuMuNxMain.exe` exists.

## Capture Flow

1. Close MuMu12 if it is already running.
2. Set MuMu12 graphics API to Vulkan.
3. Run `rdc-auto attach`.
4. Confirm MuMu12 starts through RenderDoc.
5. Confirm the CLI outputs a valid active session id.
6. In MuMu12, navigate to the frame to capture.
7. Run `rdc-auto capture --out D:\RdcCaptures`.
8. Confirm a `.rdc` file is written.

## Export Flow

```powershell
.\dist\rdc-auto.exe export D:\RdcCaptures\<your-file>.rdc --assets both --out D:\RdcExports
```

Confirm `textures`, `meshes`, `raw_mesh_json`, and `manifest.json` are written.
Confirm exported PNG files open normally and OBJ/MTL files import into a model viewer or DCC tool.

## Negative Checks

1. Configure or install a non-v1.44 RenderDoc and confirm `rdc-auto setup` does not accept it as v1.44.
2. Delete the installed RenderDocMCP extension directory and confirm `rdc-auto setup` reinstalls it from embedded source.
3. Start MuMu12 manually, then run `rdc-auto attach` without `--force`; confirm the CLI asks you to close MuMu12 instead of terminating it.
4. Clear or invalidate the active session in `config.json`, then run `rdc-auto capture`; confirm the CLI asks for a fresh attach.
5. Stop qrenderdoc during capture and confirm the CLI reports an actionable timeout or MCP error without an `Unexpected error` prefix.
6. Use an `.rdc` where at least one texture or mesh export fails and confirm `manifest.json` records the failed asset while other assets continue exporting.
