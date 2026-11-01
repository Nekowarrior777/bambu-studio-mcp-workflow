# Get started on Windows

This guide sets up the two MCP servers used by the `bambu-print` skill:

| Component | Role |
|---|---|
| `unofficial-bambu` | Saved-project preparation, slicing and observed Bambu Studio UI control |
| `bambu-printer` | Printer telemetry, camera and dedicated device tools |
| `bambu-print` | Chooses the appropriate tools for the user's task and keeps review, preparation and printing separate |

The source installer prepares both runtimes. Its optional registration switch registers **only `unofficial-bambu`**; add `bambu-printer` separately below. An existing working printer connection can be retained.

## 1. Check the prerequisites

- Windows 10/11 x64 and Bambu Studio installed separately.
- **Bambu Studio 02.08.02.61** for the currently verified Prepare/Preview detection profile. Other versions return an unknown active view.
- Python **3.14**, Node.js **24**, npm and Git on `PATH`.
- Windows PowerShell and the .NET Framework x64 compiler/UI Automation assemblies used by the build script.
- Codex CLI/app for the provided skill workflow. Manual configuration for another stdio MCP client is also described below; that client's full workflow has not been independently validated here.

Read [compatibility and verification limits](../VALIDATION.md) and [connection security](../SECURITY.md). Clean-machine installation and a new physical final Send are still unverified.

## 2. Get the source and prepare the runtimes

Open PowerShell in the directory where you keep source projects:

```powershell
git clone https://github.com/Nekowarrior777/bambu-studio-mcp-workflow.git
Set-Location .\bambu-studio-mcp-workflow
powershell -NoProfile -File .\scripts\install.ps1 -PythonExe python
```

Review the installer before running it. It creates the Python environment, checks pinned dependencies, builds the pinned printer runtime and compiles the native UI helper. It does not contact a printer or register MCP servers by default.

For a **fresh Codex setup**, the optional switches register the Studio server and install the skill:

```powershell
powershell -NoProfile -File .\scripts\install.ps1 -PythonExe python -RegisterCodex -InstallSkill
```

If either registration or skill already exists, use the manual configuration route instead of overwriting it. See [existing setup conflicts](TROUBLESHOOTING.md#an-existing-registration-or-skill-blocks-installation).

If Studio is installed elsewhere, pass `-StudioExe` with its actual executable path. The installer requires the tested Python and Node major versions; it does not automatically upgrade them.

## 3. Configure the private printer connection

For a new P1S connection, find your printer's host, serial and LAN access code locally using the printer screen and the [upstream setup reference](https://github.com/DMontgomery40/bambu-printer-mcp/blob/b3c33f55998b946914273e95fc26d5632bc86e01/docs/SETUP.md#configuration). Keep an existing working Studio/printer connection unchanged. This guide does not require disabling cloud features or changing firmware/network authorization modes. Check current vendor guidance for your model if the existing connection is unavailable.

Create this private file **outside the clone**:

```text
%LOCALAPPDATA%\BambuPrinterMCP\printer.env
```

Use these keys, replacing the angle-bracket placeholders locally:

```dotenv
PRINTER_HOST=<PRINTER_HOST>
BAMBU_SERIAL=<PRINTER_SERIAL>
BAMBU_TOKEN=<PRINTER_ACCESS_CODE>
BAMBU_MODEL=p1s
BED_TYPE=textured_plate
NOZZLE_DIAMETER=0.4
```

This file is required by the extension's read-only safety probe. The `bambu-printer` configuration below also loads the same file using Node's `--env-file` option. No real connection values belong in a public example, issue, screenshot or repository.

These keys configure the Node printer runtime and the extension's safety probe. They do not configure every upstream `unofficial-bambu` direct printer tool. The skill routes ordinary telemetry and camera requests to `bambu-printer`; official Send also requires the correct printer connection and selection in Bambu Studio.

The final-send route currently supports **P1S, a 0.4 mm nozzle, Textured PEI and one external-spool material**. If your actual setup differs, do not use those example defaults as a substitute for verifying it.

## 4. Register both MCP servers

Choose one route:

- **Codex:** merge the required entries from [the TOML example](../examples/codex.mcp.example.toml) into your private Codex `config.toml`. If the installer already added `unofficial-bambu`, preserve that entry and add only `bambu-printer`.
- **A JSON-based client:** merge the entries from [the stdio JSON example](../examples/mcp-servers.example.json) into that client's supported MCP settings. The JSON format applies to clients with an `mcpServers` object; it is not the Codex format.

Replace every `<PLACEHOLDER>` with a real **absolute path** before enabling the entries. Clients do not automatically expand these placeholders or `%LOCALAPPDATA%` in command arguments. Forward slashes are accepted in the Windows path examples and avoid JSON/TOML backslash escaping.

| Placeholder | Value to supply privately |
|---|---|
| `<REPOSITORY_DIR>` | Full path to this clone |
| `<NODE_EXE>` | Full path to the installed Node.js 24 `node.exe` |
| `<BAMBU_STUDIO_EXE>` | Full path to `bambu-studio.exe` |
| `<STUDIO_RESOURCES_DIR>` | Studio's `resources` directory next to its executable |
| `<STUDIO_DATA_DIR>` | Your Bambu Studio application-data directory |
| `<LOCAL_APP_DATA_DIR>` | The actual expanded Windows local application-data directory |
| `<PROJECT_OUTPUT_DIR>` | A separate writable directory for generated project copies |
| `<MCP_TEMP_DIR>` | A writable temporary directory for the Studio MCP |

Create the output and temporary directories first. The expected printer entry point is `tools/bambu-printer-mcp/dist/index.js`; the source installer builds it from the pinned checkout. The private file path in the Node argument and the Studio server's `LOCALAPPDATA` value must resolve to the same `BambuPrinterMCP/printer.env` file.

If you use manual registration and want the skill in Codex, install the repository's `skills/bambu-print` folder at user scope through Codex's skill installation flow, or use the installer's `-InstallSkill` switch when that destination is empty. Do not replace an existing skill without comparing and preserving it first.

## 5. Add the private Studio printer binding when needed

For read-only Studio UI inspection and `studio_dispatch_diagnostics`, no final-send binding is required. For later guarded final submission, copy [the binding template](../examples/printer-bindings.example.json) to:

```text
%LOCALAPPDATA%\BambuStudioMCPWorkflow\printer-bindings.json
```

Replace its serial key and visible Studio printer name only after confirming they refer to the same physical printer. The access code belongs in the private environment file, never in this binding. Existing dispatch receipts are held under the private workflow `state` directory; preserve them during upgrades.

## 6. Verify without printing

Restart Codex or open a fresh local session after registering servers or installing the skill. Open Bambu Studio normally and keep the intended project window visible. Ask:

> Use $bambu-print to check the Studio UI extension and the printer connection. Report the active view, printer state and actual/target temperatures. Do not change project settings, heat, move, slice, upload or print. Do not display connection credentials.

Expected evidence is a responding `studio_ui_status`, a window inspection with a known active view on the supported build, and fresh `bambu-printer.get_printer_status` telemetry. `unknown` is an explicit compatibility/state result and should be diagnosed rather than treated as a confirmed tab.

A follow-up UI check can be requested separately:

> Switch between Prepare and Preview through MCP, confirm each transition without screenshots, then restore the original view. Keep project settings unchanged and do not print.

The first handoff to Studio or opening a print dialog is not a completed print. See the [workflow overview](../README.md), [active-tab contract](../tools/unofficial-bambu-mcp/local_extension/ACTIVE_TABS.md) and [troubleshooting guide](TROUBLESHOOTING.md).
