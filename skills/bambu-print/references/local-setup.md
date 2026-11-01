# Installed tandem and source locations

Find the existing `unofficial-bambu` entry in the user's Codex configuration. Its command is the local Python venv and its arguments point to `enhanced_server.py`. Read only the fields needed to locate the runtime; never dump the configuration or credentials. The directory containing that file is the extension base. In this installation it is `<project>/tools/unofficial-bambu-mcp`.

| Source | Purpose |
|---|---|
| `enhanced_server.py` | Upstream 0.3.0 plus local Studio UI Extension 0.1.0; discover actual versions/tools live |
| `local_extension/printer-bindings.json` | Verified visible Studio printer name and serial; use the current mapping |
| `local_extension/StudioUi.exe` | One-request Windows UI adapter; no manual service startup |
| Runtime `STATE` directory from `enhanced_server.py` | Prepared tickets and durable attempted/submitted/unknown receipts; never erase to bypass replay protection. The original local installation uses `state/dispatch-receipts` under the extension base; a portable distribution may store state under LOCALAPPDATA or an explicit private state directory |
| `qa/ui-extension-smoke.json` | Protocol and read-only UI verification |
| `qa/ui-navigation-smoke.json` | Reversible project-tab verification |
| `<project>/Bambu_MCP_projects` | Separate project copies, sliced output and requested camera snapshots |
| `<project>/Bambu_MCP_projects/Управление_Studio_через_MCP.md`, when present | Historical local implementation record; in a portable source package use its README and SECURITY documents instead |
| `<project>/tools/bambu-printer-mcp` | Independent file/printer validation and physical device connector |

Keep credentials in the existing configured connection. Do not copy them into skills, models, reports or repositories. The skill is portable guidance, not a copy of the user's printer credentials or local runtime.

The extension's final dispatcher reads live MQTT identity and inspects the exact saved file. Display-oriented cached status alone cannot authorize a start. `studio_dispatch_diagnostics` is read-only; `ready_state=true` does not prove the plate is empty or grant print authorization.

Known public signatures (discover current tool schemas before calling):

```text
studio_ui_status()
studio_ui_inspect(window_id=0, name_filter='')
studio_ui_action(snapshot_id, element_token, action='click', value=None, execute=false)
studio_dispatch_diagnostics(file_path, printer_serial)
studio_open_print_dialog(file_path)
studio_prepare_send(file_path, printer_serial, printer_name, bed_cleared=false, dry_run=true)
studio_submit_send(ticket)
```

Do not run `extension_navigation_smoke.py` as a background health check: it clicks real project tabs. Do not start physical prints during software tests. Existing Python/unit and Windows-fixture tests can validate code in isolation when changes are requested.
