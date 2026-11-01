---
name: bambu-print
description: "Use for Bambu Lab P1S and Bambu Studio work: inspect a saved or open 3D project, prepare or slice a model, start an explicitly requested print, inspect printer status or show its camera. Route through unofficial-bambu with the local Studio UI extension and bambu-printer. Apply to Russian requests such as проверь проект, подготовь модель, напечатай and покажи камеру when the context is this 3D printer."
---

# Bambu printing workflow

Use the existing connected tandem; the user should not need to name each MCP. This skill describes workflow and does not authorize a print, testing a live machine, heating or other unrelated actions.

## Route the user's intent

- **Status / finished? / camera:** read `bambu-printer.get_printer_status`; for a fresh photo call `camera_snapshot(bambu_model='P1S', save_path=...)`, inspect it and display the returned local image. Describe actual/target temperatures and observed job state. A finished job is not a verified-quality part; a partly obscured photo cannot establish the whole part's quality.
- **Review:** inspect the project and report findings. Do not change settings or send a print just because review was requested.
- **Prepare / arrange / slice:** make the requested changes on a separate saved copy and verify slicing/previews. Stop before sending.
- **Print / напечатай / отправь на печать:** the specific request authorizes preparing and starting that job. Complete the workflow below; do not ask again merely because Send is consequential. Resolve genuinely missing material, target object or physical bed-clearance evidence before starting.
- **Stop / стой during preparation:** cease further actions. Do not interpret a bare interruption as permission to cancel an already running job; an explicit cancel/stop-print request uses the dedicated printer control.

## Find the installed capabilities

Use live tool discovery and `unofficial-bambu.studio_ui_status`. Read [local setup](references/local-setup.md) when locating the installation, diagnosing connectivity or preparing final dispatch. The extension adds UI commands to the same `unofficial-bambu` server; it is not a second manual service.

- `unofficial-bambu`: project/settings/mesh inspection, layout, slicing and previews.
- `unofficial-bambu.studio_ui_inspect` / `studio_ui_action`: actual Studio buttons, tabs, fields and lists.
- `bambu-printer`: physical printer status, camera and dedicated device controls.

Do not infer current machine state or available tools from a past report. If the catalog lacks the new commands, check registration before reinstalling; a restart/new chat may be needed. Be explicit about what was actually verified.

## Review and preparation

Identify the requested object, plate, actual filament and purpose. Preserve original projects and user presets. Use the current project's settings plus the user's instructions; **ABS and a 90 °C bed were choices for one impeller, not defaults for all models**.

The project MCP reads saved `.3mf` files, not unsaved GUI memory. Use UI inspection to identify an open project; obtain a separate saved copy when needed and authorized. Never claim an unsaved scene was read from disk.

After `open_project`, read all warnings and verify effective settings with `get_setting`: printer/nozzle/plate, material, layer height, walls/infill, supports/brim and nozzle/bed temperatures. Missing custom presets can silently fall back to 0.20 mm in upstream 0.3.0. Restore the intended settings on the copy and verify them rather than accepting the fallback. Reopen/verify after saving.

For physical print preparation, examine orientation, bed contact, overhangs and support removability for the actual geometry and loading direction. Use geometry checks as evidence within their scope, not a strength guarantee. After layout changes inspect `preview_plate`; then `slice_project`, report warnings and inspect `preview_layer` for the first layer and relevant overhang heights. Report estimated time/material before dispatch.

## Complete an authorized print through official Studio

The configured local final-send route supports **P1S, 0.4 mm, Textured PEI and one external-spool material**. Do not silently use it for AMS, another nozzle, plate or printer.

1. Obtain fresh status and a camera view; confirm the selected printer, filament, errors, readiness and clear build plate. A retained FINISH job needs current physical bed-clearance confirmation; do not reuse an old clear-bed photo or set `bed_cleared=true` merely because the user said print. If the camera view cannot establish clearance, ask for that missing physical fact. Do not clear errors or change network/security modes as a shortcut.
2. Call `send_to_printer(plate=..., via='bambu_studio', ...)`. The enhanced command creates a unique SHA256-bound print copy and opens it. **This alone does not start printing.** Use its returned `print_file` for subsequent steps; do not substitute an older similarly named artifact.
3. Select the exact returned Studio window. Call `studio_open_print_dialog(file_path=print_file)` and inspect the dialog, selected printer and external-spool mapping. General UI actions must not bypass final-send guards.
4. Call `studio_prepare_send(file_path=print_file, printer_serial=..., printer_name=..., bed_cleared=true, dry_run=false)` only with the actual bed-clearance evidence and the user's print request. Use the current verified printer binding, not a guessed serial/name. The result is a single-use ticket with a 60-second lifetime, not a dispatch receipt.
5. Call `studio_submit_send(ticket=...)` once. It rechecks the file/dialog/fresh printer state and records the attempt before pressing Send. If a ticket expires before any input, reread the state and prepare a fresh ticket. If an attempt may have occurred, **never replay it automatically or delete its receipt**; reconcile current printer state and the recorded job first.
6. Verify the named job with fresh printer telemetry and, when useful, a fresh camera image. Separate prepared, dialog opened, submission attempted/accepted, heating/preparing, actual layer printing and FINISH. Report rejection or uncertainty plainly. Do not claim physical success from a UI click or a submission receipt alone.

The unsigned direct MQTT print route was rejected on this printer. Prefer the official Studio route; do not retry the unchanged rejected route or weaken firmware authorization. Final Send in the extension has mock/integration coverage; a real new print must still provide its own live acceptance evidence. Skill validation is not permission to start a test print.

## General Studio UI

Read `studio_ui_inspect(window_id, name_filter)` before every action. Use only its returned snapshot/control token; snapshots last 30 seconds and are consumed by an executed attempt. `execute=false` is a preview; `execute=true` attempts the requested action once. Reread state afterwards. Supported actions are `click`, `set_value`, `select`, `expand`, `collapse`, and `toggle` with explicit `on`/`off`.

A minimized/hidden window is intentionally rejected. Restore the specific returned Studio window using the available Computer Use API, then inspect it again; do not guess coordinates or arbitrary handles. Use dedicated printer tools for physical controls. Leave authentication/password/security interactions to the user. An unavailable pattern or uncertain click is not a reason to click repeatedly.

## Completion

State what changed and what was verified, identify the exact saved artifact/job and report material limitations. For status/photos, simply answer with fresh evidence. Never send GitHub/Notion updates on ordinary printer tasks unless the user requested those writes for that task.
