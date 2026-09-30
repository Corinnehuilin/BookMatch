import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QDialog
from bookmatch_app.dialogs import GoalBooksDialog, GoalDialog
from bookmatch_app.storage import LibraryStore
from bookmatch_app.transfer import export_library, import_bookmatch_json, parse_bookmatch_json


class CustomGoalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = LibraryStore(self.folder / "library")
        self.ids = []
        for title, status, finished in (("Selected mystery", "Read", "2026-01-01"),
                                        ("Other mystery", "Read", "2026-12-31"),
                                        ("Future novel", "Want to Read", None),
                                        ("Earlier novel", "Read", "2025-12-31")):
            book_id = self.store.add_book(title, "Example Author", genre="Mystery", status=status)
            self.store.update_entry(book_id, status=status, rating=4.25, notes="Keep private",
                                    review="", started_on=None, finished_on=finished)
            self.ids.append(book_id)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _custom(self, ids):
        return self.store.add_goal("Custom goal", "2026-01-01", "2026-12-31", 3, book_ids=ids)

    def test_counts_only_selected_read_books_with_finish_dates_in_period(self):
        self._custom([self.ids[0], self.ids[0], self.ids[2], self.ids[3]])
        self.assertEqual(self.store.goals()[0]["completed"], 1)
        self.assertEqual(len(self.store.goals()[0]["book_ids"]), 3)
        self.store.set_status(self.ids[2], "Read")
        self.assertEqual(self.store.goals()[0]["completed"], 1)  # Undated reads do not count.
        self.store.update_entry(self.ids[2], status="Read", rating=4.25, notes="Keep private",
                                review="", started_on=None, finished_on="2026-12-31")
        self.assertEqual(self.store.goals()[0]["completed"], 2)
        self.store.set_status(self.ids[0], "Did Not Finish")
        self.assertEqual(self.store.goals()[0]["completed"], 1)
        self.store.add_goal("General goal", "2026-01-01", "2026-12-31", 12)
        self.assertEqual(next(g for g in self.store.goals() if g["scope"] == "all")["completed"], 2)

    def test_edit_switches_scope_in_place_and_rejects_unknown_book_without_changes(self):
        goal_id = self._custom([self.ids[0]])
        before = self.store.goals()
        with self.assertRaises(ValueError):
            self.store.update_goal(goal_id, "Custom goal", "2026-01-01", "2026-12-31", 3,
                                   book_ids=["missing-book"])
        self.assertEqual(self.store.goals(), before)
        self.store.update_goal(goal_id, "Custom goal", "2026-01-01", "2026-12-31", 3)
        goal = self.store.goals()[0]
        self.assertEqual(goal["id"], goal_id)
        self.assertEqual(goal["scope"], "all")
        self.assertEqual(goal["book_ids"], [])
        self.assertEqual(goal["completed"], 2)
        self.store.update_goal(goal_id, "Custom goal", "2026-01-01", "2026-12-31", 3,
                               book_ids=[self.ids[2]])
        self.assertEqual(self.store.goals()[0]["completed"], 0)

    def test_shelf_shortcut_is_a_snapshot_and_search_keeps_hidden_selections(self):
        self.store.create_shelf("Book club")
        self.store.assign_shelves(self.ids[0], "Read", ["Book club"])
        self.store.assign_shelves(self.ids[2], "Want to Read", ["Book club"])
        picker = GoalBooksDialog(self.store, [self.ids[1]])
        picker.shelf_filter.setCurrentText("Custom: Book club")
        self.assertEqual(set(picker.boxes), {self.ids[0], self.ids[2]})
        picker.select_shown.click()
        self.assertEqual(picker.selected_ids, set(self.ids[:3]))
        picker.search.setText("Selected mystery")
        picker.clear_shown.click()
        self.assertEqual(picker.selected_ids, {self.ids[1], self.ids[2]})
        picker.search.clear()
        self.assertFalse(picker.boxes[self.ids[0]].isChecked())
        self.assertTrue(picker.boxes[self.ids[2]].isChecked())
        selected = sorted(picker.selected_ids)
        picker.close()
        self._custom(selected)
        new_id = self.store.add_book("New book club choice", "Example Author", status="Read")
        self.store.assign_shelves(new_id, "Read", ["Book club"])
        self.assertNotIn(new_id, self.store.goals()[0]["book_ids"])
        self.store.delete_shelf("Book club")
        self.assertEqual(self.store.goals()[0]["book_ids"], selected)

    def test_goal_editor_selects_books_sets_target_and_preserves_choices_on_cancel(self):
        editor = GoalDialog(self.store)
        editor.scope_field.setCurrentIndex(1)
        with patch("bookmatch_app.dialogs.QMessageBox.warning") as warning:
            editor._save()
        warning.assert_called_once()
        self.assertEqual(self.store.goals(), [])
        with patch("bookmatch_app.dialogs.GoalBooksDialog") as picker:
            picker.return_value.exec.return_value = QDialog.DialogCode.Accepted
            picker.return_value.selected_ids = {self.ids[0], self.ids[2]}
            editor.choose_button.click()
        editor.selection_target.click()
        self.assertEqual(editor.target_field.value(), 2)
        editor._save()
        goal = self.store.goals()[0]
        self.assertEqual(goal["scope"], "selected")
        self.assertEqual(goal["completed"], 1)
        edit = GoalDialog(self.store, goal=goal)
        self.assertEqual(edit.scope_field.currentIndex(), 1)
        self.assertEqual(set(edit.book_ids), {self.ids[0], self.ids[2]})
        with patch("bookmatch_app.dialogs.GoalBooksDialog") as picker:
            picker.return_value.exec.return_value = QDialog.DialogCode.Rejected
            picker.return_value.selected_ids = {self.ids[1]}
            edit.choose_button.click()
        edit.reject()
        self.assertEqual(self.store.goals(), [goal])
        editor.close()

    def test_migration_keeps_existing_general_goals_and_progress(self):
        self.store.add_goal("Existing goal", "2026-01-01", "2026-12-31", 12)
        goal_id = self.store.goals()[0]["id"]
        with self.store.connection:
            self.store.connection.execute("DROP TABLE goal_books")
            self.store.connection.execute("ALTER TABLE goals DROP COLUMN scope")
            self.store.connection.execute("PRAGMA user_version=11")
        self.store.close()
        self.store = LibraryStore(self.folder / "library")
        goal = self.store.goals()[0]
        self.assertEqual(goal["id"], goal_id)
        self.assertEqual(goal["scope"], "all")
        self.assertEqual(goal["target_books"], 12)
        self.assertEqual(goal["completed"], 2)
        self.assertEqual(self.store.book(self.ids[0])["notes"], "Keep private")

    def test_backup_restores_scopes_selections_and_removed_book_metadata_without_duplicates(self):
        self._custom([self.ids[0], self.ids[3]])
        self.store.add_goal("General goal", "2026-01-01", "2026-12-31", 12)
        self.store.remove_from_library(self.ids[3])
        path = self.folder / "backup.json"
        export_library(self.store, path)
        restored = LibraryStore(self.folder / "restored")
        try:
            preview = parse_bookmatch_json(path)
            result = import_bookmatch_json(restored, preview)
            self.assertEqual(result["goals_added"], 2)
            self.assertEqual(result["invalid"], 0)
            custom = next(g for g in restored.goals() if g["scope"] == "selected")
            self.assertEqual(set(custom["book_ids"]), {self.ids[0], self.ids[3]})
            self.assertEqual(custom["completed"], 1)
            self.assertIsNone(restored.book(self.ids[3])["status"])
            self.assertNotIn(self.ids[3], restored.entries())
            repeat = import_bookmatch_json(restored, preview)
            self.assertEqual(repeat["goals_added"], 0)
            self.assertEqual(repeat["goals_skipped"], 2)
            self.assertEqual(len(restored.goals()), 2)
        finally:
            restored.close()

    def test_empty_imported_selection_counts_zero_and_invalid_goal_is_reported(self):
        path = self.folder / "goals.json"
        goal = {"label": "Empty selection", "start_on": "2026-01-01", "end_on": "2026-12-31",
                "target_books": 3, "scope": "selected", "book_ids": []}
        path.write_text(json.dumps({"format": "bookmatch-library", "version": 1, "books": [],
                                    "goals": [goal, {**goal, "scope": "invalid"}]}))
        preview = parse_bookmatch_json(path)
        self.assertEqual(len(preview.errors), 1)
        result = import_bookmatch_json(self.store, preview)
        self.assertEqual(result["goals_added"], 1)
        self.assertEqual(self.store.goals()[0]["scope"], "selected")
        self.assertEqual(self.store.goals()[0]["completed"], 0)

    def test_compact_goal_editor_keeps_text_fields_readable_and_save_visible(self):
        from PySide6.QtWidgets import QDialogButtonBox, QScrollArea, QStyle, QStyleOptionFrame
        from bookmatch_app.ui import BookMatchWindow
        self._custom(self.ids[:2])
        window = BookMatchWindow(self.store)
        editor = GoalDialog(self.store, window, goal=self.store.goals()[0])
        try:
            editor.resize(470, 400)
            editor.show()
            for _ in range(4):
                self.app.processEvents()
            for field in (editor.name_field, editor.start_field, editor.end_field):
                option = QStyleOptionFrame()
                field.initStyleOption(option)
                contents = field.style().subElementRect(QStyle.SubElement.SE_LineEditContents,
                                                       option, field)
                self.assertGreaterEqual(contents.height(), field.fontMetrics().height())
            scroll = editor.findChild(QScrollArea)
            self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
            save = editor.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save)
            self.assertTrue(save.isVisible())
            self.assertLess(save.mapTo(editor, save.rect().bottomRight()).y(), editor.height())
        finally:
            editor.close()
            window.close()
