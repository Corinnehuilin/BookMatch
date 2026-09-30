"""Capture public demo screenshots with synthetic reading data and cached cover art.

Run from the repository root with QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from bookmatch_app.recommend import recommend
from bookmatch_app.storage import LibraryStore, data_directory
from bookmatch_app.dialogs import (AddBookDialog, BookDetailsDialog, CatalogPickerDialog,
                                   ShelfDialog, ManageShelvesDialog, GoalDialog, GoalBooksDialog)
from bookmatch_app.widgets import ShelfSection
from bookmatch_app.ui import BookMatchWindow


def main() -> None:
    os.environ.setdefault("BOOKMATCH_DISABLE_COVER_DOWNLOADS", "1")
    app = QApplication([])
    app.setApplicationName("BookMatch")
    app.setOrganizationName("BookMatch")
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#f7f5ef"),
        (QPalette.ColorRole.WindowText, "#26332e"),
        (QPalette.ColorRole.Base, "#fffefa"),
        (QPalette.ColorRole.Text, "#26332e"),
        (QPalette.ColorRole.Button, "#edf2eb"),
        (QPalette.ColorRole.ButtonText, "#26332e"),
        (QPalette.ColorRole.Highlight, "#d5e3d5"),
        (QPalette.ColorRole.HighlightedText, "#234e3b"),
    ):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    output = Path(__file__).resolve().parent.parent / "screenshots"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bookmatch-demo-") as folder:
        store = LibraryStore(Path(folder))
        for name in ("Book club", "Favorites", "Next year"):
            store.create_shelf(name)
        window = BookMatchWindow(store)
        # Read only public artwork from the existing cache. Downloads are disabled;
        # the real library, notes, and reading activity are never opened.
        window.cover_cache.directory = data_directory() / "covers"
        window.resize(1180, 820)
        window.show()
        app.processEvents()
        window.grab().save(str(output / "home-with-covers.png"))
        window.navigate(4)
        app.processEvents()
        window.grab().save(str(output / "catalog-with-covers.png"))
        window.sidebar_toggle.click()
        for _ in range(6):
            app.processEvents()
        window.grab().save(str(output / "catalog-collapsed-sidebar.png"))
        window.sidebar_toggle.click()
        for _ in range(6):
            app.processEvents()
        scroll = window.stack.widget(4)
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents()
        window.grab().save(str(output / "catalog-pagination.png"))
        scroll.verticalScrollBar().setValue(0)
        shelf = ShelfDialog("Atomic Habits", "Want to Read", window, store=store)
        shelf.show()
        app.processEvents()
        shelf.shelf.showPopup()
        app.processEvents()
        shelf.shelf.view()._set_hovered(1, animate=False)
        shelf.shelf.view().window().grab().save(str(output / "shelf-options.png"))
        shelf.shelf.hidePopup()
        shelf.close()
        query = "Atmospheric mystery and friendship, but no graphic violence"
        matches, mode, prefs = recommend(query, store.discovery_books(), store.directory, limit=None)
        window._discovery_query = query
        window._discovery_draft = query
        window._discovery_results = matches
        window._discovery_mode = mode
        window._discovery_prefs = prefs
        window.refresh()
        window.navigate(2)
        app.processEvents()
        window.grab().save(str(output / "discover.png"))
        scroll = window.stack.widget(2)
        scroll.verticalScrollBar().setValue(300)
        for _ in range(6):
            app.processEvents()
        window.grab().save(str(output / "discover-filters.png"))
        scroll.verticalScrollBar().setValue(0)
        add_book = AddBookDialog(store, window)
        add_book.show()
        app.processEvents()
        add_book.grab().save(str(output / "add-book.png"))
        add_book.close()
        picker = CatalogPickerDialog(store, "Atomic", window)
        picker.show()
        app.processEvents()
        picker.grab().save(str(output / "catalog-picker.png"))
        picker.close()
        featured_id = store.catalog_books(limit=1, offset=536)[0]["id"]
        store.set_status(featured_id, "Want to Read")
        cache = store.directory / "metadata-cache"
        cache.mkdir(exist_ok=True)
        (cache / f"{featured_id}.json").write_text(
            json.dumps({"work_id": featured_id, "description": ""}), encoding="utf-8"
        )
        details = BookDetailsDialog(store, featured_id, window)
        details.show()
        app.processEvents()
        details.grab().save(str(output / "book-details.png"))
        details.close()
        store.remove_from_library(featured_id)
        rated_id = "OL5738147W"  # Elantris, a public catalog work.
        store.set_status(rated_id, "Read")
        store.update_entry(rated_id, status="Read", rating=4.25,
                           notes="", review="", started_on=None, finished_on="2026-09-30",
                           shelves="Favorites, Book club")
        goal_book_ids = [rated_id]
        for book in store.catalog_books(limit=2):
            store.assign_shelves(book["id"], "Want to Read", ["Book club"])
            goal_book_ids.append(book["id"])
        store.add_goal("Annual reading goal", "2026-01-01", "2026-12-31", 12)
        store.add_goal("Book club reading", "2026-01-01", "2026-12-31", 3, book_ids=goal_book_ids)
        for name in ("Want to Read", "Currently Reading", "Did Not Finish"):
            store.set_shelf_collapsed(name, "library", True)
        window.refresh()
        window.navigate(1)
        app.processEvents()
        window.grab().save(str(output / "my-library.png"))
        for section in window.stack.widget(1).findChildren(ShelfSection):
            section.header.setChecked(False)
        app.processEvents()
        window.grab().save(str(output / "my-library-shelves.png"))
        window.navigate(0)
        app.processEvents()
        window.stack.widget(0).verticalScrollBar().setValue(350)
        app.processEvents()
        window.grab().save(str(output / "home-shelves.png"))
        shelves = ShelfDialog("Elantris", "Read", window, store=store, selected="Favorites, Book club")
        shelves.show()
        app.processEvents()
        shelves.grab().save(str(output / "choose-shelves.png"))
        shelves.close()
        manager = ManageShelvesDialog(store, window)
        manager.show()
        app.processEvents()
        manager.grab().save(str(output / "manage-shelves.png"))
        manager.close()
        window.navigate(3)
        app.processEvents()
        window.grab().save(str(output / "stats-goals.png"))
        goal = GoalDialog(store, window, goal=store.goals()[0])
        goal.show()
        app.processEvents()
        goal.grab().save(str(output / "edit-reading-goal.png"))
        goal.close()
        custom_goal = next(goal for goal in store.goals() if goal["scope"] == "selected")
        goal = GoalDialog(store, window, goal=custom_goal)
        goal.show()
        app.processEvents()
        goal.grab().save(str(output / "custom-reading-goal.png"))
        picker = GoalBooksDialog(store, custom_goal["book_ids"], goal)
        picker.show()
        picker.shelf_filter.setCurrentText("Custom: Book club")
        app.processEvents()
        picker.grab().save(str(output / "choose-goal-books.png"))
        picker.close()
        goal.close()
        window.close()


if __name__ == "__main__":
    main()
