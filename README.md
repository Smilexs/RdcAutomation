# rdc-auto

Windows CLI for automating RenderDoc v1.44 with MuMu12:

- `attach` launches MuMu12 through RenderDoc.
- `capture` connects to the running RenderDoc target and writes an `.rdc`.
- `export` uses the RenderDocMCP qrenderdoc extension to export textures and meshes from an existing `.rdc`.

## Requirements

- Windows
- Python 3.11+
- PowerShell
- MuMu12 installed locally

`rdc-auto setup` can install/configure RenderDoc and RenderDocMCP.

## Source Setup

```powershell
.\scripts\bootstrap.ps1
```

This installs the package in editable mode with development dependencies and runs the test suite.

## Build Executable

```powershell
.\scripts\build_exe.ps1
```

The executable is written to `dist\rdc-auto.exe`. Build outputs (`build\`, `dist\`, `rdc-auto.spec`) are generated artifacts and are intentionally ignored by git.

## Build GUI Executable

```powershell
.\scripts\build_gui_exe.ps1
```

The desktop executable is written to `dist\RdcAutomation.exe`.

The GUI keeps the same workflow as the CLI: setup, attach, capture, and export. The AI assistant screen in the first GUI release stores UI settings and returns local diagnostic replies only.

GUI build outputs (`build\`, `dist\`, `RdcAutomation.spec`) are generated artifacts and are intentionally ignored by git.

## Basic Usage

```powershell
rdc-auto setup
rdc-auto attach --yes-vulkan
rdc-auto capture --out C:\Captures
rdc-auto export C:\Captures\frame.rdc --assets textures --out C:\Exports
```

Use `--vm-index` with `attach` when selecting a specific MuMu instance.
