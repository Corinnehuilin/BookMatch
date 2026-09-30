import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QDialog, QFrame, QPushButton

from bookmatch_app.dialogs import (AddBookDialog, BookDetailsDialog, ManageShelvesDialog,
                                   NewShelfDialog, ShelfDialog)
from bookmatch_app.storage import LibraryStore, STATUSES
from bookmatch_app.transfer import export_library, import_bookmatch_json, parse_bookmatch_json
from bookmatch_app.ui import BookMatchWindow
from bookmatch_app.widgets import ShelfSection


class ShelfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = LibraryStore(self.folder / "library")

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_schema_upgrade_registers_old_shelves_without_changing_personal_data(self):
        book_id = self.store.add_book("Legacy book", "Example Author")
        with self.store.connection:
            self.store.connection.execute("UPDATE library_entries SET shelves='Favorites, Book club', notes='Keep me', rating=4.25 WHERE book_id=?", (book_id,))
            self.store.connection.execute("DROP TABLE shelf_definitions")
            self.store.connection.execute("PRAGMA user_version=10")
        self.store.close()
        self.store = LibraryStore(self.folder / "library")
        self.assertEqual(self.store.custom_shelves(), ["Book club", "Favorites"])
        self.assertEqual(self.store.book(book_id)["notes"], "Keep me")
        self.assertEqual(self.store.book(book_id)["rating"], 4.25)
        self.assertEqual([row["name"] for row in self.store.shelf_definitions() if row["builtin"]], list(STATUSES))

    def test_empty_shelves_persist_and_names_and_builtins_are_protected(self):
        self.store.create_shelf("  Book club  ")
        for name in ("book CLUB", "Read", "", "a,b", "a" * 61):
            with self.assertRaises(ValueError):
                self.store.create_shelf(name)
        for name in STATUSES:
            with self.assertRaises(ValueError):
                self.store.delete_shelf(name)
        self.store.close()
        self.store = LibraryStore(self.folder / "library")
        self.assertEqual(self.store.custom_shelves(), ["Book club"])

    def test_multi_assignment_and_delete_preserve_book_activity_and_other_shelves(self):
        book_id = self.store.add_book("Personal book", "Example Author")
        self.store.update_entry(book_id, status="Read", rating=3.75, notes="Private note",
                                review="Private review", started_on="2026-01-01",
                                finished_on="2026-01-05", shelves="Favorites, Book club")
        self.store.assign_shelves(book_id, "Read", ["favorites", "Book club", "Favorites"])
        before = self.store.book(book_id)
        self.assertEqual(before["shelves"], "Favorites, Book club")
        self.store.delete_shelf("FAVORITES")
        after = self.store.book(book_id)
        self.assertEqual(after["shelves"], "Book club")
        for key in ("title", "status", "rating", "notes", "review", "started_on", "finished_on"):
            self.assertEqual(before[key], after[key])
        self.assertEqual(self.store.custom_shelves(), ["Book club"])
        with self.assertRaises(ValueError):
            self.store.assign_shelves(book_id, "Read", ["Favorites"])

    def test_picker_and_add_details_forms_save_multiple_custom_shelves(self):
        for name in ("Favorites", "Book club"):
            self.store.create_shelf(name)
        picker = ShelfDialog("Example", "Read", store=self.store, selected="Favorites")
        self.assertEqual(picker.shelf.count(), 4)
        self.assertEqual(picker.shelf.currentText(), "Read")
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        picker.show()
        self.app.processEvents()
        club = picker.custom.checkboxes["Book club"]
        QTest.mouseClick(club, Qt.MouseButton.LeftButton)
        self.assertTrue(club.isChecked())
        QTest.keyClick(club, Qt.Key.Key_Space)
        self.assertFalse(club.isChecked())
        QTest.keyClick(club, Qt.Key.Key_Space)
        self.assertEqual(set(picker.custom.selected_shelves()), {"Favorites", "Book club"})
        picker.close()
        add = AddBookDialog(self.store)
        add.title_field.setText("Example book")
        add.author_field.setText("Example Author")
        for box in add.shelves_field.checkboxes.values():
            box.setChecked(True)
        add._save()
        self.assertEqual(add.result(), QDialog.DialogCode.Accepted)
        book = self.store.library_books()[0]
        self.assertEqual(set(book["shelves"].split(", ")), {"Favorites", "Book club"})
        details = BookDetailsDialog(self.store, book["id"])
        details.shelves_field.checkboxes["Book club"].setChecked(False)
        details._save()
        self.assertEqual(self.store.book(book["id"])["shelves"], "Favorites")
        details.close()

    def test_sections_count_shared_members_and_remember_collapse_per_page(self):
        self.store.create_shelf("Favorites")
        self.store.create_shelf("Empty shelf")
        book_id = self.store.add_book("Example book", "Example Author")
        self.store.assign_shelves(book_id, "Read", ["Favorites"])
        window = BookMatchWindow(self.store)
        window.show()
        window.navigate(1)
        self.app.processEvents()
        sections = {s.name: s for s in window.stack.widget(1).findChildren(ShelfSection)}
        self.assertIn("Read • 1", sections["Read"].header.text())
        self.assertIn("Favorites • 1", sections["Favorites"].header.text())
        self.assertIn("Empty shelf • 0", sections["Empty shelf"].header.text())
        self.assertFalse(sections["Read"].body.isHidden())
        sections["Read"].header.click()
        self.assertTrue(sections["Read"].body.isHidden())
        self.assertTrue(sections["Favorites"].body.isHidden())
        sections["Favorites"].header.click()
        self.assertFalse(sections["Favorites"].body.isHidden())
        self.assertEqual(len(sections["Favorites"].findChildren(QFrame, "surface")), 1)
        window.refresh()
        self.app.processEvents()
        refreshed = {s.name: s for s in window.stack.widget(1).findChildren(ShelfSection)}
        self.assertTrue(refreshed["Read"].body.isHidden())
        self.assertFalse(refreshed["Favorites"].body.isHidden())
        home = {s.name: s for s in window.stack.widget(0).findChildren(ShelfSection)}
        self.assertIn("Favorites • 1", home["Favorites"].header.text())
        self.assertTrue(home["Favorites"].body.isHidden())
        window.close()
        self.store = LibraryStore(self.folder / "library")
        flags = {s["name"]: s for s in self.store.shelf_definitions()}
        self.assertEqual(flags["Read"]["library_collapsed"], 1)
        self.assertEqual(flags["Favorites"]["library_collapsed"], 0)
        self.assertEqual(flags["Favorites"]["home_collapsed"], 1)

    def test_manager_has_delete_only_for_custom_shelves_and_confirms(self):
        self.store.create_shelf("Empty shelf")
        manager = ManageShelvesDialog(self.store)
        buttons = [b for b in manager.findChildren(QPushButton) if b.text() == "Delete"]
        self.assertEqual([b.accessibleName() for b in buttons], ["Delete shelf Empty shelf"])
        with patch("bookmatch_app.dialogs.QMessageBox.question", return_value=0):
            manager._delete("Empty shelf")
        self.assertIn("Empty shelf", self.store.custom_shelves())
        from PySide6.QtWidgets import QMessageBox
        with patch("bookmatch_app.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            buttons[0].click()
        self.assertEqual(self.store.custom_shelves(), [])
        self.assertEqual(len(self.store.shelf_definitions()), 4)
        manager.close()
        new = NewShelfDialog(self.store)
        new.name_field.setText("Read")
        new._save()
        self.assertNotEqual(new.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(new.error.text())
        new.close()

    def test_backup_restores_empty_shelves_memberships_and_collapsed_state(self):
        self.store.create_shelf("Empty shelf")
        self.store.set_shelf_collapsed("Empty shelf", "home", False)
        book_id = self.store.add_book("Example book", "Example Author")
        self.store.update_entry(book_id, status="Read", rating=4.25, notes="Private",
                                review="", started_on=None, finished_on=None, shelves="Favorites")
        self.store.set_shelf_collapsed("Read", "library", True)
        path = self.folder / "backup.json"
        export_library(self.store, path)
        restored = LibraryStore(self.folder / "restored")
        try:
            import_bookmatch_json(restored, parse_bookmatch_json(path))
            self.assertEqual(restored.custom_shelves(), ["Empty shelf", "Favorites"])
            self.assertEqual(restored.book(book_id)["shelves"], "Favorites")
            self.assertEqual(restored.book(book_id)["notes"], "Private")
            flags = {s["name"]: s for s in restored.shelf_definitions()}
            self.assertEqual(flags["Empty shelf"]["home_collapsed"], 0)
            self.assertEqual(flags["Read"]["library_collapsed"], 1)
        finally:
            restored.close()

    def test_large_shelf_pages_keep_full_count_and_lazy_collapsed_body(self):
        books = [{"title": str(i)} for i in range(25)]
        from PySide6.QtWidgets import QLabel
        section = ShelfSection("Favorites", books, lambda b: QLabel(b["title"]),
                               collapsed=True, compact=True)
        self.assertEqual(section.body_layout.count(), 0)
        section.header.click()
        self.assertEqual(len(section.body.findChildren(QLabel)), 12)
        section._go_to(2)
        self.app.sendPostedEvents(None, 0)
        self.assertEqual(section.body_layout.count(), 2)  # Last book plus pager.
        self.assertIn("Favorites • 25", section.header.text())
        section.close()

    def test_shelf_page_survives_refresh_and_filter_change_starts_at_first_page(self):
        for i in range(13):
            self.store.add_book(f"Example book {i}", "Example Author")
        window = BookMatchWindow(self.store)
        window.show()
        window.navigate(1)
        self.app.processEvents()
        section = next(s for s in window.stack.widget(1).findChildren(ShelfSection) if s.name == "Want to Read")
        section._go_to(1)
        window.refresh()
        self.app.processEvents()
        section = next(s for s in window.stack.widget(1).findChildren(ShelfSection) if s.name == "Want to Read")
        self.assertEqual(section.page, 1)
        window._set_library_sort("Title A–Z")
        section = next(s for s in window.stack.widget(1).findChildren(ShelfSection) if s.name == "Want to Read")
        self.assertEqual(section.page, 0)
        window.close()
        self.store = LibraryStore(self.folder / "library")

    def test_settings_imports_backup_containing_empty_shelves_and_no_books(self):
        self.store.create_shelf("Empty shelf")
        path = self.folder / "empty-backup.json"
        export_library(self.store, path)
        self.store.delete_shelf("Empty shelf")
        window = BookMatchWindow(self.store)
        from PySide6.QtWidgets import QMessageBox
        with patch("bookmatch_app.ui.QFileDialog.getOpenFileName", return_value=(str(path), "")), \
                patch("bookmatch_app.ui.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes), \
                patch("bookmatch_app.ui.QMessageBox.information"):
            window._import_json()
        self.assertEqual(self.store.custom_shelves(), ["Empty shelf"])
        self.assertEqual(self.store.entries(), {})
        window.close()
        self.store = LibraryStore(self.folder / "library")
