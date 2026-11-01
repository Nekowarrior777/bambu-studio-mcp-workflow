import unittest

from local_extension.ui import UiController, UiError, validate_general_action


class FakeHelper:
    def __init__(self):
        self.actions = []
        self.caption = "Качество"
        self.elements = None

    def __call__(self, request):
        if request["op"] == "act":
            self.actions.append(request)
            return {"ok": True, "dispatched": True}
        return {"ok": True, "window": {"id": 1, "title": "test - BambuStudio"},
                "elements": self.elements if self.elements is not None else
                [{"token": "target", "name": self.caption, "enabled": True,
                  "control_type": "Pane", "hwnd": 10, "parent_token": "root"}]}


class UiTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.helper = FakeHelper()
        self.ui = UiController(self.helper, clock=lambda: self.now)

    def observe(self):
        return self.ui.inspect(1)["snapshot_id"]

    def test_preview_does_not_click(self):
        result = self.ui.action(self.observe(), "target", "click")
        self.assertEqual(result["status"], "preview")
        self.assertEqual(self.helper.actions, [])

    def test_observed_button_can_be_clicked_once(self):
        snapshot = self.observe()
        self.ui.action(snapshot, "target", "click", execute=True)
        self.assertEqual(len(self.helper.actions), 1)
        with self.assertRaises(UiError):
            self.ui.action(snapshot, "target", "click", execute=True)
        self.assertEqual(len(self.helper.actions), 1)

    def test_old_snapshot_and_unknown_element_reject(self):
        snapshot = self.observe()
        with self.assertRaises(UiError):
            self.ui.action(snapshot, "other", "click", execute=True)
        self.now += 31
        with self.assertRaises(UiError):
            self.ui.action(snapshot, "target", "click", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_final_send_is_not_a_generic_click(self):
        self.helper.caption = "Отправить"
        with self.assertRaisesRegex(UiError, "studio_prepare_send"):
            self.ui.action(self.observe(), "target", "click", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_print_and_printer_controls_cannot_bypass_dispatch(self):
        for caption in ["Send", "Start print", "Печать", "Возобновить", "Unload", "Температура"]:
            self.helper.caption = caption
            with self.assertRaises(UiError, msg=caption):
                self.ui.action(self.observe(), "target", "click", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_security_and_login_controls_block(self):
        self.helper.caption = "Войти в аккаунт"
        with self.assertRaises(UiError):
            self.ui.action(self.observe(), "target", "click", execute=True)

    def test_semantic_parent_names_guard_unnamed_children(self):
        for parents in [["Отправить", "Отправка задания на печать"], ["Принтер"], ["Войти в аккаунт"]]:
            with self.assertRaises(UiError):
                validate_general_action({"name": "", "ancestors": ["opaque-runtime-hash"],
                                         "parent_names": parents, "enabled": True}, "click")

    def test_set_value_and_selection_are_explicit_actions(self):
        self.ui.action(self.observe(), "target", "set_value", value="0.16", execute=True)
        self.ui.action(self.observe(), "target", "select", execute=True)
        self.assertEqual([x["action"] for x in self.helper.actions], ["set_value", "select"])
        self.assertEqual(self.helper.actions[0]["value"], "0.16")

    def test_unknown_or_partial_outcome_is_consumed(self):
        def helper(request):
            if request["op"] == "act":
                raise OSError("result not available")
            return self.helper(request)
        self.ui.helper = helper
        snapshot = self.observe()
        with self.assertRaises(UiError):
            self.ui.action(snapshot, "target", "click", execute=True)
        with self.assertRaises(UiError):
            self.ui.action(snapshot, "target", "click", execute=True)

    @staticmethod
    def device_controls():
        # Studio's actual Device UI uses numeric heater captions and anonymous
        # panel ancestors, rather than a semantic "Device" ancestor.
        return [
            {"token": "camera-source", "name": "MqttSource", "control_type": "ControlType.Image",
             "parent_token": "root", "enabled": True, "offscreen": False},
            {"token": "heater", "name": "90", "control_type": "ControlType.Edit", "hwnd": 20,
             "parent_token": "anonymous", "parent_names": ["90", "panel", "panel"],
             "enabled": True, "offscreen": False, "depth": 9},
        ]

    @staticmethod
    def navigation_control(name="Подготовка", token="navigation"):
        return {"token": token, "name": name, "control_type": "ControlType.Pane",
                "class_name": "wxWindowNR", "hwnd": 30, "parent_token": "topbar",
                "parent_names": ["control", "", "test - BambuStudio"],
                "enabled": True, "offscreen": False, "depth": 3}

    def test_device_view_blocks_numeric_heater_without_device_ancestor(self):
        self.helper.elements = self.device_controls()
        for action in ["set_value", "click"]:
            with self.assertRaisesRegex(UiError, "dedicated printer"):
                self.ui.action(self.observe(), "heater", action, value="100", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_device_progress_and_control_markers_also_block(self):
        for progress, control in [("Прогресс печати", "Управление"), ("Print progress", "Control")]:
            self.helper.elements = self.device_controls()[1:] + [
                {"token": "progress", "name": progress, "control_type": "ControlType.Text", "offscreen": False},
                {"token": "control", "name": control, "control_type": "ControlType.Text", "offscreen": False},
            ]
            with self.assertRaises(UiError):
                self.ui.action(self.observe(), "heater", "set_value", value="100", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_device_view_preserves_unambiguous_top_navigation(self):
        for name in ["Подготовка", "Предпросмотр нарезки", "Принтер", "Проект"]:
            self.helper.elements = self.device_controls() + [self.navigation_control(name)]
            self.ui.action(self.observe(), "navigation", "click", execute=True)
        self.assertEqual(len(self.helper.actions), 4)
        self.assertEqual([r["element"]["name"] for r in self.helper.actions],
                         ["Подготовка", "Предпросмотр нарезки", "Принтер", "Проект"])

    def test_device_navigation_caption_on_wrong_control_is_blocked(self):
        fake = self.navigation_control()
        fake["parent_names"] = ["panel", "panel"]
        self.helper.elements = self.device_controls() + [fake]
        with self.assertRaises(UiError):
            self.ui.action(self.observe(), "navigation", "click", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_duplicate_top_navigation_does_not_authorize_either_control(self):
        self.helper.elements = self.device_controls() + [self.navigation_control(),
                                                        self.navigation_control(token="duplicate")]
        with self.assertRaises(UiError):
            self.ui.action(self.observe(), "navigation", "click", execute=True)
        self.assertEqual(self.helper.actions, [])

    def test_hidden_device_markers_do_not_block_project_edit(self):
        self.helper.elements = self.device_controls()
        self.helper.elements[0]["offscreen"] = True
        self.ui.action(self.observe(), "heater", "set_value", value="0.16", execute=True)
        self.assertEqual(len(self.helper.actions), 1)


if __name__ == "__main__":
    unittest.main()
