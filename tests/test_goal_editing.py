import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtWidgets import QApplication, QDialog, QGridLayout, QLabel, QPushButton, QMessageBox
from bookmatch_app.dialogs import GoalDialog
from bookmatch_app.storage import LibraryStore
from bookmatch_app.ui import BookMatchWindow


class GoalEditingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.store = LibraryStore(self.folder)
        book_id = self.store.add_book("An example book", "Example Author")
        self.store.update_entry(book_id, status="Read", rating=4.25, notes="Private note",
                                review="", started_on=None, finished_on="2026-05-01")
        self.store.add_goal("My goal", "2026-01-01", "2026-12-31", 12)
        self.goal = self.store.goals()[0]

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_deleting_selected_goal_keeps_books_shelves_and_other_goals(self):
        book_id = self.store.library_books()[0]["id"]
        self.store.create_shelf("Favorites")
        self.store.assign_shelves(book_id, "Read", ["Favorites"])
        selected_id = self.store.add_goal("Selected goal", "2026-01-01", "2026-12-31", 1,
                                          book_ids=[book_id])
        before = self.store.library_books()
        shelves = self.store.shelf_definitions()
        goal = next(goal for goal in self.store.goals() if goal["id"] == selected_id)
        dialog = GoalDialog(self.store, goal=goal)
        with patch("bookmatch_app.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Cancel):
            dialog.delete_button.click()
        self.assertEqual(len(self.store.goals()), 2)
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        with patch("bookmatch_app.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            dialog.delete_button.click()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.store.goals(), [self.goal])
        self.assertEqual(self.store.connection.execute("SELECT COUNT(*) FROM goal_books").fetchone()[0], 0)
        self.assertEqual(self.store.library_books(), before)
        self.assertEqual(self.store.shelf_definitions(), shelves)
        with self.assertRaises(ValueError):
            self.store.delete_goal(selected_id)
        dialog.close()
        create = GoalDialog(self.store)
        self.assertFalse(hasattr(create, "delete_button"))
        create.close()

    def test_deletion_from_home_or_stats_refreshes_both_and_tagline_is_removed(self):
        window = BookMatchWindow(self.store)
        window.show()

        def delete_dialog(store, parent, *, goal):
            dialog = GoalDialog(store, parent, goal=goal)
            with patch("bookmatch_app.dialogs.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                dialog.delete_button.click()
            dialog.exec = lambda: QDialog.DialogCode.Accepted
            return dialog

        try:
            for index in (0, 3):
                if not self.store.goals():
                    self.store.add_goal("My goal", "2026-01-01", "2026-12-31", 12)
                    window.refresh()
                window.navigate(index)
                self.app.processEvents()
                button = next(b for b in window.stack.widget(index).findChildren(QPushButton)
                              if b.text() == "Edit goal")
                with patch("bookmatch_app.ui.GoalDialog", side_effect=delete_dialog):
                    button.click()
                self.app.processEvents()
                self.assertEqual(window.stack.currentIndex(), index)
                self.assertEqual(self.store.goals(), [])
                for page in (0, 3):
                    self.assertFalse(any(b.text() == "Edit goal" for b in
                                         window.stack.widget(page).findChildren(QPushButton)))
            window.sidebar_toggle.setChecked(True)
            window.sidebar_toggle.setChecked(False)
            self.assertFalse(any("a quieter place to read" in label.text().lower()
                                 for label in window.findChildren(QLabel)))
        finally:
            window.close()

    def test_edit_updates_same_goal_and_recounts_dates_without_changing_books(self):
        self.assertEqual(self.goal["completed"], 1)
        books_before = self.store.library_books()
        self.store.update_goal(self.goal["id"], "Summer goal", "2026-06-01", "2026-09-30", 5)
        self.store.close()
        self.store = LibraryStore(self.folder)
        goals = self.store.goals()
        self.assertEqual(len(goals), 1)
        self.assertEqual(goals[0]["id"], self.goal["id"])
        self.assertEqual(goals[0]["label"], "Summer goal")
        self.assertEqual(goals[0]["target_books"], 5)
        self.assertEqual(goals[0]["completed"], 0)
        self.assertEqual(self.store.library_books(), books_before)
        with self.assertRaises(ValueError):
            self.store.update_goal(self.goal["id"], "Invalid dates", "2026-12-31", "2026-01-01", 5)
        with self.assertRaises(ValueError):
            self.store.update_goal(-1, "Missing goal", "2026-01-01", "2026-12-31", 5)
        self.assertEqual(self.store.goals(), goals)

    def test_dialog_prefills_validates_and_cancels_without_changes(self):
        dialog = GoalDialog(self.store, goal=self.goal)
        self.assertEqual(dialog.windowTitle(), "Edit reading goal")
        self.assertEqual(dialog.name_field.text(), "My goal")
        self.assertEqual(dialog.start_field.text(), "2026-01-01")
        self.assertEqual(dialog.end_field.text(), "2026-12-31")
        self.assertEqual(dialog.target_field.value(), 12)
        dialog.start_field.setText("not a date")
        with patch("bookmatch_app.dialogs.QMessageBox.warning") as warning:
            dialog._save()
        warning.assert_called_once()
        self.assertNotEqual(dialog.result(), QDialog.DialogCode.Accepted)
        dialog.reject()
        self.assertEqual(self.store.goals(), [self.goal])
        saved = GoalDialog(self.store, goal=self.goal)
        saved.name_field.setText("Updated goal")
        saved.target_field.setValue(24)
        saved._save()
        self.assertEqual(saved.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(len(self.store.goals()), 1)
        self.assertEqual(self.store.goals()[0]["target_books"], 24)
        self.assertEqual(self.store.goals()[0]["completed"], 1)
        saved.close()

    def test_home_and_stats_edit_buttons_save_and_refresh_current_page(self):
        window = BookMatchWindow(self.store)
        window.show()
        self.app.processEvents()

        def edited_dialog(store, parent, *, goal):
            dialog = GoalDialog(store, parent, goal=goal)
            dialog.name_field.setText("My revised goal")
            dialog.target_field.setValue(goal["target_books"] + 1)
            dialog._save()
            dialog.exec = lambda: QDialog.DialogCode.Accepted
            return dialog

        try:
            for index in (0, 3):
                window.navigate(index)
                self.app.processEvents()
                button = next(b for b in window.stack.widget(index).findChildren(QPushButton)
                              if b.text() == "Edit goal")
                with patch("bookmatch_app.ui.GoalDialog", side_effect=edited_dialog):
                    button.click()
                self.app.processEvents()
                self.assertEqual(window.stack.currentIndex(), index)
                self.assertEqual(len(self.store.goals()), 1)
                self.assertTrue(any("My revised goal" in label.text() for label in
                                    window.stack.widget(index).findChildren(QLabel)))
            self.assertEqual(self.store.goals()[0]["target_books"], 14)
        finally:
            window.close()

    def test_home_at_glance_reflows_from_three_across_to_one_above_two(self):
        window = BookMatchWindow(self.store)
        window.show()
        try:
            for width, compact in ((1300, False), (850, True), (1300, False)):
                window.resize(width, 820)
                for _ in range(4):
                    self.app.processEvents()
                grid = window.stack.widget(0).findChild(QGridLayout, "readingAtGlance")
                positions = [grid.getItemPosition(i) for i in range(3)]
                self.assertEqual(positions, [(0, 0, 1, 2), (1, 0, 1, 1), (1, 1, 1, 1)] if compact
                                 else [(0, 0, 1, 1), (0, 1, 1, 1), (0, 2, 1, 1)])
                cards = [grid.itemAt(i).widget() for i in range(3)]
                self.assertEqual([c.property("statCaption") for c in cards],
                                 ["On your shelves", "Reading now", "Finished"])
                if compact:
                    self.assertGreater(cards[0].width(), cards[1].width() * 1.9)
                    self.assertAlmostEqual(cards[1].width(), cards[2].width(), delta=1)
                    self.assertEqual(cards[1].y(), cards[2].y())
                    self.assertGreater(cards[1].y(), cards[0].y())
        finally:
            window.close()
