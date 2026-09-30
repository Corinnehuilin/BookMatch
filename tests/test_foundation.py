import tempfile
import unittest
from pathlib import Path

from bookmatch_app.storage import LibraryStore


class FoundationTests(unittest.TestCase):
    def test_shelf_survives_reopen_and_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            first = LibraryStore(path)
            book_id = first.catalog_books(limit=1)[0]["id"]
            first.set_status(book_id, "Want to Read")
            first.close()

            reopened = LibraryStore(path)
            self.assertEqual(reopened.entries(), {book_id: "Want to Read"})
            reopened.set_status(book_id, "Currently Reading")
            self.assertEqual(reopened.entries(), {book_id: "Currently Reading"})
            reopened.close()

    def test_invalid_status_does_not_change_library(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            book_id = store.catalog_books(limit=1)[0]["id"]
            with self.assertRaises(ValueError):
                store.set_status(book_id, "Lost")
            self.assertEqual(store.entries(), {})
            store.close()


if __name__ == "__main__":
    unittest.main()
