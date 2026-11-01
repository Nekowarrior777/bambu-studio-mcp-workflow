"""Official submission integration checks with fake UI and fake printer reports.

No helper process, printer transport, GUI, slicing or upload is started.
"""
import copy
import hashlib
import importlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_extension.dispatch import DispatchService, GuardError


class FakeUi:
    def __init__(self, record):
        self.actions = []
        title = Path(record["file_path"]).stem + " - BambuStudio"
        self.window = {"window_id": 10, "process_id": 99, "title": title}
        self.elements = [
            {"token": "root", "parent_token": "", "name": title, "depth": 0},
            {"token": "dialog", "parent_token": "root", "name": "Отправка задания на печать", "depth": 1},
            {"token": "job", "parent_token": "dialog", "name": record["job_name"] + "_Plate 1", "depth": 2},
            {"token": "selector", "parent_token": "dialog", "name": "My P1S(LAN)",
             "control_type": "ControlType.Pane", "offscreen": False, "patterns": [], "hwnd": 666, "depth": 2},
            {"token": "send", "parent_token": "dialog", "name": "Отправить", "hwnd": 777,
             "enabled": True, "depth": 2},
        ]

    def __call__(self, request):
        if request["op"] == "act":
            self.actions.append(copy.deepcopy(request))
            return {"ok": True, "action_attempted": True}
        if "window_id" not in request:
            return {"ok": True, "windows": [copy.deepcopy(self.window)]}
        return {"ok": True, "elements": copy.deepcopy(self.elements)}


class ServerExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Startup registers tools and constructs adapter objects, but no adapter
        # is invoked until an explicit tool call; every I/O entry point below is fake.
        cls.server = importlib.import_module("enhanced_server")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "impeller-0123456789-abcdefff.gcode.3mf"
        self.path.write_bytes(b"exact file bytes for fake inspector")
        self.record = {"file_path": str(self.path.resolve()), "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                       "job_name": self.path.stem, "project_name": "impeller"}
        self.ui = FakeUi(self.record)
        for target, replacement in [("HELPER", self.ui), ("opened_record", lambda path: self.record)]:
            context = patch.object(self.server, target, replacement)
            context.start()
            self.addCleanup(context.stop)
        config = patch.object(self.server.upstream.studio, "app_config",
                              lambda: {"app": {"user_last_selected_machine": "01PTEST"}})
        config.start()
        self.addCleanup(config.stop)
        self.submission = self.server.OfficialSubmission()
        self.submission.record = self.record
        self.submission.serial = "01PTEST"
        self.submission.name = "My P1S(LAN)"

    def printer_report(self, **changes):
        return {"read_at": 1000.0, "state": "IDLE", "serial": "01PTEST", "model": "P1S",
                "nozzle_diameter": .4, "material": "ABS", "errors": [], "job_name": "", **changes}

    def fake_probe(self, report):
        context = patch.object(self.server, "probe", lambda *args, **kwargs: {"printer": report})
        context.start()
        self.addCleanup(context.stop)

    def test_exact_selected_selector_is_bound(self):
        observation = self.submission.observe_ui()
        self.assertEqual("selector", observation["printer_selector_token"])
        self.assertEqual(666, observation["printer_selector_hwnd"])
        self.assertEqual(self.record["job_name"], observation["job_name"])
        self.assertEqual([], self.ui.actions)

    def test_duplicate_visible_selector_rejects(self):
        self.ui.elements.append({**self.ui.elements[3], "token": "duplicate", "hwnd": 667})
        with self.assertRaisesRegex(GuardError, "selected printer"):
            self.submission.observe_ui()
        self.assertEqual([], self.ui.actions)

    def test_unselected_list_item_does_not_prove_selected_printer(self):
        self.ui.elements[3]["patterns"] = ["SelectionItemPatternIdentifiers.Pattern"]
        with self.assertRaisesRegex(GuardError, "selected printer"):
            self.submission.observe_ui()

    def test_hidden_name_is_not_selection_evidence(self):
        self.ui.elements[3]["offscreen"] = True
        with self.assertRaisesRegex(GuardError, "selected printer"):
            self.submission.observe_ui()

    def test_expanded_dropdown_or_secondary_popup_rejects(self):
        self.ui.elements[3]["expand_state"] = "Expanded"
        with self.assertRaisesRegex(GuardError, "dropdown"):
            self.submission.observe_ui()
        self.ui.elements[3].pop("expand_state")
        self.ui.elements.append({"token": "popup", "parent_token": "", "depth": 0, "name": "Other printers"})
        with self.assertRaisesRegex(GuardError, "popups"):
            self.submission.observe_ui()

    def test_renamed_or_prefix_colliding_dialog_job_rejects(self):
        for name in ["impeller", self.record["job_name"] + "2_Plate 1", "some other job"]:
            with self.subTest(name=name):
                self.ui.elements[2]["name"] = name
                with self.assertRaisesRegex(GuardError, "recorded job"):
                    self.submission.observe_ui()
        self.assertEqual([], self.ui.actions)

    def test_config_serial_mismatch_rejects_despite_matching_name(self):
        with patch.object(self.server.upstream.studio, "app_config",
                          lambda: {"app": {"user_last_selected_machine": "OTHER"}}):
            with self.assertRaisesRegex(GuardError, "serial"):
                self.submission.observe_ui()

    def test_changed_selector_after_ticket_prevents_input(self):
        expected = self.submission.observe_ui()
        self.ui.elements[3]["hwnd"] = 667
        with self.assertRaisesRegex(GuardError, "changed"):
            self.submission.click(expected)
        self.assertEqual([], self.ui.actions)

    def test_post_send_different_job_same_project_is_not_acceptance(self):
        expected = self.submission.observe_ui()
        self.fake_probe(self.printer_report(state="RUNNING", job_name="impeller_other-job"))
        with self.assertRaisesRegex(GuardError, "different printer job"):
            self.submission.click(expected)
        self.assertEqual(1, len(self.ui.actions))

    def test_matching_job_with_active_error_is_not_silent_success(self):
        expected = self.submission.observe_ui()
        self.fake_probe(self.printer_report(state="RUNNING", job_name=self.record["job_name"], errors=[{"hms": "fault"}]))
        with self.assertRaisesRegex(GuardError, "error"):
            self.submission.click(expected)
        self.assertEqual(1, len(self.ui.actions))

    def test_accepted_named_job_is_not_claimed_as_physical_print_verification(self):
        self.fake_probe(self.printer_report(state="PREPARE", job_name=self.record["job_name"] + "_Plate 1"))
        artifact = {"sha256": self.record["sha256"], "model": "P1S", "nozzle_diameter": .4,
                    "material": "ABS", "bed_temperature": 90, "job_name": self.record["job_name"]}
        service = DispatchService(lambda path: artifact, lambda: self.printer_report(),
                                  self.submission.observe_ui, self.submission.click,
                                  Path(self.tmp.name) / "receipts", clock=lambda: 1000.0)
        ticket = service.prepare(str(self.path), "01PTEST", "My P1S(LAN)", True)["ticket"]
        receipt = service.submit(ticket)
        self.assertEqual("submitted", receipt["status"])
        self.assertFalse(receipt["physical_print_verified"])
        self.assertEqual(1, len(self.ui.actions))
        with self.assertRaises(GuardError):
            service.submit(ticket)
        self.assertEqual(1, len(self.ui.actions))


if __name__ == "__main__":
    unittest.main()
