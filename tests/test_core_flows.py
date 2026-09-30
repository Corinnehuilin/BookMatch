import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookmatch_app.recommend import parse_preferences, recommend
from bookmatch_app.storage import LibraryStore
from bookmatch_app.transfer import (
    export_library,
    import_bookmatch_json,
    import_goodreads,
    parse_bookmatch_json,
    parse_goodreads_csv,
)


class CoreFlowTests(unittest.TestCase):
    def test_upgrade_permanently_removes_page_and_edition_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder)
            book_id = store.add_book("A Personal Book", "A. Reader")
            with store.connection:
                store.connection.execute("ALTER TABLE books ADD COLUMN pages INTEGER")
                store.connection.execute("ALTER TABLE books ADD COLUMN isbn TEXT")
                store.connection.execute("ALTER TABLE library_entries ADD COLUMN pages_read INTEGER")
                store.connection.execute("UPDATE books SET pages=321, isbn='9780000000001' WHERE id=?", (book_id,))
                store.connection.execute("UPDATE library_entries SET pages_read=123 WHERE book_id=?", (book_id,))
                store.connection.execute("PRAGMA user_version = 9")
            store.close()
            upgraded = LibraryStore(folder)
            self.assertEqual(upgraded.connection.execute("PRAGMA user_version").fetchone()[0], 12)
            self.assertNotIn("pages", upgraded.book(book_id))
            self.assertNotIn("isbn", upgraded.book(book_id))
            self.assertNotIn("pages_read", upgraded.book(book_id))
            self.assertEqual(upgraded.book(book_id)["title"], "A Personal Book")
            export_path = folder / "export.json"
            export_library(upgraded, export_path)
            exported = export_path.read_text(encoding="utf-8")
            self.assertNotIn("pages_read", exported)
            self.assertNotIn('"pages"', exported)
            self.assertNotIn('"isbn"', exported)
            upgraded.close()

    def test_public_details_fill_only_blank_catalog_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            book_id = "OL17930368W"
            store.set_status(book_id, "Want to Read")
            store.fill_missing_catalog_details(book_id, genre="Self-help",
                                               description="Public description")
            self.assertEqual(store.book(book_id)["genre"], "Self-help")
            self.assertEqual(store.book(book_id)["description"], "Public description")
            store.update_book(book_id, title="Atomic Habits", author="James Clear",
                              genre="My category", description="My edited summary",
                              publication_year=2018)
            store.fill_missing_catalog_details(book_id, genre="Psychology",
                                               description="A later public summary")
            self.assertEqual(store.book(book_id)["genre"], "My category")
            self.assertEqual(store.book(book_id)["description"], "My edited summary")
            store.close()

    def test_catalog_book_can_be_added_with_enriched_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            work = store.catalog_books(limit=1)[0]
            store.add_catalog_book(
                work["id"], title=work["title"], author=work["author"], genre="Nonfiction",
                description="Public work summary", publication_year=2018,
                status="Want to Read",
            )
            saved = store.book(work["id"])
            self.assertEqual(saved["source"], "openlibrary")
            self.assertEqual(saved["source_url"], work["source_url"])
            self.assertEqual(saved["subjects"], work["subjects"])
            self.assertEqual(saved["description"], "Public work summary")
            self.assertNotIn("pages", saved)
            self.assertNotIn("isbn", saved)
            self.assertEqual(saved["status"], "Want to Read")
            with self.assertRaises(ValueError):
                store.add_catalog_book(work["id"], title=work["title"], author=work["author"],
                                       genre="", description="",
                                       publication_year=None, status="Read")
            store.close()

    def test_legacy_samples_leave_catalog_without_losing_saved_book(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            with store.connection:
                store.connection.execute("ALTER TABLE books ADD COLUMN pages INTEGER")
                store.connection.execute("ALTER TABLE books ADD COLUMN isbn TEXT")
                store.connection.execute("ALTER TABLE library_entries ADD COLUMN pages_read INTEGER")
                for book_id in ("sample-keep", "sample-unused"):
                    store.connection.execute(
                        "INSERT INTO books (id, title, author, source, source_id) VALUES (?, ?, ?, 'sample', ?)",
                        (book_id, book_id, "Example Author", book_id),
                    )
                store.connection.execute(
                    "INSERT INTO library_entries (book_id, status) VALUES ('sample-keep', 'Want to Read')"
                )
                store.connection.execute("PRAGMA user_version = 8")
            store.close()
            restored = LibraryStore(Path(directory))
            self.assertIsNotNone(restored.book("sample-keep"))
            self.assertIsNone(restored.book("sample-unused"))
            self.assertIn("sample-keep", restored.entries())
            restored.close()

    def test_catalog_refresh_keeps_personal_entry_and_paged_results(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder / "app")
            existing = store.catalog_books(limit=1)[0]
            store.set_status(existing["id"], "Currently Reading")
            store.update_entry(existing["id"], status="Currently Reading", rating=None,
                               notes="My private note", review="",
                               started_on=None, finished_on=None)
            store.close()
            catalog_path = folder / "catalog.json"
            catalog_path.write_text(json.dumps({
                "catalog_revision": "replacement-test",
                "books": [
                    {"id": "OL999999999W", "title": "The First Popular Book", "author": "A. Writer",
                     "genre": "", "publication_year": 2020, "subjects": ["Mystery"],
                     "url": "https://openlibrary.org/works/OL999999999W", "read_count": 100, "rank": 1},
                    {"id": existing["id"], "title": existing["title"], "author": existing["author"],
                     "genre": "", "publication_year": None, "subjects": [],
                     "url": existing["source_url"], "read_count": 90, "rank": 2},
                ],
            }), encoding="utf-8")
            with patch("bookmatch_app.storage.CATALOG_PATH", catalog_path):
                restored = LibraryStore(folder / "app")
                self.assertEqual(restored.catalog_count(), 2)
                self.assertEqual(restored.catalog_books(limit=1)[0]["title"], "The First Popular Book")
                self.assertEqual(restored.catalog_books(limit=1, offset=1)[0]["id"], existing["id"])
                self.assertEqual(restored.book(existing["id"])["notes"], "My private note")
                restored.close()

    def test_personal_book_roundtrip_and_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder / "original")
            book_id = store.add_book("An Invented Title", "A. Reader", genre="Mystery")
            store.update_entry(book_id, status="Read", rating=4.25, notes="Keep private",
                               review="A thoughtful mystery",
                               started_on="2026-01-04", finished_on="2026-01-10",
                               shelves="Book club, Favorites")
            self.assertEqual(store.custom_shelves(), ["Book club", "Favorites"])
            store.add_goal("This year", "2026-01-01", "2026-12-31", 12)
            self.assertEqual(store.goals()[0]["completed"], 1)
            export_path = folder / "library.json"
            self.assertEqual(export_library(store, export_path), 1)
            store.close()

            restored = LibraryStore(folder / "restored")
            preview = parse_bookmatch_json(export_path)
            self.assertEqual(import_bookmatch_json(restored, preview)["added"], 1)
            self.assertEqual(import_bookmatch_json(restored, preview)["skipped"], 1)
            book = restored.book(book_id)
            self.assertEqual(book["rating"], 4.25)
            self.assertEqual(book["notes"], "Keep private")
            self.assertEqual(book["finished_on"], "2026-01-10")
            self.assertEqual(book["shelves"], "Book club, Favorites")
            restored.close()

    def test_goodreads_preview_and_duplicate_handling(self):
        csv_text = (
            "Book Id,Title,Author,My Rating,Exclusive Shelf,Number of Pages,Date Read,Private Notes\n"
            "42,The First Book,M. Writer,4.25,read,301,2026/03/12,A private note\n"
            "43,The Second Book,N. Writer,0,to-read,,,\n"
            "44,Missing Author,,3,read,,,\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / "goodreads.csv"
            path.write_text(csv_text, encoding="utf-8")
            preview = parse_goodreads_csv(path)
            self.assertEqual(preview.valid_count, 2)
            self.assertEqual(len(preview.errors), 1)
            store = LibraryStore(folder / "app")
            self.assertEqual(import_goodreads(store, preview)["added"], 2)
            self.assertEqual(import_goodreads(store, preview)["skipped"], 2)
            self.assertEqual(store.book("goodreads-42")["rating"], 4.25)
            self.assertEqual(store.book("goodreads-42")["notes"], "A private note")
            store.close()

    def test_recommendation_separates_avoidance_and_works_without_model(self):
        prefs = parse_preferences("I want eerie friendships, but don't want graphic violence")
        self.assertIn("friendships", prefs.wanted)
        self.assertIn("violence", prefs.avoided)
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            matches, mode, _ = recommend("eerie friendships but no violence",
                                         store.discovery_books(), Path(directory), limit=8)
            self.assertEqual(mode, "Metadata fallback")
            self.assertTrue(matches)
            self.assertTrue(all("violence" not in match.explanation.casefold() for match in matches))
            store.close()


if __name__ == "__main__":
    unittest.main()
