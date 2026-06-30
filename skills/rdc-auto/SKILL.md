---
name: rdc-auto
description: Use when the user wants to install or operate the rdc-auto RenderDoc automation workflow for MuMu12, including setting up RenderDoc v1.44, RenderDocMCP, launching MuMu12 through RenderDoc, capturing the current emulator frame, or exporting textures and meshes from .rdc files.
---

# rdc-auto

Use this Skill to drive the `rdc-auto` CLI. Keep the Skill thin: ask for missing paths or asset choices, then run the CLI.

## Commands

- Environment setup: `rdc-auto setup`
- Start MuMu12 through RenderDoc: `rdc-auto attach`
- Capture current emulator frame: `rdc-auto capture`
- Export assets from an RDC: `rdc-auto export`

## Workflow

1. If the user asks to deploy or install the capture environment, run `rdc-auto setup`.
2. If the user asks to attach or start the emulator capture environment, run `rdc-auto attach`.
3. If MuMu12 is already running, tell the user to close it. Use `rdc-auto attach --force` only after the user explicitly approves automatic termination.
4. If the user asks to capture the current emulator frame, run `rdc-auto capture`.
5. If capture output path is missing, ask for a save directory.
6. If the user asks to analyze, export, extract textures, or extract models from an `.rdc`, run `rdc-auto export`.
7. If export inputs are missing, ask for the `.rdc` path, asset type (`textures`, `meshes`, or `both`), and output directory.

## Fixed Constraints

- RenderDoc version is v1.44.
- RenderDoc installer is downloaded from `https://renderdoc.org/builds` when RenderDoc is missing.
- RenderDocMCP is installed from the latest GitHub release setup executable at `https://api.github.com/repos/Smilexs/RenderDocMCP/releases/latest`.
- The only supported emulator in the first release is MuMu12.
- MuMu12 root is the directory that directly contains `nx_main`; the executable path is `<MuMu12Root>\nx_main\MuMuNxMain.exe`.
- MuMu12 must use Vulkan.

## Error Handling

- RenderDoc missing: run `rdc-auto setup`.
- RenderDocMCP bridge unavailable: run `rdc-auto setup` and ask the user to restart RenderDoc if needed.
- MuMu12 root invalid: ask for the directory that directly contains `nx_main`.
- MuMu12 already running: ask the user to close it before attach.
- Vulkan not confirmed: ask the user to switch MuMu12 to Vulkan.
- Capture session expired: run `rdc-auto attach` again.
- Export failures: report the manifest path and summarize failed textures or meshes.
