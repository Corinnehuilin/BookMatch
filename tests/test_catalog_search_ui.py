import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow
from bookmatch_app.widgets import CatalogSearchLineEdit


class CatalogSearchUiTests(unittest.TestCase):
    def test_settings_clear_requires_confirmation_and_keeps_app_open(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder)
            store.add_book("My private book", "A reader")
            window = BookMatchWindow(store)
            window.show()
            window.navigate(5)
            app.processEvents()
            button = next(button for button in window.stack.widget(5).findChildren(
                QPushButton) if button.text() == "Clear saved books…")
            with patch("bookmatch_app.ui.QInputDialog.getText", return_value=("", False)):
                button.click()
            self.assertTrue((folder / "library.sqlite3").exists())
            self.assertEqual(len(store.entries()), 1)
            with patch("bookmatch_app.ui.QInputDialog.getText", return_value=("ERASE", True)), \
                    patch("bookmatch_app.ui.QMessageBox.warning") as warning:
                button.click()
            warning.assert_called_once()
            self.assertIn("Nothing has been removed", warning.call_args.args[2])
            self.assertEqual(len(store.entries()), 1)
            with patch("bookmatch_app.ui.QInputDialog.getText", return_value=("CLEAR", True)), \
                    patch("bookmatch_app.ui.QMessageBox.information") as notice:
                button.click()
            self.assertTrue((folder / "library.sqlite3").exists())
            self.assertEqual(store.entries(), {})
            self.assertTrue(window.isVisible())
            self.assertFalse(window._store_closed)
            self.assertEqual(window.stack.currentIndex(), 5)
            self.assertEqual(store.catalog_count(), 20_000)
            notice.assert_called_once()
            window.close()

    def test_search_updates_as_typed_and_keeps_focus(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            window = BookMatchWindow(store)
            try:
                window.show()
                window.navigate(4)
                app.processEvents()
                field = window.stack.widget(4).findChild(
                    CatalogSearchLineEdit, "catalogSearch")
                self.assertEqual(field.HINT, "Title, author, genre, or subject")
                field.setFocus()
                QTest.keyClicks(field, "Atomic Habits")
                QTest.qWait(400)
                replacement = window.stack.widget(4).findChild(
                    CatalogSearchLineEdit, "catalogSearch")
                self.assertEqual(window._catalog_query, "Atomic Habits")
                self.assertEqual(replacement.text(), "Atomic Habits")
                self.assertTrue(replacement.hasFocus())
                self.assertGreater(window.store.catalog_count(window._catalog_query), 0)
                self.assertLess(window.store.catalog_count(window._catalog_query), 20_000)
            finally:
                window.close()
