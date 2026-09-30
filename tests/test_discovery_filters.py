import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QPlainTextEdit

from bookmatch_app.recommend import Match, Preferences
from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow, SearchWorker
from bookmatch_app.widgets import BookMatchComboBox, PageNavigator


class DiscoveryFilterTests(unittest.TestCase):
    def test_results_filter_sort_page_and_keep_draft(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            store = LibraryStore(Path(folder))
            books = store.catalog_books(limit=30)
            with store.connection:
                for index, book in enumerate(books):
                    store.connection.execute(
                        "UPDATE books SET genre=?, subjects='', publication_year=? WHERE id=?",
                        ("Fantasy" if index >= 12 else "Mystery", 2022 if index >= 20 else 1980, book["id"]))
            books = store.catalog_books(limit=30)
            matches = [Match(book, index / 30, "Match explanation", "", "Metadata caveat")
                       for index, book in enumerate(books)]
            window = BookMatchWindow(store)
            try:
                window.show()
                window._discovery_query = window._discovery_draft = "a magical story"
                window._show_discovery_results(matches, "Metadata fallback", Preferences("magical", ""))
                app.processEvents()
                self.assertEqual(window._discovery_sort, "Popularity")
                self.assertEqual([match.book["id"] for match in window._filtered_discovery_results()],
                                 [book["id"] for book in books])
                navigator = window.stack.widget(2).findChild(PageNavigator)
                self.assertEqual(navigator.count, 3)
                window._discovery_go_to(2)
                self.assertEqual(window._discovery_page, 2)
                draft = window.stack.widget(2).findChild(QPlainTextEdit)
                draft.setPlainText("A new draft, still editing")
                combos = {combo.accessibleName(): combo for combo in
                          window.stack.widget(2).findChildren(BookMatchComboBox)}
                combos["Discover genre"].setCurrentText("Fantasy")
                app.processEvents()
                self.assertEqual(window._discovery_page, 0)
                self.assertEqual(len(window._filtered_discovery_results()), 18)
                self.assertEqual(window._discovery_draft, "A new draft, still editing")
                self.assertEqual(window._discovery_query, "a magical story")
                window._set_discovery_filter("_discovery_period", "2020 or later")
                self.assertEqual(len(window._filtered_discovery_results()), 10)
                self.assertEqual(len(window._discovery_results), 30)
                window._set_discovery_filter("_discovery_sort", "Best match")
                self.assertEqual(window._filtered_discovery_results()[0].book["id"], books[-1]["id"])
                window._set_discovery_filter("_discovery_topic", "Horror")
                self.assertFalse(window._filtered_discovery_results())
                window._clear_discovery_filters()
                self.assertEqual(len(window._filtered_discovery_results()), 30)
                window._set_discovery_filter("_discovery_sort", "Title A–Z")
                titles = [match.book["title"].casefold() for match in window._filtered_discovery_results()]
                self.assertEqual(titles, sorted(titles))
            finally:
                window.close()

    def test_worker_returns_matches_beyond_first_twelve_and_excludes_saved_books(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            store = LibraryStore(Path(folder))
            fantasy = store.catalog_books(topic="Fantasy", limit=2)
            store.set_status(fantasy[0]["id"], "Read")
            store.dismiss_book(fantasy[1]["id"])
            worker = SearchWorker("fantasy", store.discovery_books(), store.directory,
                                  store.catalog_books(), store.catalog_revision())
            captured = []
            worker.finished_search.connect(lambda matches, mode, prefs: captured.extend(matches))
            worker.run()
            self.assertGreater(len(captured), 12)
            ids = {match.book["id"] for match in captured}
            self.assertNotIn(fantasy[0]["id"], ids)
            self.assertNotIn(fantasy[1]["id"], ids)
            store.close()
