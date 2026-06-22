# GUI Manual Acceptance Checklist

Use this checklist for a human GUI pass after the packaged desktop build is available. Do not treat this as an automated smoke test.

## Build

- [ ] Run `.\scripts\build_gui_exe.ps1` from the repository root.
- [ ] Confirm `dist\RdcAutomation.exe` exists after the build.
- [ ] Confirm build artifacts are not staged unless explicitly needed.

## Environment

- [ ] Start the GUI on a Windows machine with Python project prerequisites already installed.
- [ ] Verify the setup screen opens and displays configured RenderDoc, RenderDocMCP, MuMu, capture, and export paths.
- [ ] Verify editing settings stores values in the same configuration used by the CLI.
- [ ] Verify validation errors are shown clearly when required paths are missing or invalid.

## MCP

- [ ] Run setup from the GUI and confirm RenderDocMCP installation or configuration status is reported.
- [ ] Confirm MCP-related diagnostics match the CLI behavior for installed, missing, and already-configured states.
- [ ] Confirm failed MCP setup leaves the UI responsive and provides an actionable error message.

## Capture

- [ ] Use the attach workflow with a known MuMu instance and confirm progress/status messages update.
- [ ] Use the capture workflow and confirm the selected output directory receives an `.rdc` file.
- [ ] Confirm capture failures show the command context and error summary without closing the GUI.

## Export

- [ ] Select an existing `.rdc` file and an export output directory.
- [ ] Export textures and verify expected files are written.
- [ ] Export meshes and verify expected files are written.
- [ ] Confirm export progress and final status are visible in the GUI.

## EID

- [ ] Enter a valid event ID and confirm it is passed through to the export workflow.
- [ ] Leave the event ID empty and confirm the default export behavior matches the CLI.
- [ ] Enter an invalid event ID and confirm the GUI blocks or reports the invalid value clearly.

## AI Screen

- [ ] Open the AI assistant screen.
- [ ] Change AI-related UI settings and confirm they persist after navigating away and back.
- [ ] Submit a local diagnostic prompt and confirm the response is generated locally.
- [ ] Confirm the first GUI release does not call a remote AI service from this screen.
