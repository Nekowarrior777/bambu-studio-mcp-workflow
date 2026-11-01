"""Upstream MCP plus local, observed Windows Bambu Studio control tools."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
import uuid

from mcp.server.mcpserver.exceptions import ToolError
from unofficial_bambu_mcp import server as upstream
from local_extension.dispatch import DispatchService, GuardError
from local_extension.ui import UiController, UiError, WindowsHelper

BASE = Path(__file__).resolve().parent
PRIVATE_DIR = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "BambuStudioMCPWorkflow"
STATE = Path(os.environ.get("BAMBU_WORKFLOW_STATE_DIR", str(PRIVATE_DIR / "state"))).resolve()
STATE.mkdir(parents=True, exist_ok=True)
BINDINGS_FILE = Path(os.environ.get("BAMBU_WORKFLOW_BINDINGS", str(PRIVATE_DIR / "printer-bindings.json"))).resolve()
STUDIO_EXE = Path(os.environ.get("BAMBU_STUDIO_EXE") or upstream.studio.executable()
                  or r"C:\Program Files\Bambu Studio\bambu-studio.exe").resolve()
HELPER = WindowsHelper(BASE / "local_extension" / "StudioUi.exe", STUDIO_EXE)
UI = UiController(HELPER)
ORIGINAL_SEND = upstream.send_to_printer
OPENED = STATE / "opened-print-files.json"
SEND_LOCK = threading.RLock()


def digest(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def probe(operation, file_path=None, printer_serial=None):
    request = {"op": operation}
    if file_path:
        request["file_path"] = str(file_path)
    if printer_serial:
        request["printer_serial"] = printer_serial
    result = subprocess.run([shutil.which("node") or "node", str(BASE / "local_extension" / "safety_probe.mjs")],
                            input=json.dumps(request), text=True, encoding="utf-8", capture_output=True,
                            timeout=22, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        data = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("Read-only printer/file probe returned no valid evidence") from None
    if not data.get("ok"):
        raise RuntimeError(data.get("error", "Printer/file verification failed"))
    return data


def opened_files():
    if not OPENED.exists():
        return []
    return json.loads(OPENED.read_text(encoding="utf-8"))


def remember_opened(record):
    values = [record, *opened_files()][:30]
    temporary = OPENED.with_suffix(".tmp")
    temporary.write_text(json.dumps(values, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(temporary, OPENED)


def opened_record(file_path):
    requested = os.path.normcase(str(Path(file_path).resolve()))
    records = [r for r in opened_files() if os.path.normcase(r["file_path"]) == requested]
    if len(records) != 1:
        raise GuardError("Use send_to_printer(via='bambu_studio') first; the exact opened print file must be recorded")
    record = records[0]
    if digest(record["file_path"]) != record["sha256"]:
        raise GuardError("Opened print file changed; export a fresh official Studio copy")
    return record


def window_for_record(record):
    windows = HELPER({"op": "inspect"})["windows"]
    expected_title = Path(record["file_path"]).stem + " - BambuStudio"
    matches = [w for w in windows if w["title"] == expected_title]
    if len(matches) != 1:
        raise GuardError("The unique recorded sliced-file window is missing or ambiguous; wait for Studio to open it")
    return matches[0]


def descendants(elements, root):
    tokens = {root["token"]}
    selected = []
    for _ in range(50):
        new = [e for e in elements if e.get("parent_token") in tokens and e["token"] not in tokens]
        if not new:
            break
        selected.extend(new)
        tokens.update(e["token"] for e in new)
    return selected


class OfficialSubmission:
    def __init__(self):
        self.record = None
        self.serial = None
        self.name = None
        self.target = None

    def bind(self, file_path, serial, printer_name):
        if not BINDINGS_FILE.is_file():
            raise GuardError("Configure the private printer binding file before final Send; see README")
        try:
            bindings = json.loads(BINDINGS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise GuardError("Private printer binding configuration is unreadable or malformed") from None
        if not isinstance(bindings, dict) or not isinstance(bindings.get(serial), dict):
            raise GuardError("Private printer binding configuration has no matching printer object")
        if bindings[serial].get("studio_name") != printer_name:
            raise GuardError("Printer name/serial is not in the verified Studio binding configuration")
        self.record = opened_record(file_path)
        self.serial, self.name = serial, printer_name

    def inspect_file(self, file_path):
        opened_record(file_path)
        return probe("inspect", file_path)["artifact"]

    def printer(self):
        report = probe("status", printer_serial=self.serial)["printer"]
        if report["state"] in {"IDLE", "FINISH"}:
            # Reuse the existing independent live nozzle/material/error gate.
            report = probe("preflight", self.record["file_path"], self.serial)["printer"]
        return report

    def observe_ui(self):
        record = opened_record(self.record["file_path"])
        window = window_for_record(record)
        snapshot = HELPER({"op": "inspect", "window_id": window["window_id"]})
        elements = snapshot["elements"]
        dialogs = [e for e in elements if e.get("name", "").strip().lower() in
                   {"отправка задания на печать", "send print job", "send print job to printer"}]
        if len(dialogs) != 1:
            raise GuardError("One official print submission dialog is required")
        controls = descendants(elements, dialogs[0])
        allowed_roots = {window["title"], dialogs[0]["name"]}
        if any(e.get("depth") == 0 and e.get("name") not in allowed_roots for e in elements):
            raise GuardError("Close secondary popups before preparing final Send")
        sends = [e for e in controls if e.get("name", "").strip().lower() in {"send", "отправить"}]
        if len(sends) != 1:
            raise GuardError("The final Send control is missing or ambiguous")
        names = [e.get("name", "") for e in controls]
        if not any(name == record["job_name"] or name.startswith(record["job_name"] + "_Plate ") for name in names):
            raise GuardError("Submission dialog does not show the recorded job")
        selected_names = [e for e in controls if e.get("name") == self.name
                          and not e.get("offscreen") and e.get("control_type") == "ControlType.Pane"
                          and "SelectionItemPatternIdentifiers.Pattern" not in e.get("patterns", [])]
        if len(selected_names) != 1:
            raise GuardError("Submission dialog does not show the expected selected printer name")
        if any(e.get("expand_state") == "Expanded" for e in controls):
            raise GuardError("Close printer/material dropdowns before preparing final Send")
        selected = upstream.studio.app_config().get("app", {}).get("user_last_selected_machine")
        if selected != self.serial:
            raise GuardError("Studio's selected printer serial does not match the target")
        send = sends[0]
        self.target = {"window_id": window["window_id"], "element": send}
        return {"pid": window["process_id"], "hwnd": window["window_id"],
                "element_hwnd": send["hwnd"], "window_title": window["title"],
                "file_path": record["file_path"], "job_name": record["job_name"],
                "printer_name": self.name, "printer_serial": selected,
                "printer_selector_token": selected_names[0]["token"],
                "printer_selector_hwnd": selected_names[0]["hwnd"],
                "process_path": str(STUDIO_EXE), "enabled": send.get("enabled") is True}

    def click(self, expected_ui):
        current = self.observe_ui()
        if current != expected_ui:
            raise GuardError("Official dialog changed immediately before input")
        # This is the only final UI dispatch boundary. The generic UI tool refuses Send.
        HELPER({"op": "act", **self.target, "action": "click"})
        deadline = time.monotonic() + 14
        while time.monotonic() < deadline:
            report = probe("status", printer_serial=self.serial)["printer"]
            if report["errors"]:
                raise GuardError("Printer reported an error after Send; do not retry")
            if report["state"] in {"RUNNING", "PREPARE", "SLICING"}:
                name = self.record["job_name"]
                if report["job_name"] == name or re.fullmatch(re.escape(name) + r"_Plate [1-9][0-9]*", report["job_name"]):
                    return {"status": "submitted", "printer": report}
                raise GuardError("A different printer job appeared after Send; do not retry")
            time.sleep(1)
        raise GuardError("Printer acceptance was not observed after Send; do not retry automatically")


SUBMISSION = OfficialSubmission()
DISPATCH = DispatchService(SUBMISSION.inspect_file, SUBMISSION.printer, SUBMISSION.observe_ui,
                           SUBMISSION.click, STATE / "dispatch-receipts")


@upstream.tool()
def studio_ui_status() -> dict:
    """Windows Studio UI extension health. Read-only: list real Bambu Studio windows and available operations.
    Existing project tools still operate on saved .3mf files. No printer action is performed."""
    return {"extension_version": "0.1.0", "helper_exists": Path(HELPER.executable).is_file(),
            "operations": ["inspect", "click", "set_value", "select", "expand", "collapse", "toggle"],
            "windows": HELPER({"op": "inspect"})["windows"],
            "final_send": "studio_open_print_dialog -> studio_prepare_send -> studio_submit_send",
            "note": "No screenshot is needed. Native patterns and bounded custom wx control events are supported."}


@upstream.tool()
def studio_dispatch_diagnostics(file_path: str, printer_serial: str) -> dict:
    """Read-only file and fresh printer checks, including a busy printer. No dialog, ticket or click.
    P1S 0.4 mm external-spool sliced jobs are supported by this local submission extension."""
    artifact = probe("inspect", file_path)["artifact"]
    report = probe("status", printer_serial=printer_serial)["printer"]
    ready = report["state"] in {"IDLE", "FINISH"} and not report["errors"]
    return {"artifact": artifact, "printer": report, "ready_state": ready,
            "dispatch_attempted": False, "note": "This diagnostic does not create permission or a ticket to print"}


@upstream.tool()
def studio_ui_inspect(window_id: int = 0, name_filter: str = "") -> dict:
    """Read Bambu Studio windows (window_id=0) or the actual controls of one returned window.
    Returns semantic names, tokens, parent names, enabled state, values and supported patterns.
    active_tab reports independently observed native Plater visibility on supported Studio builds;
    check verified and reason. Unsupported or ambiguous layouts return an unknown active tab.
    Control tokens are bound to a snapshot valid for 30 seconds. name_filter limits displayed controls.
    Does not press anything. Use this before each UI action."""
    return UI.inspect(window_id, name_filter)


@upstream.tool()
def studio_ui_action(snapshot_id: str, element_token: str, action: str = "click",
                     value: str | None = None, execute: bool = False) -> dict:
    """Operate an observed Bambu Studio control after the user's request: click a button/tab, set_value,
    select an item, expand/collapse a dropdown, or toggle with value='on'/'off'. execute=False previews only.
    execute=True consumes the observation and attempts input once. Inspect again to verify the result.
    Recognized Prepare/Preview clicks include result.verification.confirmed and before/after active_tab.
    A confirmed transition requires two consecutive native state reads; unconfirmed input is never replayed.
    No guessed coordinates, arbitrary keyboard or other applications. Login/security and physical printer
    controls are excluded; use the printer MCP for those. Final Send uses studio_prepare_send/submit_send.
    Only perform the requested operation; capability installation is not authorization to change a live job."""
    return UI.action(snapshot_id, element_token, action, value, execute)


@upstream.tool()
def studio_open_print_dialog(file_path: str) -> dict:
    """Open Print plate for the exact file exported by send_to_printer(via='bambu_studio').
    Opens the official submission dialog only; does not press final Send or start a print."""
    record = opened_record(file_path)
    window = window_for_record(record)
    snapshot = UI.inspect(window["window_id"])
    cached = UI.snapshots[snapshot["snapshot_id"]]
    buttons = [e for e in cached["elements"].values() if e.get("name", "").strip().lower() in
               {"распечатать стол", "print plate"} and e.get("enabled") and not e.get("offscreen")]
    if len(buttons) != 1:
        raise UiError("One enabled Print plate control is required")
    result = UI.action(snapshot["snapshot_id"], buttons[0]["token"], "click", execute=True)
    return {"file_path": record["file_path"], "action": result,
            "next": "Inspect the dialog, then studio_prepare_send with expected printer and bed clearance"}


@upstream.tool()
def studio_prepare_send(file_path: str, printer_serial: str, printer_name: str,
                        bed_cleared: bool = False, dry_run: bool = True) -> dict:
    """Check final official Studio Send: exact exported sliced file, fresh printer identity/material/nozzle,
    ready state, expected dialog/job/printer. Does not click Send. Busy printers reject.
    dry_run=True produces diagnostic evidence only. With dry_run=False and bed_cleared=True, create a
    single-use ticket valid 60 seconds. Use only for a print the user explicitly requested; then call
    studio_submit_send(ticket) without asking for the same authorization again. printer_name must exactly
    match the selected visible name, including '(LAN)' if shown. Never clear a printer error automatically."""
    with SEND_LOCK:
        SUBMISSION.bind(file_path, printer_serial, printer_name)
        if dry_run:
            return DISPATCH.diagnose(file_path, printer_serial, printer_name, bed_cleared)
        if not bed_cleared:
            raise GuardError("The build plate must be confirmed clear before preparing final Send")
        return DISPATCH.prepare(file_path, printer_serial, printer_name, bed_cleared)


@upstream.tool()
def studio_submit_send(ticket: str) -> dict:
    """Press final Send exactly once for a studio_prepare_send ticket. Starts the explicitly authorized job
    through official Bambu Studio. Rechecks file, dialog and fresh ready printer state; writes a receipt
    before input. Waits for the named job on the printer. Never auto-replay an uncertain result.
    A submitted receipt is acceptance evidence; inspect printer progress/camera separately."""
    if not re.fullmatch(r"[0-9a-f]{48}", ticket):
        raise GuardError("Invalid dispatch ticket")
    with SEND_LOCK:
        saved = json.loads((STATE / "dispatch-receipts" / f"ticket-{ticket}.json").read_text(encoding="utf-8"))
        SUBMISSION.bind(saved["artifact"]["file_path"], saved["printer"]["serial"], saved["printer_name"])
        return DISPATCH.submit(ticket)


upstream.mcp.remove_tool("send_to_printer")


@upstream.tool()
def send_to_printer(plate: int = 1, via: str = "auto", bed_leveling: bool = True,
                    timelapse: bool = False, ams_slots: list[int] | None = None, confirm: str = "") -> dict:
    """Prepare/open one sliced plate. On Windows, via='bambu_studio' (or auto without Connect) opens a unique
    SHA256-bound file in official Studio and records it. Then studio_open_print_dialog, studio_prepare_send
    and studio_submit_send can complete the requested print without a manual button press.
    This call alone does not press final Send. File/official Connect routes retain upstream behavior;
    unsigned direct LAN dispatch is disabled in this distribution."""
    if via == "lan":
        raise GuardError("Unsigned direct LAN dispatch is disabled in this distribution; use the official Bambu Studio route")
    studio_route = via == "bambu_studio" or (via == "auto" and not upstream.studio.bambu_connect())
    if not studio_route:
        return ORIGINAL_SEND(plate=plate, via=via, bed_leveling=bed_leveling, timelapse=timelapse,
                             ams_slots=ams_slots, confirm=confirm)
    result = ORIGINAL_SEND(plate=plate, via="file", bed_leveling=bed_leveling, timelapse=timelapse,
                           ams_slots=ams_slots, confirm=confirm)
    original = Path(result["print_file"])
    sha = digest(original)
    folder = Path(upstream.out_dir()) / "studio_jobs"
    folder.mkdir(exist_ok=True)
    target = folder / f"{upstream.P().name}-{sha[:10]}-{uuid.uuid4().hex[:8]}.gcode.3mf"
    with original.open("rb") as source, target.open("xb") as destination:
        shutil.copyfileobj(source, destination)
    if digest(target) != sha:
        raise GuardError("Studio print snapshot hash mismatch")
    probe("inspect", target)
    record = {"file_path": str(target.resolve()), "sha256": sha,
              "job_name": target.stem, "project_name": upstream.P().name, "created_at": time.time()}
    remember_opened(record)
    upstream.studio.open_in_gui(str(target))
    return {**result, "print_file": str(target), "sha256": sha, "via": "bambu_studio",
            "next_step": "studio_open_print_dialog(file_path), inspect, studio_prepare_send, studio_submit_send; no final Send has happened"}


if __name__ == "__main__":
    upstream.main()
