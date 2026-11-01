"""Recent semantic observations and one-attempt actions in Bambu Studio only."""
import json
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid


class UiError(RuntimeError):
    pass


class WindowsHelper:
    def __init__(self, executable, studio_exe):
        self.executable = str(Path(executable).resolve())
        self.studio_exe = str(Path(studio_exe).resolve())

    def __call__(self, request):
        request = {**request, "expected_exe": self.studio_exe}
        try:
            process = subprocess.run([self.executable], input=json.dumps(request),
                                     text=True, encoding="utf-8", capture_output=True,
                                     timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired as error:
            raise UiError("Windows UI helper timed out; do not automatically repeat an action") from error
        try:
            result = json.loads(process.stdout.lstrip("\ufeff"))
        except (ValueError, TypeError) as error:
            raise UiError("Windows UI helper returned no readable result; action outcome may be unknown") from error
        if not result.get("ok"):
            raise UiError(result.get("error", "Windows UI operation failed"))
        return result


def _context(element):
    parents = element.get("parent_names", [])
    if not isinstance(parents, list):
        parents = [str(parents)]
    names = [str(p.get("name", "")) if isinstance(p, dict) else str(p) for p in parents]
    return " ".join([str(element.get("name", "")), *names]).lower()


def _mark_device_view(elements):
    """Fail closed for Device's numeric/anonymous controls, not just captions.

    Only the four observed top-level navigation controls remain clickable.
    Their process/window identity is still rechecked by the Windows adapter.
    """
    for element in elements:
        element.pop("device_view", None)
        element.pop("device_navigation", None)
    visible = [e for e in elements if e.get("offscreen") is not True]
    names = {str(e.get("name", "")).strip().casefold() for e in visible}
    mqtt_source = any(str(e.get("name", "")).strip() == "MqttSource"
                      and e.get("control_type") == "ControlType.Image" for e in visible)
    progress = bool(names & {"прогресс печати", "print progress"})
    controls = bool(names & {"управление", "control", "controls"})
    if not (mqtt_source or (progress and controls)):
        return
    navigation_names = {"подготовка", "предпросмотр нарезки", "принтер", "проект",
                        "prepare", "preview", "device", "project"}
    candidates = []
    for element in visible:
        parents = element.get("parent_names", [])
        if (str(element.get("name", "")).strip().casefold() in navigation_names
                and element.get("control_type") == "ControlType.Pane"
                and element.get("class_name") == "wxWindowNR"
                and element.get("depth") == 3
                and isinstance(parents, list) and parents and parents[0] == "control"
                and type(element.get("hwnd")) is int and element["hwnd"] > 0):
            candidates.append(element)
    counts = {}
    for element in candidates:
        name = element["name"].strip().casefold()
        counts[name] = counts.get(name, 0) + 1
    allowed = {e["token"] for e in candidates if counts[e["name"].strip().casefold()] == 1}
    for element in elements:
        element["device_view"] = True
        element["device_navigation"] = element["token"] in allowed


def validate_general_action(element, action):
    caption = str(element.get("name", "")).strip().lower()
    context = _context(element)
    if element.get("password"):
        raise UiError("Password controls require the user's direct interaction")
    if re.search(r"sign.?in|log.?in|password|privacy|security|developer mode|войти|парол|безопасност|конфиденц|режим разработчика", context):
        raise UiError("Authentication, privacy and security controls require the user's direct interaction")
    if element.get("device_view"):
        if not element.get("device_navigation") or action != "click":
            raise UiError("Physical Device controls require the dedicated printer tools")
        if element.get("enabled") is not True:
            raise UiError("The observed control is disabled")
        return
    # Final dispatch has file, identity, readiness and duplicate-send guards.
    if (caption in {"send", "отправить", "print", "печать", "start", "начать"}
            or re.search(r"start.?print|начать печать|отправка задания на печать|send print job", context)
            or any(str(p).strip().lower() in {"send", "отправить", "print", "печать", "start", "начать"}
                   for p in element.get("parent_names", []))
            or element.get("guarded_subtree")):
        raise UiError("Use studio_prepare_send and studio_submit_send for final print submission")
    # The existing printer MCP provides checked physical control operations.
    # Generic UI is for application/project controls and may not bypass them.
    if re.search(r"pause|resume|cancel print|unload|load filament|drying|температур|приостанов|возобнов|остановить печать|отменить печать|выгрузить|загрузить пруток|сушка", caption):
        raise UiError("Use the dedicated printer control tool for this physical operation")
    if re.search(r"device|устройство|камера принтера|printer control|управление принтером", context):
        raise UiError("Physical Device controls require the dedicated printer tools")
    if any(str(p).strip().lower() == "принтер" for p in element.get("parent_names", [])):
        raise UiError("Physical Device controls require the dedicated printer tools")
    if action == "click" and not caption and element.get("control_type", "").endswith("Pane"):
        raise UiError("An unnamed container is not a semantic button; inspect a specific control")
    if action not in {"click", "set_value", "select", "expand", "collapse", "toggle"}:
        raise UiError("Unsupported semantic UI action")
    if element.get("enabled") is not True:
        raise UiError("The observed control is disabled")


class UiController:
    def __init__(self, helper, *, clock=time.time):
        self.helper = helper
        self.clock = clock
        self.snapshots = {}
        self.lock = threading.Lock()

    def inspect(self, window_id=0, name_filter=""):
        result = self.helper({"op": "inspect", **({"window_id": window_id} if window_id else {})})
        if not window_id:
            return result
        elements = result.get("elements", [])
        if not isinstance(elements, list):
            raise UiError("Window inspection returned no control list")
        _mark_device_view(elements)
        by_token = {e["token"]: e for e in elements}
        # A container click must not bypass a guarded child button.
        for element in elements:
            if str(element.get("name", "")).strip().lower() in {"send", "отправить", "print", "печать", "start", "начать"}:
                parent = by_token.get(element.get("parent_token"))
                for _ in range(50):
                    if parent is None:
                        break
                    parent["guarded_subtree"] = True
                    parent = by_token.get(parent.get("parent_token"))
        token = uuid.uuid4().hex
        now = self.clock()
        with self.lock:
            self.snapshots = {k: v for k, v in self.snapshots.items() if now - v["at"] <= 30}
            self.snapshots[token] = {"at": now, "window_id": window_id,
                                     "elements": {e["token"]: e for e in elements}}
        matched = [e for e in elements if not name_filter or name_filter.casefold() in _context(e).casefold()]
        return {**result, "snapshot_id": token, "expires_in_seconds": 30,
                "elements": matched[:160], "matched_count": len(matched), "total_elements": len(elements)}

    def action(self, snapshot_id, element_token, action, value=None, execute=False):
        with self.lock:
            snapshot = self.snapshots.get(snapshot_id)
            if not snapshot or not 0 <= self.clock() - snapshot["at"] <= 30:
                raise UiError("Observation expired or was consumed; inspect the window again")
            element = snapshot["elements"].get(element_token)
            if element is None:
                raise UiError("Element was not returned by this observation")
            validate_general_action(element, action)
            if action == "set_value" and not isinstance(value, str):
                raise UiError("set_value requires a string value")
            request = {"op": "act", "window_id": snapshot["window_id"], "element": element,
                       "action": action, **({"value": value} if value is not None else {})}
            if not execute:
                return {"status": "preview", "action": action, "element": element, "dispatch_attempted": False}
            # Consume before any input. A timeout never justifies replaying a click.
            del self.snapshots[snapshot_id]
        try:
            result = self.helper(request)
        except Exception as error:
            raise UiError("UI action outcome may be unknown; observation consumed. Inspect before any further action") from error
        return {"status": "action_attempted", "result": result,
                "next": "Inspect the window to verify the resulting state; do not repeat the action automatically"}
