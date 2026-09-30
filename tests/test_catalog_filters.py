import tempfile
import unittest
from pathlib import Path

from bookmatch_app.storage import LibraryStore


class CatalogFilterTests(unittest.TestCase):
    def test_search_matches_title_author_genre_and_subject(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            atomic = store.catalog_books(limit=1)[0]
            self.assertEqual(atomic["title"], "Atomic Habits")
            with store.connection:
                store.connection.execute("UPDATE books SET genre=? WHERE id=?",
                                         ("Epistolary studies", atomic["id"]))
            for query in ("Atomic Habits", "James Clear", "Epistolary",
                          "Behavior modification"):
                self.assertIn(atomic["id"],
                              {book["id"] for book in store.catalog_books(query, limit=20)},
                              query)
                self.assertGreaterEqual(store.catalog_count(query), 1)
            self.assertEqual(store.catalog_count("no-match-7349z"), 0)
            store.close()

    def test_combined_filters_count_sort_and_shelf(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            books = store.catalog_books(topic="Mystery", period="2000–2009", limit=10)
            self.assertTrue(books)
            for book in books:
                text = f"{book['genre']} {book['subjects']}".casefold()
                self.assertTrue("mystery" in text or "detective" in text)
                self.assertGreaterEqual(book["publication_year"], 2000)
                self.assertLessEqual(book["publication_year"], 2009)
            book_id = books[0]["id"]
            store.set_status(book_id, "Want to Read")
            on_shelf = store.catalog_books(topic="Mystery", period="2000–2009",
                                           shelf="On my shelves")
            self.assertEqual([book["id"] for book in on_shelf], [book_id])
            self.assertEqual(store.catalog_count(topic="Mystery", period="2000–2009",
                                                 shelf="On my shelves"), 1)
            self.assertNotIn(book_id, {book["id"] for book in store.catalog_books(
                topic="Mystery", period="2000–2009", shelf="Not on my shelves")})
            titles = store.catalog_books(topic="Mystery", limit=20, sort="Title A–Z")
            self.assertEqual([book["title"].casefold() for book in titles],
                             sorted(book["title"].casefold() for book in titles))
            store.close()

    def test_unknown_filter_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            with self.assertRaises(ValueError):
                store.catalog_books(topic="' OR 1=1 --")
            with self.assertRaises(ValueError):
                store.catalog_books(sort="unsupported")
            store.close()
