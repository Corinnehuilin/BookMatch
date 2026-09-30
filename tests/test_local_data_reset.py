import sqlite3
import tempfile
import unittest
from pathlib import Path

from bookmatch_app.storage import LibraryStore


class LocalDataResetTests(unittest.TestCase):
    def test_clear_removes_memberships_and_activity_preserves_goals_shelves_and_files(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder)
            manual_id = store.add_book("Private title", "Private author")
            public_id = store.catalog_books(limit=1)[0]["id"]
            for book_id in (manual_id, public_id):
                store.update_entry(book_id, status="Read", rating=4.75,
                                   notes="Private note", review="Private review",
                                   started_on="2026-01-01", finished_on="2026-01-03",
                                   shelves="Favorites")
            store.set_shelf_collapsed("Favorites", "library", True)
            store.add_goal("All books", "2026-01-01", "2026-12-31", 10)
            store.add_goal("Selected books", "2026-01-01", "2026-12-31", 2,
                           book_ids=[manual_id, public_id])
            shelves_before = store.shelf_definitions()
            goals_before = [{**goal, "completed": 0} for goal in store.goals()]
            store.dismiss_book(public_id)
            preserved = []
            for name in ("covers", "metadata-cache", "models"):
                cache = folder / name
                cache.mkdir()
                preserved.append(cache / "cached.bin")
            preserved.extend(folder / name for name in (
                "library-before-catalog-v6.sqlite3", "user-export.json"))
            for path in preserved:
                path.write_bytes(b"keep")

            self.assertEqual(store.clear_saved_books(), 2)
            self.assertEqual(store.entries(), {})
            self.assertEqual(store.library_books(), [])
            self.assertEqual(store.stats()["total"], 0)
            self.assertIsNone(store.stats()["average_rating"])
            self.assertEqual(store.shelf_definitions(), shelves_before)
            self.assertEqual(store.goals(), goals_before)
            self.assertEqual(store.catalog_count(), 20_000)
            self.assertEqual(store.connection.execute(
                "SELECT COUNT(*) FROM dismissed_books").fetchone()[0], 1)
            for book_id in (manual_id, public_id):
                book = store.book(book_id)
                for field in ("status", "rating", "notes", "review", "started_on",
                              "finished_on", "shelves", "source_shelf"):
                    self.assertIsNone(book[field], field)
            for path in preserved:
                self.assertEqual(path.read_bytes(), b"keep")
            self.assertEqual(store.clear_saved_books(), 0)
            store.close()
            reopened = LibraryStore(folder)
            self.assertEqual(reopened.entries(), {})
            self.assertEqual(reopened.goals(), goals_before)
            reopened.close()

    def test_readding_manual_and_imported_books_starts_fresh_and_keeps_goal_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            for source in ("manual", "goodreads"):
                book_id = store.add_book(f"{source} book", "Example author")
                with store.connection:
                    store.connection.execute("UPDATE books SET source=? WHERE id=?", (source, book_id))
                store.update_entry(book_id, status="Read", rating=4.25, notes="Old note",
                                   review="Old review", started_on="2026-01-01",
                                   finished_on="2026-01-05", shelves="Favorites")
                goal_id = store.add_goal(source, "2026-01-01", "2026-12-31", 1, book_ids=[book_id])
                store.clear_saved_books()
                readded = store.add_book(f"{source} book", "Example author", genre="Mystery")
                self.assertEqual(readded, book_id)
                book = store.book(book_id)
                self.assertEqual(book["genre"], "Mystery")
                self.assertEqual(book["status"], "Want to Read")
                self.assertEqual(book["notes"], "")
                self.assertEqual(book["review"], "")
                self.assertIsNone(book["rating"])
                self.assertIsNone(book["started_on"])
                self.assertIsNone(book["finished_on"])
                goal = next(goal for goal in store.goals() if goal["id"] == goal_id)
                self.assertEqual(goal["book_ids"], [book_id])
                self.assertEqual(goal["completed"], 0)
                with self.assertRaises(ValueError):
                    store.add_book(f"{source} book", "Example author")
            store.close()

    def test_clear_failure_rolls_back_all_saved_books(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            for number in range(2):
                store.add_book(f"Book {number}", "Example author")
            before = store.library_books()
            with store.connection:
                store.connection.execute("""CREATE TRIGGER prevent_clear BEFORE DELETE ON library_entries
                    WHEN OLD.book_id = (SELECT id FROM books WHERE title = 'Book 1')
                    BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
            with self.assertRaises(sqlite3.Error):
                store.clear_saved_books()
            self.assertEqual(store.library_books(), before)
            store.close()
