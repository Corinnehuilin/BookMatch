import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QFrame

from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow
from bookmatch_app.widgets import RatingSummary


class LibraryCardTests(unittest.TestCase):
    def test_saved_quarter_rating_appears_only_on_its_library_card(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            rated_id = store.add_book("Rated book", "A. Reader")
            unrated_id = store.add_book("Unrated book", "A. Reader")
            store.update_entry(rated_id, status="Read", rating=4.25,
                               notes="", review="", started_on=None, finished_on=None)
            window = BookMatchWindow(store)
            try:
                window.show()
                window.navigate(1)
                app.processEvents()
                cards = {card.property("bookId"): card
                         for card in window.stack.widget(1).findChildren(QFrame)
                         if card.property("bookId")}
                rated = cards[rated_id].findChild(RatingSummary, "ratingSummary")
                self.assertIsNotNone(rated)
                self.assertEqual(rated.rating, 4.25)
                self.assertEqual(rated.accessibleName(),
                                 "Your rating: 4.25 out of 5 stars")
                self.assertIsNone(cards[unrated_id].findChild(
                    RatingSummary, "ratingSummary"))
            finally:
                window.close()
