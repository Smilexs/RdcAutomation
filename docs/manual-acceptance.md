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
