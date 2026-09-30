import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication

from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow


class HomePicksTests(unittest.TestCase):
    def test_ten_unique_eligible_picks_stable_until_added_and_reshuffled_on_reopen(self):
        app = QApplication.instance() or QApplication([])
        calls = []

        def shuffle(_random, items):
            if items:
                if not calls:
                    items.reverse()
                else:
                    items[:] = items[10:] + items[:10]
                calls.append(list(items))

        with tempfile.TemporaryDirectory() as folder, patch("bookmatch_app.ui.SystemRandom.shuffle", shuffle):
            store = LibraryStore(Path(folder))
            for book in store.catalog_books(limit=5):
                store.set_status(book["id"], "Read")
            window = BookMatchWindow(store)
            try:
                first = [book["id"] for book in window._home_picks()]
                eligible = {book["id"] for book in store.catalog_books(limit=75, shelf="Not on my shelves")}
                self.assertEqual(len(first), 10)
                self.assertEqual(len(set(first)), 10)
                self.assertTrue(set(first).issubset(eligible))
                window.refresh()
                self.assertEqual([book["id"] for book in window._home_picks()], first)
                store.set_status(first[0], "Want to Read")
                refreshed = [book["id"] for book in window._home_picks()]
                self.assertNotIn(first[0], refreshed)
                self.assertEqual(len(refreshed), 10)
                self.assertEqual(refreshed[:9], first[1:])
            finally:
                window.close()
            reopened = BookMatchWindow(LibraryStore(Path(folder)))
            try:
                next_mix = [book["id"] for book in reopened._home_picks()]
                self.assertNotEqual(next_mix, refreshed)
                self.assertEqual(len(set(next_mix)), 10)
                self.assertFalse(set(next_mix) & set(reopened.store.entries()))
            finally:
                reopened.close()
