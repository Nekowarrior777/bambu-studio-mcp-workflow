"""Source-distribution configuration boundaries; no UI or printer transport."""
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_extension.dispatch import GuardError


class DistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = importlib.import_module("enhanced_server")

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "private-bindings.json"
        patched = patch.object(self.server, "BINDINGS_FILE", self.path)
        patched.start()
        self.addCleanup(patched.stop)
        self.submission = self.server.OfficialSubmission()

    def test_missing_private_binding_blocks_before_artifact_or_ui(self):
        with patch.object(self.server, "opened_record") as artifact:
            with self.assertRaisesRegex(GuardError, "private printer binding"):
                self.submission.bind("unused", "TEST-SERIAL", "Test printer")
            artifact.assert_not_called()

    def test_malformed_private_binding_is_an_actionable_rejection(self):
        self.path.write_text("invalid json", encoding="utf-8")
        with self.assertRaisesRegex(GuardError, "malformed"):
            self.submission.bind("unused", "TEST-SERIAL", "Test printer")

    def test_non_object_or_mismatching_binding_rejects(self):
        for value in [[], {"TEST-SERIAL": "wrong schema"}, {"TEST-SERIAL": {"studio_name": "Other printer"}}]:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(GuardError):
                    self.submission.bind("unused", "TEST-SERIAL", "Test printer")

    def test_valid_private_binding_retains_exact_serial_and_name(self):
        self.path.write_text(json.dumps({"TEST-SERIAL": {"studio_name": "Test printer"}}), encoding="utf-8")
        record = {"file_path": "synthetic", "sha256": "synthetic"}
        with patch.object(self.server, "opened_record", return_value=record):
            self.submission.bind("unused", "TEST-SERIAL", "Test printer")
        self.assertEqual("TEST-SERIAL", self.submission.serial)
        self.assertEqual("Test printer", self.submission.name)
        self.assertEqual(record, self.submission.record)

    def test_unsigned_lan_route_never_calls_original_sender(self):
        with patch.object(self.server, "ORIGINAL_SEND") as original:
            with self.assertRaises(Exception) as raised:
                self.server.send_to_printer(via="lan")
            self.assertIn("Unsigned direct LAN dispatch is disabled", str(raised.exception))
            original.assert_not_called()


if __name__ == "__main__":
    unittest.main()
