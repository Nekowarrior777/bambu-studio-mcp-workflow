"""Dispatch guard tests use fake adapters and never contact a printer or UI."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_extension.dispatch import DispatchService, GuardError, DispatchUncertain


class Fixture:
    def __init__(self, folder):
        self.now = 1000.0
        self.path = folder / "impeller.gcode.3mf"
        self.path.write_bytes(b"verified print bytes")
        self.store = folder / "receipts"
        self.printer = {"read_at": self.now, "state": "IDLE", "serial": "01PTEST",
                        "model": "P1S", "nozzle_diameter": 0.4, "material": "ABS",
                        "errors": [], "job_name": ""}
        self.ui = {"pid": 123, "hwnd": 456, "element_hwnd": 789,
                   "file_path": str(self.path), "job_name": "impeller", "printer_name": "My P1S",
                   "printer_serial": "01PTEST", "send_bounds": [10, 20, 90, 60], "enabled": True,
                   "process_path": r"C:\Program Files\Bambu Studio\bambu-studio.exe"}
        self.clicks = 0
        self.click_result = {"status": "submitted"}
        self.raise_click = False
        self.block_click = None
        self.clicked_event = threading.Event()

    def inspect(self, path):
        return {"sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "model": "P1S",
                "nozzle_diameter": 0.4, "material": "ABS", "bed_temperature": 90,
                "job_name": "impeller"}

    def observe(self):
        return dict(self.printer)

    def observe_ui(self):
        return dict(self.ui)

    def click(self, expected):
        self.clicks += 1
        self.clicked_event.set()
        if self.block_click:
            self.block_click.wait(2)
        if self.raise_click:
            raise TimeoutError("UI refresh lost after input")
        return self.click_result

    def service(self):
        return DispatchService(self.inspect, self.observe, self.observe_ui, self.click,
                               self.store, clock=lambda: self.now)

    def prepare(self, service=None, bed_cleared=True):
        return (service or self.service()).prepare(str(self.path), "01PTEST", "My P1S", bed_cleared)


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.fx = Fixture(Path(self.tmp.name))

    def test_prepare_is_read_only_and_submit_records_before_click(self):
        service = self.fx.service()
        prepared = self.fx.prepare(service)
        self.assertEqual(0, self.fx.clicks)
        original = self.fx.click
        def click(expected):
            records = list(self.fx.store.glob("receipt-*.json"))
            self.assertEqual(1, len(records))
            self.assertEqual("attempting", json.loads(records[0].read_text())["status"])
            self.assertEqual(self.fx.ui, expected)
            return original(expected)
        service.click_ui = click
        receipt = service.submit(prepared["ticket"])
        self.assertEqual("submitted", receipt["status"])
        self.assertFalse(receipt["physical_print_verified"])
        self.assertEqual(1, self.fx.clicks)

    def test_busy_diagnostics_and_prepare_never_click(self):
        for state in ["RUNNING", "PAUSE", "PREPARE", "SLICING", "FAILED", "UNKNOWN", ""]:
            self.fx.printer["state"] = state
            service = self.fx.service()
            self.assertFalse(service.diagnose(str(self.fx.path), "01PTEST", "My P1S", True)["ready"])
            with self.assertRaises(GuardError):
                self.fx.prepare(service)
        self.assertEqual(0, self.fx.clicks)
        self.assertEqual([], list(self.fx.store.glob("ticket-*.json")))

    def test_finished_job_requires_bed_clearance(self):
        self.fx.printer.update(state="FINISH", job_name="old job")
        with self.assertRaises(GuardError):
            self.fx.prepare(bed_cleared=False)
        self.assertIn("ticket", self.fx.prepare(bed_cleared=True))

    def test_stale_missing_future_reports_reject(self):
        for read_at in [None, 989, 1003]:
            self.fx.printer["read_at"] = read_at
            with self.assertRaises(GuardError):
                self.fx.prepare()
        self.assertEqual(0, self.fx.clicks)

    def test_wrong_identity_hardware_material_and_error_reject(self):
        original = dict(self.fx.printer)
        for key, value in [("serial", "wrong"), ("model", "A1"), ("nozzle_diameter", .6),
                           ("material", "PLA"), ("errors", [{"hms": "fault"}]), ("errors", None)]:
            self.fx.printer = {**original, key: value}
            with self.assertRaises(GuardError, msg=key):
                self.fx.prepare()

    def test_changed_file_rejects_before_input(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.path.write_bytes(b"changed file")
        with self.assertRaises(GuardError):
            service.submit(ticket)
        self.assertEqual(0, self.fx.clicks)

    def test_changed_dialog_target_or_selection_rejects_before_input(self):
        for key, value in [("pid", 124), ("hwnd", 457), ("element_hwnd", 790),
                           ("printer_name", "other"), ("printer_serial", "other"),
                           ("send_bounds", [11, 20, 90, 60]), ("enabled", False),
                           ("file_path", "other.3mf"), ("job_name", "other")]:
            with self.subTest(key=key):
                original = dict(self.fx.ui)
                service = self.fx.service()
                ticket = self.fx.prepare(service)["ticket"]
                self.fx.ui[key] = value
                with self.assertRaises(GuardError):
                    service.submit(ticket)
                self.fx.ui = original
        self.assertEqual(0, self.fx.clicks)

    def test_expiry_and_busy_change_after_prepare_reject(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.now += 61
        self.fx.printer["read_at"] = self.fx.now
        with self.assertRaises(GuardError):
            service.submit(ticket)
        self.fx.now = 1000
        self.fx.printer["read_at"] = 1000
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.printer["state"] = "RUNNING"
        with self.assertRaises(GuardError):
            service.submit(ticket)
        self.assertEqual(0, self.fx.clicks)

    def test_used_ticket_rejected_after_service_restart(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        service.submit(ticket)
        with self.assertRaises(GuardError):
            self.fx.service().submit(ticket)
        self.assertEqual(1, self.fx.clicks)

    def test_unknown_click_never_retries_and_blocks_new_prepare(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.raise_click = True
        with self.assertRaises(DispatchUncertain):
            service.submit(ticket)
        with self.assertRaises(GuardError):
            self.fx.service().submit(ticket)
        with self.assertRaises(GuardError):
            self.fx.prepare()
        self.assertEqual(1, self.fx.clicks)

    def test_unconfirmed_click_result_is_uncertain(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.click_result = {"clicked": True}
        with self.assertRaises(DispatchUncertain):
            service.submit(ticket)
        self.assertEqual(1, self.fx.clicks)

    def test_receipt_update_failure_still_surfaces_uncertain_and_blocks_replay(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        original = service._write
        def write(path, value, *, exclusive=False):
            if not exclusive:
                raise OSError("disk no longer writable after input")
            return original(path, value, exclusive=exclusive)
        service._write = write
        with self.assertRaises(DispatchUncertain):
            service.submit(ticket)
        with self.assertRaises(GuardError):
            self.fx.service().submit(ticket)
        with self.assertRaises(GuardError):
            self.fx.prepare()
        self.assertEqual(1, self.fx.clicks)

    def test_concurrent_calls_attempt_input_once(self):
        service = self.fx.service()
        ticket = self.fx.prepare(service)["ticket"]
        self.fx.block_click = threading.Event()
        outcomes = []
        def submit():
            try:
                outcomes.append(service.submit(ticket)["status"])
            except GuardError:
                outcomes.append("blocked")
        first = threading.Thread(target=submit)
        first.start()
        self.assertTrue(self.fx.clicked_event.wait(2))
        second = threading.Thread(target=submit)
        second.start()
        second.join(2)
        self.fx.block_click.set()
        first.join(2)
        self.assertFalse(first.is_alive() or second.is_alive())
        self.assertCountEqual(["submitted", "blocked"], outcomes)
        self.assertEqual(1, self.fx.clicks)

    def test_invalid_ticket_and_non_studio_process_reject(self):
        with self.assertRaises(GuardError):
            self.fx.service().submit("../../ticket")
        self.fx.ui["process_path"] = r"C:\other.exe"
        with self.assertRaises(GuardError):
            self.fx.prepare()


if __name__ == "__main__":
    unittest.main()
