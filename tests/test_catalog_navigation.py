import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QDialog, QPushButton

from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow
from bookmatch_app.widgets import PageNavigator


class CatalogNavigationTests(unittest.TestCase):
    def test_page_links_end_arrows_and_filtered_page_count(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            window = BookMatchWindow(store)
            try:
                window.show()
                window.navigate(4)
                app.processEvents()
                navigator = window.stack.widget(4).findChild(PageNavigator)
                arrows = {button.accessibleName(): button for button in
                          navigator.findChildren(QPushButton) if button.objectName() == "pageArrow"}
                self.assertFalse(arrows["Previous page"].isEnabled())
                self.assertTrue(arrows["Next page"].isEnabled())
                last = next(button for button in navigator.findChildren(QPushButton)
                            if button.property("page") == 834)
                last.click()
                app.processEvents()
                self.assertEqual(window._catalog_page, 833)
                navigator = window.stack.widget(4).findChild(PageNavigator)
                following = next(button for button in navigator.findChildren(QPushButton)
                                 if button.accessibleName() == "Next page")
                self.assertFalse(following.isEnabled())
                self.assertEqual(window.stack.widget(4).verticalScrollBar().value(), 0)
                with patch("bookmatch_app.ui.PageJumpDialog") as jump:
                    jump.return_value.exec.return_value = QDialog.DialogCode.Accepted
                    jump.return_value.page_number.value.return_value = 417
                    window._jump_catalog_page(834)
                app.processEvents()
                self.assertEqual(window._catalog_page, 416)
                window._catalog_search("Atomic Habits")
                app.processEvents()
                navigator = window.stack.widget(4).findChild(PageNavigator)
                self.assertEqual(window._catalog_page, 0)
                self.assertEqual(navigator.count, 1)
                self.assertTrue(all(not button.isEnabled() for button in
                                   navigator.findChildren(QPushButton)
                                   if button.objectName() == "pageArrow"))
            finally:
                window.close()

    def test_saving_multiple_books_keeps_catalog_page_and_scroll(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            window = BookMatchWindow(store)
            try:
                window.show()
                window.navigate(4)
                window._catalog_go_to(3)
                app.processEvents()
                scroll = window.stack.widget(4).verticalScrollBar()
                position = min(1200, scroll.maximum())
                self.assertGreater(position, 0)
                scroll.setValue(position)
                books = store.catalog_books(limit=2, offset=72)
                for book in books:
                    with patch("bookmatch_app.ui.ShelfDialog") as picker:
                        picker.return_value.exec.return_value = QDialog.DialogCode.Accepted
                        picker.return_value.shelf.currentText.return_value = "Want to Read"
                        picker.return_value.custom.selected_shelves.return_value = []
                        window._change_status(book)
                    app.processEvents()
                    self.assertEqual(window._catalog_page, 3)
                    self.assertEqual(window.stack.currentIndex(), 4)
                    self.assertEqual(window.stack.widget(4).verticalScrollBar().value(), position)
                    self.assertEqual(store.entries()[book["id"]], "Want to Read")
            finally:
                window.close()
