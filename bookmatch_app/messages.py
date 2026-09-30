"""Text-only notices and confirmations shared by every app window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox as QtMessageBox


class MessageBox(QtMessageBox):
    @classmethod
    def _show(cls, parent, title, text, buttons, defaultButton):
        dialog = cls(parent)
        dialog.setOption(cls.Option.DontUseNativeDialog, True)
        dialog.setWindowTitle(title)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(text)
        dialog.setIcon(cls.Icon.NoIcon)
        dialog.setStandardButtons(buttons)
        if defaultButton != cls.StandardButton.NoButton:
            dialog.setDefaultButton(defaultButton)
        return cls.StandardButton(dialog.exec())

    @classmethod
    def information(cls, parent, title, text, buttons=QtMessageBox.StandardButton.Ok,
                    defaultButton=QtMessageBox.StandardButton.NoButton):
        return cls._show(parent, title, text, buttons, defaultButton)

    warning = information
    critical = information

    @classmethod
    def question(cls, parent, title, text,
                 buttons=QtMessageBox.StandardButton.Yes | QtMessageBox.StandardButton.No,
                 defaultButton=QtMessageBox.StandardButton.No):
        return cls._show(parent, title, text, buttons, defaultButton)
