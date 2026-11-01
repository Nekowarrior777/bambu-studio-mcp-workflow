"""Active-tab evidence crosses the native-helper/MCP boundary without new input.

These are protocol tests with an in-memory adapter. They do not start the native
helper, Bambu Studio, a network connection, slicing, or a physical print.
"""
import copy
import unittest

from local_extension.ui import UiController, UiError


def active_tab(tab_id="prepare", *, verified=True):
    return {
        "id": tab_id,
        "verified": verified,
        "source": "native_book_selection",
        "profile": "fixture-only",
        "evidence": {"selected_index": 0 if tab_id == "prepare" else 1},
        "reason": None if verified else "No unique active page was observed",
    }


class ProtocolHelper:
    """Return the native protocol, recording every simulated input attempt."""

    def __init__(self):
        self.actions = []
        self.active = active_tab()
        self.caption = "Предпросмотр нарезки"
        self.fail_after_input = False
        self.reply = self.tab_reply("tab_switch_confirmed", True, "preview")

    def tab_reply(self, outcome, confirmed, after_id, *, poll_count=2):
        return {
            "ok": True,
            "action_attempted": outcome != "already_in_requested_state",
            "action": "click",
            "outcome": outcome,
            "verification": {
                "confirmed": confirmed,
                "requested_tab": "preview",
                "before": copy.deepcopy(self.active),
                "after": active_tab(after_id),
                "poll_count": poll_count,
            },
        }

    def __call__(self, request):
        if request["op"] == "act":
            self.actions.append(copy.deepcopy(request))
            if self.fail_after_input:
                raise OSError("The native result was lost after input")
            return copy.deepcopy(self.reply)
        return {
            "ok": True,
            "window": {"window_id": 1, "process_id": 99,
                       "title": "fixture - BambuStudio"},
            "active_tab": copy.deepcopy(self.active),
            "elements": [{
                "token": "navigation", "parent_token": "topbar",
                "name": self.caption, "enabled": True, "offscreen": False,
                "control_type": "ControlType.Pane", "class_name": "wxWindowNR",
                "depth": 3, "hwnd": 30, "parent_names": ["control"],
            }],
        }


class ActiveTabProtocolTests(unittest.TestCase):
    def setUp(self):
        self.helper = ProtocolHelper()
        self.ui = UiController(self.helper, clock=lambda: 100.0)

    def observe(self, name_filter=""):
        return self.ui.inspect(1, name_filter)

    def click(self, observation, *, execute=True):
        return self.ui.action(observation["snapshot_id"], "navigation", "click",
                              execute=execute)

    def assert_consumed_without_replay(self, observation):
        before = len(self.helper.actions)
        with self.assertRaisesRegex(UiError, "expired or was consumed"):
            self.click(observation)
        self.assertEqual(before, len(self.helper.actions))

    def test_inspect_keeps_tab_evidence_when_filter_matches_no_elements(self):
        observation = self.observe("no control has this caption")
        self.assertEqual([], observation["elements"])
        self.assertEqual(self.helper.active, observation["active_tab"])
        self.assertTrue(observation["active_tab"]["verified"])
        self.assertEqual([], self.helper.actions)

    def test_unknown_active_tab_is_not_promoted_to_verified(self):
        self.helper.active = active_tab(None, verified=False)
        observation = self.observe()
        self.assertIsNone(observation["active_tab"]["id"])
        self.assertFalse(observation["active_tab"]["verified"])
        self.assertEqual(self.helper.active, observation["active_tab"])
        self.assertEqual([], self.helper.actions)

    def test_confirmed_switch_evidence_is_forwarded_after_one_input(self):
        observation = self.observe()
        result = self.click(observation)
        self.assertEqual("action_attempted", result["status"])
        self.assertEqual("tab_switch_confirmed", result["result"]["outcome"])
        self.assertEqual(self.helper.reply["verification"],
                         result["result"]["verification"])
        self.assertTrue(result["result"]["verification"]["confirmed"])
        self.assertEqual("preview", result["result"]["verification"]["after"]["id"])
        self.assertEqual(1, len(self.helper.actions))
        self.assert_consumed_without_replay(observation)

    def test_unconfirmed_switch_is_reported_and_cannot_be_replayed(self):
        self.helper.reply = self.helper.tab_reply("invoked_unconfirmed", False, "prepare")
        observation = self.observe()
        result = self.click(observation)
        self.assertEqual("action_attempted", result["status"])
        self.assertEqual("invoked_unconfirmed", result["result"]["outcome"])
        verification = result["result"]["verification"]
        self.assertFalse(verification["confirmed"])
        self.assertEqual("preview", verification["requested_tab"])
        self.assertEqual("prepare", verification["after"]["id"])
        self.assertEqual(1, len(self.helper.actions))
        self.assert_consumed_without_replay(observation)

    def test_already_selected_state_preserves_native_no_input_evidence(self):
        self.helper.active = active_tab("preview")
        self.helper.reply = self.helper.tab_reply(
            "already_in_requested_state", True, "preview", poll_count=0)
        result = self.click(self.observe())
        self.assertFalse(result["result"]["action_attempted"])
        self.assertTrue(result["result"]["verification"]["confirmed"])
        self.assertEqual(0, result["result"]["verification"]["poll_count"])
        # There is one helper request, but its native protocol says no input.
        self.assertEqual(1, len(self.helper.actions))

    def test_preview_does_not_call_native_action_or_consume_observation(self):
        observation = self.observe()
        preview = self.click(observation, execute=False)
        self.assertEqual("preview", preview["status"])
        self.assertFalse(preview["dispatch_attempted"])
        self.assertEqual([], self.helper.actions)
        confirmed = self.click(observation)
        self.assertTrue(confirmed["result"]["verification"]["confirmed"])
        self.assertEqual(1, len(self.helper.actions))

    def test_lost_native_result_consumes_observation_without_replay(self):
        self.helper.fail_after_input = True
        observation = self.observe()
        with self.assertRaisesRegex(UiError, "outcome may be unknown"):
            self.click(observation)
        self.assertEqual(1, len(self.helper.actions))
        self.assert_consumed_without_replay(observation)

    def test_generic_action_remains_valid_without_tab_verification(self):
        self.helper.caption = "Качество"
        self.helper.reply = {"ok": True, "action_attempted": True,
                             "outcome": "invoked", "method": "native-pattern"}
        result = self.click(self.observe())
        self.assertEqual("action_attempted", result["status"])
        self.assertEqual("invoked", result["result"]["outcome"])
        self.assertNotIn("verification", result["result"])
        self.assertEqual("Качество", self.helper.actions[0]["element"]["name"])
        self.assertEqual(1, len(self.helper.actions))


if __name__ == "__main__":
    unittest.main()
