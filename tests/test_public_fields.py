import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

from bookmatch_app.dialogs import AddBookDialog, BookDetailsDialog
from bookmatch_app.metadata import genre_from_subjects
from bookmatch_app.storage import LibraryStore


WORK_ID = "OL5738147W"  # Elantris in the bundled public catalog.


class PublicFieldTests(unittest.TestCase):
    def test_title_field_matches_author_height_and_keeps_full_title(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            store = LibraryStore(Path(directory))
            title = "A Particularly Long Book Title That Extends Beyond the Visible Field"
            book_id = store.add_book(title, "A. Writer")
            dialog = BookDetailsDialog(store, book_id)
            dialog.show()
            app.processEvents()
            self.assertIsInstance(dialog.title_field, QLineEdit)
            self.assertEqual(dialog.title_field.height(), dialog.author_field.height())
            self.assertEqual(dialog.title_field.text(), title)
            self.assertEqual(dialog.title_field.toolTip(), title)
            dialog.close()
            store.close()

    def test_details_lock_known_public_values_but_keep_personal_overrides(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder)
            public = store.book(WORK_ID)
            self.assertEqual(public["title"], "Elantris")
            cache = folder / "metadata-cache"
            cache.mkdir()
            (cache / f"{WORK_ID}.json").write_text(json.dumps({
                "work_id": WORK_ID, "genre": "Fantasy",
                "description": "A public description.", "publication_year": 2005,
            }), encoding="utf-8")
            store.set_status(WORK_ID, "Want to Read")
            store.fill_missing_catalog_details(
                WORK_ID, genre="Fantasy", description="A public description.")
            store.update_book(WORK_ID, title="Elantris", author="Brandon Sanderson",
                              genre="Fantasy", description="A public description.",
                              publication_year=2005)
            dialog = BookDetailsDialog(store, WORK_ID)
            self.assertTrue(dialog.title_field.isReadOnly())
            self.assertTrue(dialog.author_field.isReadOnly())
            self.assertTrue(dialog.genre_field.isReadOnly())
            self.assertTrue(dialog.description_field.isReadOnly())
            self.assertTrue(dialog.year_field.isReadOnly())
            self.assertFalse(dialog.notes_field.isReadOnly())
            self.assertTrue(dialog.status_field.isEnabled())
            dialog.close()

            store.update_book(WORK_ID, title="Elantris, my edition",
                              author="Brandon Sanderson", genre="My category",
                              description="My own summary", publication_year=2006)
            override = BookDetailsDialog(store, WORK_ID)
            self.assertFalse(override.title_field.isReadOnly())
            self.assertTrue(override.author_field.isReadOnly())
            self.assertFalse(override.genre_field.isReadOnly())
            self.assertFalse(override.description_field.isReadOnly())
            self.assertFalse(override.year_field.isReadOnly())
            override.close()
            store.close()

    def test_catalog_add_locks_public_fields_and_manual_mode_unlocks(self):
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder)
            dialog = AddBookDialog(store)
            with patch("bookmatch_app.dialogs.CatalogPickerDialog") as picker:
                picker.return_value.exec.return_value = QDialog.DialogCode.Accepted
                picker.return_value.book_id = WORK_ID
                dialog._choose_catalog()
            self.assertTrue(dialog.title_field.isReadOnly())
            self.assertTrue(dialog.author_field.isReadOnly())
            self.assertEqual(dialog.genre_field.text(),
                             genre_from_subjects(store.book(WORK_ID)["subjects"]))
            self.assertTrue(dialog.genre_field.isReadOnly())
            self.assertFalse(dialog.description_field.isReadOnly())
            self.assertFalse(dialog.year_field.isReadOnly())
            self.assertTrue(dialog.status_field.isEnabled())

            cache = folder / "metadata-cache"
            cache.mkdir()
            result = {"work_id": WORK_ID, "description": "A public description.",
                      "genre": "Fantasy", "publication_year": 2005}
            (cache / f"{WORK_ID}.json").write_text(json.dumps(result), encoding="utf-8")
            dialog._metadata_loaded(result)
            self.assertTrue(dialog.description_field.isReadOnly())
            self.assertTrue(dialog.year_field.isReadOnly())

            dialog._use_manual_entry()
            self.assertIsNone(dialog.selected_book_id)
            for field in (dialog.title_field, dialog.author_field, dialog.genre_field,
                          dialog.description_field, dialog.year_field):
                self.assertFalse(field.isReadOnly())
            dialog.close()
            store.close()
