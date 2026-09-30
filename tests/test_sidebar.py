import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication

from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow


class SidebarTests(unittest.TestCase):
    def test_collapse_keeps_navigation_and_catalog_state(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            window = BookMatchWindow(LibraryStore(Path(folder)))
            try:
                window.show()
                window.resize(1120, 760)
                window.navigate(4)
                window._catalog_go_to(3)
                app.processEvents()
                window.stack.widget(4).verticalScrollBar().setValue(400)
                window.sidebar_toggle.click()
                app.processEvents()
                self.assertEqual(window.sidebar.width(), 76)
                self.assertFalse(window._responsive_compact)
                self.assertEqual(window.stack.currentIndex(), 4)
                self.assertEqual(window._catalog_page, 3)
                self.assertEqual(window.stack.widget(4).verticalScrollBar().value(), 400)
                self.assertEqual(window.sidebar_toggle.accessibleName(), "Expand sidebar")
                for index, button in enumerate(window.nav_buttons):
                    self.assertEqual(button.text(), window.NAV_ICONS[index])
                    self.assertEqual(button.toolTip(), window.PAGES[index])
                    button.click()
                    self.assertEqual(window.stack.currentIndex(), index)
                    self.assertTrue(button.property("active"))
                window.sidebar_toggle.click()
                app.processEvents()
                self.assertEqual(window.sidebar.width(), 232)
                self.assertTrue(window._responsive_compact)
                self.assertEqual(window.stack.currentIndex(), 5)
                self.assertEqual(window._catalog_page, 3)
                self.assertTrue(window._brand_label.isVisible())
                self.assertEqual(window.sidebar_toggle.accessibleName(), "Collapse sidebar")
            finally:
                window.close()
