# Bambu Studio MCP Workflow

A source-only Windows integration that combines `unofficial-bambu-mcp` project tools, an observed Bambu Studio UI adapter, independent printer/file validation and a reusable `bambu-print` skill.

This source distribution is **0.1.1**. Its Python extension wrapper remains **0.1.0**, the native Windows UI adapter is **0.1.1**, and the upstream `unofficial-bambu-mcp` dependency remains **0.3.0**. It retains upstream tools and adds seven commands. It is a local extension, not an official Bambu Studio release or a replacement release of the upstream package.

## Capabilities

| Tool | Purpose |
|---|---|
| `studio_ui_status` | Extension health and actual Studio windows |
| `studio_ui_inspect` | Observed controls plus independently verified active-view evidence on supported Studio builds |
| `studio_ui_action` | Observed UI actions; Prepare/Preview clicks include bounded native postcondition verification |
| `studio_dispatch_diagnostics` | Read-only exact file and fresh printer diagnostics |
| `studio_open_print_dialog` | Open the official dialog for a recorded exported artifact |
| `studio_prepare_send` | Check readiness and bind an expiring one-use ticket |
| `studio_submit_send` | Attempt final Send once and observe the corresponding printer job |

UI control uses Windows UI Automation and, for custom wx controls, events bound to the control's own checked HWND. It does not depend on screenshot coordinates or move the global cursor. Each executed observation is consumed; inspect again after an action. Hidden/minimized windows and changed/disabled controls reject.

Prepare/Preview verification currently supports **Bambu Studio 02.08.02.61** through a strict native-window profile. `active_tab.verified` reports whether the current state is known; `result.verification.confirmed` requires two consecutive reads of the requested state after at most one input. Unsupported or ambiguous layouts remain unknown, and an unconfirmed click is never automatically replayed. Read [active-tab verification](tools/unofficial-bambu-mcp/local_extension/ACTIVE_TABS.md) for the profile and result contract.

Final Send is currently scoped to **P1S, 0.4 mm, Textured PEI and one external-spool material**. The skill routes read-only review, preparation and explicit print requests separately. It does not make ABS/90 °C a default for unrelated models and does not authorize background prints or external publication.

## Requirements and installation

- Windows 10/11 x64 with Bambu Studio installed separately.
- Python **3.14** and Node.js **24** were used for the recorded validation. Other versions are not covered by that result.
- Git, npm and Windows .NET Framework 4.x compiler/UI Automation assemblies.
- An existing local printer connection for optional status/final-dispatch checks. Do not put credentials in the repository.

Read [SECURITY.md](SECURITY.md), including the inherited self-signed-certificate verification limitation, before connecting a printer.

```powershell
pwsh -NoProfile -File .\scripts\install.ps1 -PythonExe python
```

Installation creates this clone's venv, downloads pinned Python dependencies, checks the upstream wheel hash, applies the narrow Windows-basename patch, checks out the pinned safety runtime, runs npm install/build and compiles the local UI helper. It does not start Studio, access a printer, run a physical print or register a server by default. Review the script before executing it.

Optional explicit switches:

```powershell
pwsh -NoProfile -File .\scripts\install.ps1 -PythonExe python -RegisterCodex -InstallSkill
```

`-RegisterCodex` requires the Codex CLI and refuses to replace a different existing `unofficial-bambu` entry. `-InstallSkill` refuses to overwrite an existing skill. Restart/open a fresh local Codex chat after registration. A project-scoped `AGENTS.md` may also point to `skills/bambu-print/SKILL.md` without installing it globally.

The installer sets the launch environment for this clone. For another MCP client, point a stdio entry at `tools/unofficial-bambu-mcp/.venv/Scripts/python.exe` with the absolute `enhanced_server.py` argument and the corresponding Bambu Studio resources/data directories. See the script's environment list; never publish your completed configuration.

## Configure privately

1. Keep the existing `bambu-printer` connector configured with your own printer access information. This repository does not install a filled credential file or change printer/network modes.
2. Copy `examples/printer-bindings.example.json` to `%LOCALAPPDATA%\BambuStudioMCPWorkflow\printer-bindings.json`. Replace placeholders locally only after verifying the visible Studio printer name against the serial. No LAN access code belongs in this file.
3. Default runtime state lives under `%LOCALAPPDATA%\BambuStudioMCPWorkflow\state`. Outputs default to a separate local application-data folder when registered by the script.
4. First request: **“Use $bambu-print to inspect Bambu Studio and printer status only; do not print or change settings.”**

For a requested print, the flow is `send_to_printer(via='bambu_studio')` → `studio_open_print_dialog` → inspect → `studio_prepare_send(dry_run=false, bed_cleared=true)` → `studio_submit_send(ticket)`. The initial handoff alone does not start a print. Never invent bed-clearance evidence or repeat an uncertain attempt.

## Verification evidence and limits

The staged public source passed **53/53 fake-adapter Python tests** and **40/40 isolated Windows-fixture checks**. Recorded development validation also included stdio tool discovery and a real Prepare -> Preview -> Prepare sequence, with independently confirmed native state after both input attempts. The original view and visible values were restored and the saved project remained unchanged. No private screenshots, model files, printer identifiers or raw telemetry are included in this source distribution. See [VALIDATION.md](VALIDATION.md) for the evidence boundary.

**A clean-machine run of this installer is unverified. A fresh physical print through the extension's final Send path is unverified.** A prior print through official Studio was completed separately; that does not prove this extension's final dispatcher. No claim of a full security audit, production readiness or universal button support is made.

After installation, isolated checks are:

```powershell
& .\tools\unofficial-bambu-mcp\.venv\Scripts\python.exe -m unittest discover -s .\tools\unofficial-bambu-mcp\tests -v
powershell -NoProfile -File .\tools\unofficial-bambu-mcp\local_extension\build_studio_ui.ps1 -WithFixture
& .\tools\unofficial-bambu-mcp\local_extension\StudioUiFixture.exe --self-test
```

The fixture opens only its own synthetic test window. Do not substitute a live physical print for a software test. Consult [third-party notices](THIRD_PARTY_NOTICES.md) and [LICENSE](LICENSE).
