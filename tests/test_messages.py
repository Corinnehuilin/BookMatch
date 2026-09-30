import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel
from bookmatch_app.messages import MessageBox


class MessageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_all_notice_types_have_no_icon_and_return_clicked_button(self):
        seen = []

        def inspect(dialog):
            seen.append(dialog)
            self.assertEqual(dialog.icon(), MessageBox.Icon.NoIcon)
            self.assertTrue(dialog.testOption(MessageBox.Option.DontUseNativeDialog))
            self.assertEqual(dialog.text(), "Example text")
            self.assertFalse(any(label.objectName() == "qt_msgboxex_icon_label"
                                 and not label.pixmap().isNull()
                                 for label in dialog.findChildren(QLabel)))
            return MessageBox.StandardButton.Ok

        with patch.object(MessageBox, "exec", inspect):
            for method in (MessageBox.information, MessageBox.warning, MessageBox.critical):
                self.assertEqual(method(None, "Example title", "Example text"),
                                 MessageBox.StandardButton.Ok)
        self.assertEqual(len(seen), 3)

    def test_confirmation_keeps_cancel_default_and_selected_result(self):
        def inspect(dialog):
            self.assertEqual(dialog.icon(), MessageBox.Icon.NoIcon)
            self.assertEqual(dialog.standardButton(dialog.defaultButton()), MessageBox.StandardButton.Cancel)
            self.assertEqual(dialog.standardButtons(),
                             MessageBox.StandardButton.Yes | MessageBox.StandardButton.Cancel)
            return MessageBox.StandardButton.Yes
        with patch.object(MessageBox, "exec", inspect):
            result = MessageBox.question(None, "Delete goal", "Example goal",
                                         MessageBox.StandardButton.Yes | MessageBox.StandardButton.Cancel,
                                         MessageBox.StandardButton.Cancel)
        self.assertEqual(result, MessageBox.StandardButton.Yes)
