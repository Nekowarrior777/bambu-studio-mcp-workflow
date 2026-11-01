"""One-attempt print dispatch guard; all printer and desktop I/O is injected.

This module never opens a transport or presses a key by itself. A successful
receipt means the official app accepted submission, not that plastic was printed.
Adapters must observe the actual saved file, current printer, and visible dialog.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import ntpath
import os
from pathlib import Path
import re
import secrets
import time


class GuardError(RuntimeError):
    """A required observation or binding did not permit dispatch."""


class DispatchUncertain(GuardError):
    """Input may have happened; never replay it automatically."""


def _path(value):
    if not isinstance(value, str) or not value.strip():
        raise GuardError("A nonempty absolute file path is required")
    if os.name == "nt":
        # resolve also expands Windows' 8.3 aliases (TEMP commonly uses one).
        return os.path.normcase(str(Path(value).resolve()))
    if ntpath.isabs(value) and ntpath.splitdrive(value)[0]:
        return ntpath.normcase(ntpath.normpath(value))
    return os.path.normcase(str(Path(value).resolve()))


def _number(value, label):
    if isinstance(value, bool):
        raise GuardError(f"{label} must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise GuardError(f"{label} must be a finite number") from None
    if not math.isfinite(number):
        raise GuardError(f"{label} must be a finite number")
    return number


def _text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise GuardError(f"Missing {label}")
    return value.strip()


def _same(value, expected, label):
    if value != expected:
        raise GuardError(f"{label} changed or does not match the prepared print")


class DispatchService:
    """Persisted single-use tickets bind a print artifact to one official dialog.

    inspect_file(path): sha256, model, nozzle_diameter, material, bed_temperature,
      job_name. The hash is independently checked against the actual file bytes.
    observe_printer(): read_at (epoch seconds), state, serial, model,
      nozzle_diameter, material, errors (list), job_name (string, may be empty).
    observe_ui(): pid, hwnd, file_path, job_name, printer_name, printer_serial,
      process_path, enabled; either element_hwnd or send_bounds (left/top/right/bottom).
    click_ui(expected_ui): must recheck the expected element itself at input time.
      Return status='submitted' only after observing official submission progress.
      Any other result or exception is an uncertain input outcome.
    """
    UI_FIELDS = ("pid", "hwnd", "element_hwnd", "window_title", "file_path", "job_name",
                 "printer_name", "printer_serial", "printer_selector_token", "printer_selector_hwnd",
                 "send_bounds", "enabled", "process_path")
    MAX_AGE = 10.0
    TICKET_LIFETIME = 60.0

    def __init__(self, inspect_file, observe_printer, observe_ui, click_ui,
                 persistencefolder, *, clock=time.time):
        self.inspect_file = inspect_file
        self.observe_printer = observe_printer
        self.observe_ui = observe_ui
        self.click_ui = click_ui
        self.folder = Path(persistencefolder).resolve()
        self.folder.mkdir(parents=True, exist_ok=True)
        self.clock = clock

    @staticmethod
    def _digest(path):
        try:
            with open(path, "rb") as stream:
                return hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise GuardError("The exact print file is unavailable") from error

    def _artifact(self, path):
        path = str(Path(path).resolve())
        before = self._digest(path)
        raw = self.inspect_file(path)
        if not isinstance(raw, dict):
            raise GuardError("File inspection returned no evidence")
        sha = raw.get("sha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise GuardError("File inspection did not return an exact SHA256")
        _same(sha, before, "File hash")
        _same(self._digest(path), before, "File hash during inspection")
        nozzle = _number(raw.get("nozzle_diameter"), "Nozzle diameter")
        bed = _number(raw.get("bed_temperature"), "Bed temperature")
        if nozzle <= 0 or bed <= 0:
            raise GuardError("File nozzle diameter and bed temperature must be positive")
        return {"file_path": path, "sha256": sha,
                "model": _text(raw.get("model"), "file model").upper(),
                "nozzle_diameter": nozzle,
                "material": _text(raw.get("material"), "file material").upper(),
                "bed_temperature": bed,
                "job_name": _text(raw.get("job_name"), "file job name")}

    def _printer(self, artifact, serial, bed_cleared):
        raw = self.observe_printer()
        if not isinstance(raw, dict):
            raise GuardError("Printer observation is missing")
        now = self.clock()
        read_at = _number(raw.get("read_at"), "Printer observation timestamp")
        if now - read_at > self.MAX_AGE or read_at > now + 2:
            raise GuardError("Printer observation is stale or has an invalid future timestamp")
        _same(raw.get("serial"), serial, "Printer serial")
        _same(_text(raw.get("model"), "observed printer model").upper(), artifact["model"], "Printer model")
        _same(_number(raw.get("nozzle_diameter"), "Observed nozzle diameter"), artifact["nozzle_diameter"], "Printer nozzle")
        _same(_text(raw.get("material"), "observed material").upper(), artifact["material"], "Printer material")
        if not isinstance(raw.get("errors"), list) or raw["errors"]:
            raise GuardError("Printer errors are active or have not been observed")
        if raw.get("print_error") not in (None, 0):
            raise GuardError("Printer reports an active print error")
        state = raw.get("state")
        if state not in ("IDLE", "FINISH"):
            raise GuardError(f"Printer is not ready: {state or 'UNKNOWN'}")
        if state == "FINISH" and bed_cleared is not True:
            raise GuardError("The finished job needs explicit bed-clearance confirmation")
        if not isinstance(raw.get("job_name"), str):
            raise GuardError("Observed printer job identity is missing")
        return {"serial": serial, "model": artifact["model"], "state": state,
                "job_name": raw["job_name"], "read_at": read_at}

    def _ui(self, artifact, serial, printer_name):
        raw = self.observe_ui()
        if not isinstance(raw, dict):
            raise GuardError("Official print dialog observation is missing")
        for field in ("pid", "hwnd"):
            if type(raw.get(field)) is not int or raw[field] <= 0:
                raise GuardError(f"Print dialog {field} is missing")
        process = _text(raw.get("process_path"), "official app process path")
        if ntpath.basename(process).lower() != "bambu-studio.exe":
            raise GuardError("The print dialog does not belong to Bambu Studio")
        if not (ntpath.isabs(process) or os.path.isabs(process)):
            raise GuardError("Official app process path must be absolute")
        if raw.get("enabled") is not True:
            raise GuardError("The official Send button is not enabled")
        _same(_path(raw.get("file_path")), _path(artifact["file_path"]), "Dialog print file")
        _same(raw.get("job_name"), artifact["job_name"], "Dialog job name")
        _same(raw.get("printer_serial"), serial, "Dialog printer serial")
        _same(raw.get("printer_name"), printer_name, "Dialog printer name")
        element = raw.get("element_hwnd")
        bounds = raw.get("send_bounds")
        if bounds is not None:
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
                raise GuardError("Send button bounds are malformed")
            values = [_number(value, "Send button bound") for value in bounds]
            if values[2] <= values[0] or values[3] <= values[1]:
                raise GuardError("Send button bounds are empty")
        if not (type(element) is int and element > 0) and bounds is None:
            raise GuardError("No stable Send button identity or bounds were observed")
        return {key: raw[key] for key in self.UI_FIELDS if key in raw}

    def _read(self, path):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("not an object")
            return raw
        except (OSError, ValueError) as error:
            raise GuardError("Dispatch evidence is unavailable or malformed; refusing to replay") from error

    def _write(self, path, value, *, exclusive=False):
        data = json.dumps(value, ensure_ascii=True, indent=2)
        if exclusive:
            try:
                with path.open("x", encoding="utf-8") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError as error:
                raise GuardError("This dispatch was already consumed or is being submitted") from error
        else:
            temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
            with temporary.open("x", encoding="utf-8") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)

    def _unresolved(self, serial):
        for path in self.folder.glob("receipt-*.json"):
            receipt = self._read(path)
            if receipt.get("printer_serial") == serial and receipt.get("status") != "submitted":
                raise GuardError("An earlier Send attempt has an uncertain outcome; check the printer and reconcile its receipt before any new attempt")

    @contextmanager
    def _lease(self, serial):
        lock = self.folder / ("printer-" + hashlib.sha256(serial.encode()).hexdigest() + ".lock")
        try:
            with lock.open("x", encoding="utf-8") as stream:
                stream.write(str(os.getpid()))
        except FileExistsError as error:
            raise GuardError("Another dispatch is in progress, or a previous process ended during dispatch; inspect its receipt") from error
        try:
            yield
        finally:
            lock.unlink()

    def _check(self, file_path, serial, printer_name, bed_cleared):
        serial = _text(serial, "target printer serial")
        printer_name = _text(printer_name, "target printer name")
        self._unresolved(serial)
        artifact = self._artifact(file_path)
        printer = self._printer(artifact, serial, bed_cleared)
        ui = self._ui(artifact, serial, printer_name)
        return artifact, printer, ui

    def diagnose(self, file_path, printer_serial, printer_name, bed_cleared=False):
        """Read-only preflight: no ticket and no UI input, including when busy."""
        try:
            artifact, printer, ui = self._check(file_path, printer_serial, printer_name, bed_cleared)
            return {"ready": True, "artifact": artifact, "printer": printer, "ui": ui,
                    "dispatch_attempted": False}
        except (GuardError, OSError, ValueError) as error:
            return {"ready": False, "reason": str(error), "dispatch_attempted": False}

    def prepare(self, file_path, printer_serial, printer_name, bed_cleared=False):
        artifact, printer, ui = self._check(file_path, printer_serial, printer_name, bed_cleared)
        token = secrets.token_hex(24)
        now = self.clock()
        ticket = {"created_at": now, "expires_at": now + self.TICKET_LIFETIME,
                  "artifact": artifact, "printer": printer, "ui": ui,
                  "printer_name": printer_name, "bed_cleared": bed_cleared is True}
        self._write(self.folder / f"ticket-{token}.json", ticket, exclusive=True)
        return {"ticket": token, **ticket, "dispatch_attempted": False}

    def submit(self, ticket):
        if not isinstance(ticket, str) or not re.fullmatch(r"[0-9a-f]{48}", ticket):
            raise GuardError("Invalid dispatch ticket")
        path = self.folder / f"ticket-{ticket}.json"
        receipt_path = self.folder / f"receipt-{ticket}.json"
        if receipt_path.exists():
            raise GuardError("This ticket was already consumed; never replay Send")
        prepared = self._read(path)
        try:
            serial = prepared["printer"]["serial"]
            with self._lease(serial):
                if receipt_path.exists():
                    raise GuardError("This ticket was already consumed; never replay Send")
                if self.clock() > prepared["expires_at"] or self.clock() < prepared["created_at"] - 2:
                    raise GuardError("Dispatch ticket expired or the clock changed")
                artifact, printer, ui = self._check(prepared["artifact"]["file_path"], serial,
                                                    prepared["printer_name"], prepared["bed_cleared"])
                _same(artifact, prepared["artifact"], "Inspected artifact")
                _same(ui, prepared["ui"], "Official dialog binding")
                _same(printer["state"], prepared["printer"]["state"], "Printer state")
                _same(printer["job_name"], prepared["printer"]["job_name"], "Printer job")
                _same(self._digest(artifact["file_path"]), artifact["sha256"], "File immediately before Send")
                if self.clock() > prepared["expires_at"] or self.clock() - printer["read_at"] > self.MAX_AGE:
                    raise GuardError("Dispatch evidence expired before Send")
                receipt = {"ticket": ticket, "printer_serial": serial, "printer_name": prepared["printer_name"],
                           "file_path": artifact["file_path"], "sha256": artifact["sha256"],
                           "job_name": artifact["job_name"], "bed_temperature": artifact["bed_temperature"],
                           "attempted_at": self.clock(), "status": "attempting",
                           "dispatch_attempted": True, "physical_print_verified": False}
                self._write(receipt_path, receipt, exclusive=True)
                try:
                    result = self.click_ui(ui)
                    if not isinstance(result, dict) or result.get("status") != "submitted":
                        raise DispatchUncertain("Official app submission was not observed after Send")
                    receipt["status"] = "submitted"
                    receipt["submitted_at"] = self.clock()
                    self._write(receipt_path, receipt)
                    return receipt
                except Exception as error:
                    receipt["status"] = "unknown"
                    receipt["reason"] = str(error)[:350]
                    try:
                        self._write(receipt_path, receipt)
                    except OSError:
                        # The already-fsynced 'attempting' receipt still consumes
                        # this ticket and blocks a later process from replaying it.
                        pass
                    raise DispatchUncertain("Send may have happened. Its ticket is consumed; check printer status and do not retry automatically") from error
        except (KeyError, TypeError) as error:
            raise GuardError("Dispatch ticket is malformed") from error
