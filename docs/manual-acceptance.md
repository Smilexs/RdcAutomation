# rdc-auto Manual Acceptance

Run these checks on a Windows machine with MuMu12 installed.

## Setup

1. Run `rdc-auto setup`.
2. Confirm RenderDoc v1.44 is detected or installed.
3. Confirm RenderDocMCP setup exe is downloaded from the latest GitHub release.
4. Confirm RenderDocMCP is installed and `config.json` records the installed executable path.
5. Enter the MuMu12 root directory when prompted.
6. Confirm `<MuMu12Root>\MuMuPlayer-12.0\nx_main\MuMuNxMain.exe` exists.

## Attach

1. Close MuMu12 if it is running.
2. Set MuMu12 graphics API to Vulkan.
3. Run `rdc-auto attach`.
4. Confirm MuMu12 launches through RenderDoc.
5. Confirm the CLI prints an active session id.

## Capture

1. Navigate manually to the desired game scene.
2. Run `rdc-auto capture`.
3. Choose an output directory.
4. Confirm a `.rdc` file is written.

## Export

1. Run `rdc-auto export`.
2. Use the captured `.rdc`.
3. Select `both`.
4. Choose an output directory.
5. Confirm `textures`, `meshes`, `raw_mesh_json`, and `manifest.json` are written.
6. Confirm PNG files are readable.
7. Confirm OBJ/MTL files import into a DCC or viewer.

## Negative Checks

1. Temporarily configure or install a RenderDoc version other than v1.44 and confirm `rdc-auto setup` does not accept it as v1.44.
2. Put a stale or manually built RenderDocMCP executable path in `config.json` and confirm `rdc-auto setup` reinstalls from the latest `RenderDocMCP-Setup-*.exe` release asset.
3. Start MuMu12 manually, run `rdc-auto attach` without `--force`, and confirm the CLI asks you to close MuMu12 instead of terminating it.
4. Clear or expire the active session in `config.json`, run `rdc-auto capture`, and confirm the CLI offers to run attach.
5. Disconnect or stop RenderDocMCP during capture and confirm the CLI reports an actionable timeout or MCP error without an `Unexpected error` prefix.
6. Use an `.rdc` with at least one texture or mesh export failure and confirm `manifest.json` records the failed asset while other assets continue exporting.
