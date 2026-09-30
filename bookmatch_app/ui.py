"""The BookMatch desktop window."""

from __future__ import annotations

import sqlite3
from textwrap import fill

from .messages import MessageBox as QMessageBox
from functools import partial
from hashlib import sha256
from pathlib import Path
from random import SystemRandom

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from .storage import (CATALOG_PERIODS, CATALOG_SHELVES, CATALOG_SORTS, CATALOG_TOPICS,
                      LibraryStore, STATUSES)
from .covers import CoverCache, CoverLabel
from .dialogs import (AddBookDialog, BookDetailsDialog, GoalDialog, PageJumpDialog, ShelfDialog,
                      NewShelfDialog, ManageShelvesDialog)
from .transfer import (export_library, import_goodreads, parse_goodreads_csv,
                       import_bookmatch_json, parse_bookmatch_json)
from .recommend import MODEL_CREDIT, catalog_index_ready, install_model, model_ready, recommend
from .widgets import BookMatchComboBox, CatalogSearchLineEdit, PageNavigator, RatingSummary, ShelfSection

ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "bookmatch-icon.png"

INK = "#26332e"
MUTED = "#69756d"

STYLE = """
QMainWindow, QWidget#root, QWidget#page, QWidget#formContent, QScrollArea, QScrollArea QWidget#qt_scrollarea_viewport {
    background: #f7f5ef; color: #26332e;
}
QWidget { font-family: 'Avenir Next'; font-size: 14px; }
QLabel { color: #26332e; background: transparent; }
QPushButton { background: #edf2eb; color: #315c47; border: 1px solid #d5e1d3; border-radius: 9px; padding: 9px 12px; font-weight: 650; }
QPushButton:hover { background: #e2ecdf; }
QPushButton:focus { border: 2px solid #5a8569; }
QPushButton:disabled, QPushButton#secondary:disabled, QPushButton#primary:disabled,
QPushButton#pageArrow:disabled { background: #eeeee9; color: #a0a79f; border: 1px solid #dedfd8; }
QPushButton#pageArrow { padding: 9px 12px; }
QPushButton#pageNumber { padding: 9px 7px; min-width: 22px; }
QPushButton#pageNumber[current="true"] { background: #315c47; color: white; border-color: #315c47; }
QFrame#sidebar { background: #e9ede5; border-right: 1px solid #d9dfd5; }
QLabel#brand { color: #284b3f; font-size: 24px; font-weight: 750; }
QLabel#smallCaps { color: #73837a; font-size: 10px; font-weight: 750; letter-spacing: 1.4px; }
QLabel#pageTitle { color: #233a30; font-size: 30px; font-weight: 750; }
QLabel#sectionTitle { color: #263b31; font-size: 20px; font-weight: 700; }
QLabel#muted { color: #69756d; }
QPushButton#nav { background: transparent; text-align: left; padding: 12px 16px; border: 0; border-radius: 10px; color: #4b6054; font-size: 14px; }
QPushButton#nav:hover { background: #dfe7dc; }
QPushButton#nav[active="true"] { background: #d5e3d5; color: #234e3b; font-weight: 750; }
QPushButton#nav[collapsed="true"] { text-align: center; padding: 12px 0; font-size: 20px; }
QPushButton#sidebarToggle { padding: 0; font-size: 22px; background: transparent; border: 0; border-radius: 8px; }
QPushButton#sidebarToggle:hover { background: #dfe7dc; }
QPushButton#sidebarToggle:focus { border: 2px solid #5a8569; }
QPushButton#shelfHeader { text-align: left; padding: 12px 16px; background: #edf2eb; border: 1px solid #d5e1d3; border-radius: 10px; font-size: 15px; }
QPushButton#shelfHeader:hover { background: #e2ecdf; }
QCheckBox { color: #26332e; spacing: 10px; }
QPushButton#primary { background: #315c47; color: white; border: 0; border-radius: 10px; padding: 11px 17px; font-weight: 700; }
QPushButton#primary:hover { background: #254b39; }
QPushButton#secondary { background: #edf2eb; color: #315c47; border: 1px solid #d5e1d3; border-radius: 9px; padding: 9px 12px; font-weight: 650; }
QPushButton#secondary:hover { background: #e2ecdf; }
QPushButton#danger { background: #f8eeea; color: #8a3f35; border: 1px solid #e6c9c1; border-radius: 9px; padding: 9px 12px; font-weight: 700; }
QPushButton#danger:hover { background: #f1ded8; }
QFrame#surface { background: #fffefa; border: 1px solid #e8e7dd; border-radius: 16px; }
QFrame#hero { background: #dce6d7; border: 1px solid #d4dfcf; border-radius: 20px; }
QFrame#note { background: #f2ebdc; border: 1px solid #e8dec9; border-radius: 13px; }
QLineEdit { background: #fffefa; color: #26332e; border: 1px solid #d9e0d6; border-radius: 9px; padding: 10px 12px; }
QPlainTextEdit, QSpinBox { background: #fffefa; color: #26332e; border: 1px solid #d9e0d6; border-radius: 9px; padding: 8px 10px; }
QSpinBox::up-button, QSpinBox::down-button { border: 0; background: transparent; width: 20px; }
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QSpinBox:focus { border: 2px solid #5a8569; }
QComboBox { background: #fffefa; color: #26332e; border: 1px solid #d9e0d6; border-radius: 9px; padding: 7px 10px; min-width: 145px; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox::down-arrow { image: none; }
QComboBox QAbstractItemView {
    background: #fffefa; color: #26332e; border: 0; border-radius: 9px;
    selection-background-color: #d5e3d5; selection-color: #234e3b;
    outline: 0;
}
QComboBox QAbstractItemView::item:hover,
QComboBox QAbstractItemView::item:selected {
    background: #d5e3d5; color: #234e3b;
}
QDialog { background: #f7f5ef; color: #26332e; }
QDialogButtonBox QPushButton { background: #edf2eb; color: #315c47; border: 1px solid #d5e1d3; border-radius: 9px; padding: 9px 18px; min-width: 70px; }
QDialogButtonBox QPushButton:hover { background: #e2ecdf; }
QSlider::groove:horizontal { height: 6px; border-radius: 3px; background: #dde5d9; }
QSlider::sub-page:horizontal { background: #5a8569; border-radius: 3px; }
QSlider::handle:horizontal { width: 16px; margin: -5px 0; background: #315c47; border: 1px solid #315c47; border-radius: 8px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px 1px; }
QScrollBar::handle:vertical { background: #c3cec0; border-radius: 4px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: #94ab96; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollArea { border: 0; background: transparent; }
"""


def label(text: str, name: str | None = None, *, wrap: bool = True) -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(wrap)
    result.setMinimumWidth(0)
    if name:
        result.setObjectName(name)
    return result


def vertical(parent: QWidget | None = None, spacing: int = 12) -> QVBoxLayout:
    layout = QVBoxLayout(parent)
    layout.setSpacing(spacing)
    layout.setContentsMargins(0, 0, 0, 0)
    return layout


def surface() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("surface")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(10)
    return frame, layout


def cover(book: dict, cache: CoverCache, width: int = 106, height: int = 150) -> QLabel:
    if "colors" not in book:
        palettes = (("#506b61", "#a4b9a6"), ("#715a71", "#c7a9b5"),
                    ("#435f73", "#9db1b8"), ("#a96757", "#e5be94"))
        book = {**book, "colors": palettes[sha256(book["id"].encode()).digest()[0] % len(palettes)]}
    pixmap = QPixmap(width, height)
    pixmap.fill(QColor(book["colors"][0]))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.fillRect(0, height - 42, width, 42, QColor(book["colors"][1]))
    painter.setPen(QColor("#fff8eb"))
    font = QFont("Georgia", 10)
    font.setBold(True)
    painter.setFont(font)
    title = book["title"].replace(" ", "\n", 2)
    painter.drawText(11, 18, width - 22, height - 55, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, title)
    font.setPointSize(7)
    font.setBold(False)
    painter.setFont(font)
    painter.drawText(10, height - 33, width - 20, 24, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, book["author"].upper())
    painter.end()
    result = CoverLabel(book["id"], pixmap, cache)
    result.setAccessibleName(f"Cover for {book['title']}")
    return result


class BookMatchWindow(QMainWindow):
    PAGES = ("Home", "My Library", "Discover", "Stats & Goals", "Catalog", "Settings")
    NAV_ICONS = ("⌂", "▤", "✦", "◔", "▦", "⚙")
    DISCOVERY_SORTS = ("Popularity", "Best match", "Title A–Z", "Newest first", "Oldest first")
    HOME_POOL_SIZE = 75

    def __init__(self, store: LibraryStore):
        super().__init__()
        self.store = store
        self.cover_cache = CoverCache(store.directory)
        self._discovery_query = ""
        self._discovery_results = []
        self._discovery_mode = ""
        self._discovery_prefs = None
        self._discovery_running = False
        self._discovery_topic = CATALOG_TOPICS[0]
        self._discovery_period = CATALOG_PERIODS[0]
        self._discovery_sort = self.DISCOVERY_SORTS[0]
        self._discovery_page = 0
        self._home_pick_order = []
        self._search_worker = None
        self._install_worker = None
        self._catalog_query = ""
        self._catalog_draft = ""
        self._catalog_search_timer = QTimer(self)
        self._catalog_search_timer.setSingleShot(True)
        self._catalog_search_timer.setInterval(250)
        self._catalog_search_timer.timeout.connect(self._apply_catalog_draft)
        self._catalog_page = 0
        self._catalog_topic = CATALOG_TOPICS[0]
        self._catalog_period = CATALOG_PERIODS[0]
        self._catalog_shelf = CATALOG_SHELVES[0]
        self._catalog_sort = CATALOG_SORTS[0]
        self._library_query = ""
        self._library_draft = ""
        self._discovery_draft = ""
        self._library_filter = "All shelves"
        self._library_sort = "Recently updated"
        self._shelf_pages = {}
        self._responsive_compact = False
        self._sidebar_collapsed = False
        self._store_closed = False
        self._refresh_revision = 0
        self.setWindowTitle("BookMatch — Your reading life, in one place")
        if ICON_PATH.is_file():
            self.setWindowIcon(QIcon(str(ICON_PATH)))
        self.resize(1120, 760)
        self.setMinimumSize(850, 600)
        self.setStyleSheet(STYLE)
        self._make_window()
        self._make_shortcuts()
        self.refresh()
        self.navigate(0)

    def _make_window(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        self.sidebar = sidebar
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        self._sidebar_layout = side
        side.setContentsMargins(21, 31, 21, 24)
        side.setSpacing(8)
        brand_row = QHBoxLayout()
        self._brand_row = brand_row
        brand_row.setSpacing(9)
        brand_row.addStretch(0)
        if ICON_PATH.is_file():
            icon = QLabel()
            icon.setPixmap(QPixmap(str(ICON_PATH)).scaled(
                36, 36, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation))
            icon.setFixedSize(36, 36)
            icon.setAccessibleName("BookMatch app logo")
            brand_row.addWidget(icon)
        self._brand_label = label("BookMatch", "brand")
        brand_row.addWidget(self._brand_label)
        brand_row.addStretch(1)
        side.addLayout(brand_row)
        side.addSpacing(34)
        heading_row = QHBoxLayout()
        self._sidebar_heading = label("YOUR SPACE", "smallCaps")
        heading_row.addWidget(self._sidebar_heading, 1)
        self.sidebar_toggle = QPushButton("‹")
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setFixedSize(32, 32)
        self.sidebar_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_toggle.setToolTip("Collapse sidebar")
        self.sidebar_toggle.setAccessibleName("Collapse sidebar")
        self.sidebar_toggle.setCheckable(True)
        self.sidebar_toggle.toggled.connect(self._set_sidebar_collapsed)
        heading_row.addWidget(self.sidebar_toggle, 0, Qt.AlignmentFlag.AlignCenter)
        side.addLayout(heading_row)
        side.addSpacing(5)
        self.nav_buttons = []
        for index, (icon, title) in enumerate(zip(self.NAV_ICONS, self.PAGES)):
            button = QPushButton(f"{icon}    {title.replace('&', '&&')}")
            button.setObjectName("nav")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setAccessibleName(title)
            button.setToolTip(title)
            button.clicked.connect(partial(self.navigate, index))
            side.addWidget(button)
            self.nav_buttons.append(button)
        side.addStretch()
        privacy = QFrame()
        self._sidebar_privacy = privacy
        privacy.setObjectName("note")
        privacy_layout = QVBoxLayout(privacy)
        privacy_layout.setContentsMargins(13, 13, 13, 13)
        privacy_layout.addWidget(label("PRIVATE BY DESIGN", "smallCaps"))
        privacy_layout.addWidget(label("Your shelf stays on this computer.", "muted", wrap=True))
        side.addWidget(privacy)
        outer.addWidget(sidebar)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        for _ in self.PAGES:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.stack.addWidget(scroll)

    def _make_shortcuts(self) -> None:
        for index in range(len(self.PAGES)):
            action = QAction(self)
            action.setShortcut(QKeySequence(f"Ctrl+{index + 1}"))
            action.triggered.connect(partial(self.navigate, index))
            self.addAction(action)

    def navigate(self, index: int) -> None:
        if index == 4 and self._catalog_draft.strip() != self._catalog_query:
            self._apply_catalog_draft(restore_focus=False)
        self.stack.setCurrentIndex(index)
        for position, button in enumerate(self.nav_buttons):
            button.setProperty("active", position == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_responsive_layout()

    def _set_sidebar_collapsed(self, collapsed: bool) -> None:
        self._sidebar_collapsed = collapsed
        self.sidebar.setFixedWidth(76 if collapsed else 232)
        self._brand_row.setStretch(0, 1 if collapsed else 0)
        self._sidebar_layout.setContentsMargins(12 if collapsed else 21, 31,
                                               12 if collapsed else 21, 24)
        for widget in (self._brand_label, self._sidebar_heading, self._sidebar_privacy):
            widget.setVisible(not collapsed)
        self.sidebar_toggle.setText("›" if collapsed else "‹")
        action = "Expand sidebar" if collapsed else "Collapse sidebar"
        self.sidebar_toggle.setToolTip(action)
        self.sidebar_toggle.setAccessibleName(action)
        for button, icon, title in zip(self.nav_buttons, self.NAV_ICONS, self.PAGES):
            button.setText(icon if collapsed else f"{icon}    {title.replace('&', '&&')}")
            button.setProperty("collapsed", collapsed)
            button.style().unpolish(button)
            button.style().polish(button)
        self._update_responsive_layout()

    def _update_responsive_layout(self) -> None:
        if not hasattr(self, "stack"):
            return
        compact = self.width() - self.sidebar.width() < 928
        if compact != self._responsive_compact:
            self._responsive_compact = compact
            self.refresh()

    def refresh(self, *, reset_page: int | None = None) -> None:
        for view, index in (("home", 0), ("library", 1)):
            for section in self.stack.widget(index).findChildren(ShelfSection):
                self._shelf_pages[(view, section.name)] = section.page
        if reset_page == 1:
            self._shelf_pages = {key: value for key, value in self._shelf_pages.items() if key[0] != "library"}
        positions = [self.stack.widget(index).verticalScrollBar().value()
                     for index in range(self.stack.count())]
        if reset_page is not None:
            positions[reset_page] = 0
        self._refresh_revision += 1
        revision = self._refresh_revision
        entries = self.store.entries()
        builders = (self._home, self._library, self._discover, self._stats, self._catalog, self._settings)
        for index, builder in enumerate(builders):
            page = builder(entries)
            self.stack.widget(index).setWidget(page)

        def restore_positions() -> None:
            if not isValid(self) or revision != self._refresh_revision:
                return
            for index, position in enumerate(positions):
                self.stack.widget(index).verticalScrollBar().setValue(position)

        restore_positions()
        QTimer.singleShot(0, restore_positions)

    def _page(self, eyebrow: str, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        page.setObjectName("page")
        page.setMinimumWidth(0)
        page.setAutoFillBackground(True)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(42, 36, 42, 42)
        layout.setSpacing(17)
        layout.addWidget(label(eyebrow.upper(), "smallCaps"))
        layout.addWidget(label(title, "pageTitle"))
        layout.addWidget(label(subtitle, "muted", wrap=True))
        layout.addSpacing(8)
        return page, layout

    def _home(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("Your reading home", "Make room for your next read.", "A private space for the books you love and the ones you have yet to meet.")
        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(26, 24, 26, 25)
        hero_layout.setSpacing(10)
        hero_layout.addWidget(label("WELCOME TO BOOKMATCH" if not entries else "YOUR READING SPACE", "smallCaps"))
        heading = label("Your story starts on your shelf." if not entries else "Keep your reading story moving.", "sectionTitle")
        hero_layout.addWidget(heading)
        hero_layout.addWidget(label("Browse books readers have logged on Open Library, save one to a shelf, and come back to find it waiting for you." if not entries else "Pick up a current read, add a book, or find the next one that fits your mood.", "muted", wrap=True))
        browse = QPushButton("Browse popular books  →" if not entries else "Discover a book  →")
        browse.setObjectName("primary")
        browse.setCursor(Qt.CursorShape.PointingHandCursor)
        browse.clicked.connect(partial(self.navigate, 4 if not entries else 2))
        hero_layout.addWidget(browse, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(hero)
        layout.addSpacing(8)
        layout.addWidget(label("YOUR READING AT A GLANCE", "smallCaps"))
        stats = QGridLayout()
        stats.setObjectName("readingAtGlance")
        stats.setSpacing(14)
        for column in range(2 if self._responsive_compact else 3):
            stats.setColumnStretch(column, 1)
        for index, (number, caption) in enumerate(((len(entries), "On your shelves"), (sum(value == "Currently Reading" for value in entries.values()), "Reading now"), (sum(value == "Read" for value in entries.values()), "Finished"))):
            card, inside = surface()
            card.setProperty("statCaption", caption)
            count = label(str(number), "pageTitle")
            inside.addWidget(count)
            inside.addWidget(label(caption, "muted"))
            if self._responsive_compact:
                if index == 0:
                    stats.addWidget(card, 0, 0, 1, 2)
                else:
                    stats.addWidget(card, 1, index - 1)
            else:
                stats.addWidget(card, 0, index)
        layout.addLayout(stats)
        layout.addWidget(label("YOUR SHELVES", "smallCaps"))
        layout.addWidget(self._shelf_sections(self.store.library_books(), "home"))
        if entries:
            recent = self.store.library_books()[:2]
            if recent:
                layout.addSpacing(8)
                layout.addWidget(label("RECENTLY ON YOUR SHELF", "smallCaps"))
                for book in recent:
                    layout.addWidget(self._book_card(book, book["status"]))
            goals = self.store.goals()
            if goals:
                goal = goals[0]
                goal_card, goal_layout = surface()
                goal_layout.addWidget(label("YOUR READING GOAL", "smallCaps"))
                goal_layout.addWidget(label(f"{goal['label']} · {goal['completed']} of {goal['target_books']} finished", "muted"))
                goal_layout.addWidget(label(self._goal_scope_text(goal), "muted"))
                goal_layout.addWidget(self._goal_edit_button(goal), alignment=Qt.AlignmentFlag.AlignLeft)
                layout.addWidget(goal_card)
        layout.addSpacing(10)
        layout.addWidget(label("POPULAR WITH OPEN LIBRARY READERS", "smallCaps"))
        layout.addWidget(label(f"Ten picks from the {self.HOME_POOL_SIZE} most popular books outside your library. A fresh mix each time you open BookMatch.", "muted"))
        suggestions = QGridLayout()
        suggestions.setSpacing(14)
        columns = 1 if self._responsive_compact else 2
        for index, book in enumerate(self._home_picks()):
            suggestions.addWidget(self._book_card(book, None), index // columns, index % columns)
        layout.addLayout(suggestions)
        layout.addStretch()
        return page

    def _home_picks(self) -> list[dict]:
        candidates = self.store.catalog_books(limit=self.HOME_POOL_SIZE, shelf="Not on my shelves")
        by_id = {book["id"]: book for book in candidates}
        self._home_pick_order = [book_id for book_id in self._home_pick_order if book_id in by_id]
        known = set(self._home_pick_order)
        additions = [book["id"] for book in candidates if book["id"] not in known]
        SystemRandom().shuffle(additions)
        self._home_pick_order.extend(additions)
        return [by_id[book_id] for book_id in self._home_pick_order[:10]]

    def _shelf_sections(self, books: list[dict], page: str) -> QWidget:
        host = QWidget()
        host.setObjectName("shelfSections")
        layout = vertical(host, 12)
        for shelf in self.store.shelf_definitions():
            name = shelf["name"]
            if page == "library" and self._library_filter != "All shelves":
                selected = self._library_filter.removeprefix("Custom: ")
                if selected.casefold() != name.casefold():
                    continue
            members = [book for book in books if
                       (book["status"] == name if shelf["builtin"] else name.casefold() in
                        {part.strip().casefold() for part in book["shelves"].split(",")})]
            section = ShelfSection(name, members,
                                   lambda book: self._book_card(book, book["status"], show_rating=True),
                                   collapsed=bool(shelf[f"{page}_collapsed"]),
                                   compact=self._responsive_compact,
                                   current=self._shelf_pages.get((page, name), 0))
            section.collapsed_changed.connect(
                lambda name, collapsed, view=page: self.store.set_shelf_collapsed(name, view, collapsed))
            layout.addWidget(section)
        return host

    def _add_shelf(self) -> None:
        if NewShelfDialog(self.store, self).exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _manage_shelves(self) -> None:
        ManageShelvesDialog(self.store, self).exec()
        if self._library_filter.startswith("Custom: ") and self._library_filter.removeprefix("Custom: ") not in self.store.custom_shelves():
            self._library_filter = "All shelves"
        self.refresh()

    def _book_card(self, book: dict, status: str | None, match=None,
                   *, show_rating: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("surface")
        card.setProperty("bookId", book["id"])
        row = QHBoxLayout(card)
        row.setContentsMargins(15, 15, 15, 15)
        row.setSpacing(16)
        row.addWidget(cover(book, self.cover_cache))
        details = QVBoxLayout()
        details.setSpacing(6)
        source_name = {"sample": "LEGACY SAMPLE", "openlibrary": "OPEN LIBRARY",
                       "goodreads": "GOODREADS IMPORT", "manual": "PERSONAL BOOK"}.get(book.get("source"), "SAMPLE")
        details.addWidget(label(f"{source_name} · {(book.get('genre') or 'BOOK').upper()}", "smallCaps", wrap=True))
        if book.get("read_count"):
            details.addWidget(label(f"Logged as read {book['read_count']:,} times on Open Library", "muted", wrap=True))
        title = label(book["title"], "sectionTitle", wrap=True)
        title.setStyleSheet("font-size: 17px;")
        details.addWidget(title)
        details.addWidget(label(book["author"], "muted", wrap=True))
        if show_rating and book.get("rating") is not None:
            details.addWidget(RatingSummary(book["rating"]))
        topics = ", ".join((book.get("subjects") or "").split(", ")[:2])
        details.addWidget(label(book.get("genre") or topics or "Book", "muted", wrap=True))
        if book.get("shelves"):
            details.addWidget(label(f"Custom shelves: {book['shelves']}", "muted", wrap=True))
        if match:
            details.addWidget(label(match.explanation, "muted", wrap=True))
            if match.conflict:
                warning = label(match.conflict, "muted", wrap=True)
                warning.setStyleSheet("color: #96553f;")
                details.addWidget(warning)
            details.addWidget(label(match.metadata_note, "muted", wrap=True))
        details.addStretch()
        actions = QVBoxLayout() if self._responsive_compact and match else QHBoxLayout()
        button = QPushButton(status or "Want to Read  +")
        button.setObjectName("secondary")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setAccessibleName(f"{'Change status for' if status else 'Save'} {book['title']}")
        button.clicked.connect(partial(self._change_status, book))
        actions.addWidget(button)
        details_button = QPushButton("Details")
        details_button.setObjectName("secondary")
        details_button.setAccessibleName(f"Details for {book['title']}")
        details_button.clicked.connect(partial(self._show_book, book["id"]))
        actions.addWidget(details_button)
        if match:
            dismiss_button = QPushButton("Not for me")
            dismiss_button.setObjectName("secondary")
            dismiss_button.setAccessibleName(f"Dismiss {book['title']}")
            dismiss_button.clicked.connect(partial(self._dismiss, book["id"]))
            actions.addWidget(dismiss_button)
        details.addLayout(actions)
        row.addLayout(details, 1)
        return card

    def _catalog(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("Catalog", "Find something worth opening.", "Browse 20,000 books ranked by Open Library reading logs. The catalog is available offline.")
        search = CatalogSearchLineEdit()
        search.setObjectName("catalogSearch")
        search.setText(self._catalog_draft)
        search.textChanged.connect(self._catalog_text_changed)
        search_row = QHBoxLayout()
        search_row.addWidget(search, 1)
        search_button = QPushButton("Search")
        search_button.setObjectName("secondary")
        search_button.clicked.connect(lambda: self._catalog_search(search.text()))
        search.returnPressed.connect(lambda: self._catalog_search(search.text()))
        search_row.addWidget(search_button)
        layout.addLayout(search_row)
        filters = QGridLayout()
        filters.setSpacing(10)
        selections = (("Genre", CATALOG_TOPICS, self._catalog_topic, "_catalog_topic"),
                      ("Published", CATALOG_PERIODS, self._catalog_period, "_catalog_period"),
                      ("Shelf", CATALOG_SHELVES, self._catalog_shelf, "_catalog_shelf"),
                      ("Sort", CATALOG_SORTS, self._catalog_sort, "_catalog_sort"))
        columns = 2 if self._responsive_compact else 4
        for index, (heading, choices, selected, attribute) in enumerate(selections):
            field = QVBoxLayout()
            field.setSpacing(5)
            field.addWidget(label(heading, "smallCaps"))
            combo = BookMatchComboBox()
            combo.setAccessibleName(f"Catalog {heading.lower()}")
            combo.addItems(choices)
            combo.setCurrentText(selected)
            combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            combo.currentTextChanged.connect(partial(self._set_catalog_filter, attribute))
            field.addWidget(combo)
            filters.addLayout(field, index // columns, index % columns)
        layout.addLayout(filters)
        filter_args = {"topic": self._catalog_topic, "period": self._catalog_period,
                       "shelf": self._catalog_shelf}
        total = self.store.catalog_count(self._catalog_query, **filter_args)
        page_size = 24
        page_count = max(1, (total + page_size - 1) // page_size)
        self._catalog_page = min(self._catalog_page, page_count - 1)
        visible = self.store.catalog_books(self._catalog_query, page_size,
                                           self._catalog_page * page_size,
                                           sort=self._catalog_sort, **filter_args)
        result_row = QHBoxLayout()
        result_row.addWidget(label(f"{total:,} books • Page {self._catalog_page + 1} of {page_count}", "muted", wrap=False))
        result_row.addStretch()
        if (self._catalog_query or self._catalog_topic != CATALOG_TOPICS[0] or
                self._catalog_period != CATALOG_PERIODS[0] or
                self._catalog_shelf != CATALOG_SHELVES[0] or
                self._catalog_sort != CATALOG_SORTS[0]):
            clear = QPushButton("Clear filters")
            clear.setObjectName("secondary")
            clear.clicked.connect(self._clear_catalog_filters)
            result_row.addWidget(clear)
        layout.addLayout(result_row)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(14)
        for index, book in enumerate(visible):
            card = self._book_card(book, entries.get(book["id"]))
            columns = 1 if self._responsive_compact else 2
            grid.addWidget(card, index // columns, index % columns)
        layout.addWidget(grid_host)
        if not total:
            layout.addWidget(label("No books match these filters. Try another genre, year, shelf, or search.", "muted"))
        if total:
            controls = PageNavigator(self._catalog_page, page_count,
                                     compact=self._responsive_compact)
            controls.page_changed.connect(self._catalog_go_to)
            controls.jump_requested.connect(partial(self._jump_catalog_page, page_count))
            layout.addWidget(controls)
        layout.addStretch()
        return page

    def _catalog_search(self, query: str) -> None:
        self._catalog_draft = query
        self._catalog_search_timer.stop()
        self._apply_catalog_draft(restore_focus=True)

    def _catalog_text_changed(self, query: str) -> None:
        self._catalog_draft = query
        self._catalog_search_timer.start()

    def _apply_catalog_draft(self, *, restore_focus: bool = True) -> None:
        self._catalog_search_timer.stop()
        query = self._catalog_draft.strip()
        if query == self._catalog_query:
            return
        active = self.stack.currentIndex()
        current_search = self.stack.widget(4).findChild(CatalogSearchLineEdit, "catalogSearch")
        focused = bool(restore_focus and active == 4 and current_search and
                       current_search.hasFocus())
        cursor_position = current_search.cursorPosition() if focused else 0
        self._catalog_query = query
        self._catalog_page = 0
        self.refresh(reset_page=4)
        if focused:
            replacement = self.stack.widget(4).findChild(CatalogSearchLineEdit,
                                                        "catalogSearch")
            if replacement:
                replacement.setFocus()
                replacement.setCursorPosition(min(cursor_position, len(replacement.text())))

    def _set_catalog_filter(self, attribute: str, value: str) -> None:
        setattr(self, attribute, value)
        self._catalog_page = 0
        self.refresh(reset_page=4)
        self.navigate(4)

    def _clear_catalog_filters(self) -> None:
        self._catalog_search_timer.stop()
        self._catalog_query = self._catalog_draft = ""
        self._catalog_topic = CATALOG_TOPICS[0]
        self._catalog_period = CATALOG_PERIODS[0]
        self._catalog_shelf = CATALOG_SHELVES[0]
        self._catalog_sort = CATALOG_SORTS[0]
        self._catalog_page = 0
        self.refresh(reset_page=4)
        self.navigate(4)

    def _catalog_turn(self, direction: int) -> None:
        self._catalog_go_to(self._catalog_page + direction)

    def _catalog_go_to(self, page: int) -> None:
        total = self.store.catalog_count(self._catalog_query, topic=self._catalog_topic,
                                         period=self._catalog_period, shelf=self._catalog_shelf)
        page_count = max(1, (total + 23) // 24)
        destination = max(0, min(page, page_count - 1))
        if destination == self._catalog_page:
            return
        self._catalog_page = destination
        self.refresh(reset_page=4)
        self.navigate(4)

    def _jump_catalog_page(self, count: int) -> None:
        dialog = PageJumpDialog(self._catalog_page, count, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._catalog_go_to(dialog.page_number.value() - 1)

    def _library(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("My Library", "Every book has a place here.", "Your books, ratings, and notes are stored privately on this computer.")
        add_button = QPushButton("+  Add a book")
        add_button.setObjectName("primary")
        add_button.clicked.connect(self._add_book)
        actions = QHBoxLayout()
        actions.addWidget(add_button)
        add_shelf = QPushButton("+ Add a shelf")
        add_shelf.setObjectName("secondary")
        add_shelf.clicked.connect(self._add_shelf)
        actions.addWidget(add_shelf)
        manage = QPushButton("Manage shelves")
        manage.setObjectName("secondary")
        manage.clicked.connect(self._manage_shelves)
        actions.addWidget(manage)
        actions.addStretch()
        layout.addLayout(actions)
        selected_status = self._library_filter if self._library_filter in STATUSES else None
        books = self.store.library_books(self._library_query, selected_status)
        if self._library_filter.startswith("Custom: "):
            shelf_name = self._library_filter.removeprefix("Custom: ").casefold()
            books = [book for book in books if shelf_name in
                     {part.strip().casefold() for part in book["shelves"].split(",")}]
        if self._library_sort == "Title A–Z":
            books.sort(key=lambda book: book["title"].casefold())
        elif self._library_sort == "Author A–Z":
            books.sort(key=lambda book: (book["author"].casefold(), book["title"].casefold()))
        elif self._library_sort == "Rating high":
            books.sort(key=lambda book: (-(book["rating"] or 0), book["title"].casefold()))
        if entries:
            search = QLineEdit()
            search.setPlaceholderText("Find a book by title, author, or genre")
            search.setAccessibleName("Search my library")
            search.setText(self._library_draft)
            search.textChanged.connect(lambda value: setattr(self, "_library_draft", value))
            search_row = QHBoxLayout()
            search_row.addWidget(search, 1)
            search_button = QPushButton("Search")
            search_button.setObjectName("secondary")
            search_button.clicked.connect(lambda: self._library_search(search.text()))
            search.returnPressed.connect(lambda: self._library_search(search.text()))
            search_row.addWidget(search_button)
            layout.addLayout(search_row)
            filter_row = QGridLayout()
            filter_row.setSpacing(10)
            filter_row.addWidget(label("Shelf", "smallCaps"), 0, 0)
            shelf_filter = BookMatchComboBox()
            shelf_filter.addItems(("All shelves",) + STATUSES +
                                  tuple(f"Custom: {name}" for name in self.store.custom_shelves()))
            shelf_filter.setCurrentText(self._library_filter)
            shelf_filter.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            shelf_filter.currentTextChanged.connect(self._set_library_filter)
            filter_row.addWidget(shelf_filter, 1, 0)
            filter_row.addWidget(label("Sort", "smallCaps"), 0, 1)
            sort = BookMatchComboBox()
            sort.addItems(("Recently updated", "Title A–Z", "Author A–Z", "Rating high"))
            sort.setCurrentText(self._library_sort)
            sort.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            sort.currentTextChanged.connect(self._set_library_sort)
            filter_row.addWidget(sort, 1, 1)
            layout.addLayout(filter_row)
        if not books:
            empty, inside = surface()
            inside.setContentsMargins(28, 35, 28, 35)
            inside.addWidget(label("No books match these filters" if entries else "Your shelf is waiting", "sectionTitle"))
            inside.addWidget(label("Clear the search or choose another shelf." if entries else "Start by choosing a book from the catalog.", "muted"))
            button = QPushButton("Clear filters" if entries else "Browse catalog  →")
            button.setObjectName("primary")
            button.clicked.connect(self._clear_library_search if entries else partial(self.navigate, 4))
            inside.addWidget(button, alignment=Qt.AlignmentFlag.AlignLeft)
            layout.addWidget(empty)
        layout.addWidget(label(f"{len(books):,} {'book' if len(books) == 1 else 'books'}", "muted"))
        layout.addWidget(self._shelf_sections(books, "library"))
        layout.addStretch()
        return page

    def _library_search(self, query: str) -> None:
        self._library_query = query.strip()
        self._library_draft = query
        self.refresh(reset_page=1)
        self.navigate(1)

    def _clear_library_search(self) -> None:
        self._library_query = ""
        self._library_draft = ""
        self._library_filter = "All shelves"
        self.refresh(reset_page=1)
        self.navigate(1)

    def _set_library_filter(self, value: str) -> None:
        self._library_filter = value
        self.refresh(reset_page=1)
        self.navigate(1)

    def _set_library_sort(self, value: str) -> None:
        self._library_sort = value
        self.refresh(reset_page=1)
        self.navigate(1)

    def _discover(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("Discover", "Describe the book you're hoping for.", "Tell BookMatch what you liked and what you want to avoid. Searches stay on this computer.")
        prompt = QPlainTextEdit()
        prompt.setPlaceholderText("I loved the eerie small-town atmosphere and friendships, but I don't want graphic violence…")
        prompt.setAccessibleName("Describe your ideal next book")
        prompt.setPlainText(self._discovery_draft)
        prompt.textChanged.connect(lambda: setattr(self, "_discovery_draft", prompt.toPlainText()))
        prompt.setFixedHeight(105)
        layout.addWidget(prompt)
        search = QPushButton("Find matching books  →")
        search.setObjectName("primary")
        search.setEnabled(not self._discovery_running)
        search.clicked.connect(lambda: self._search_discover(prompt.toPlainText()))
        layout.addWidget(search, alignment=Qt.AlignmentFlag.AlignLeft)
        if model_ready(self.store.directory):
            index_ready = catalog_index_ready(self.store.directory, self.store.catalog_revision(),
                                              self.store.catalog_count())
            model_line = ("Local language model ready · searches are offline" if index_ready else
                          "Local model installed · first search prepares the offline catalog index and may take several minutes")
        else:
            model_line = "Metadata search mode · install the free local model in Settings for broader matching"
        layout.addWidget(label(model_line, "muted"))
        if self._discovery_running:
            layout.addWidget(label("Looking through your available book metadata. A first search may need several minutes to prepare the offline index…", "sectionTitle", wrap=True))
        elif self._discovery_query:
            layout.addSpacing(9)
            layout.addWidget(label(f"RESULTS · {self._discovery_mode.upper()}", "smallCaps"))
            if self._discovery_prefs:
                if self._discovery_prefs.wanted:
                    layout.addWidget(label(f"Looking for: {self._discovery_prefs.wanted}", "muted", wrap=True))
                if self._discovery_prefs.avoided:
                    layout.addWidget(label(f"Avoiding: {self._discovery_prefs.avoided}", "muted", wrap=True))
            filters = QGridLayout()
            filters.setSpacing(10)
            columns = 2 if self._responsive_compact else 3
            selections = (("Genre", CATALOG_TOPICS, self._discovery_topic, "_discovery_topic"),
                          ("Published", CATALOG_PERIODS, self._discovery_period, "_discovery_period"),
                          ("Sort", self.DISCOVERY_SORTS, self._discovery_sort, "_discovery_sort"))
            for index, (heading, choices, selected, attribute) in enumerate(selections):
                field = QVBoxLayout()
                field.setSpacing(5)
                field.addWidget(label(heading, "smallCaps"))
                combo = BookMatchComboBox()
                combo.setAccessibleName(f"Discover {heading.lower()}")
                combo.addItems(choices)
                combo.setCurrentText(selected)
                combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
                combo.currentTextChanged.connect(partial(self._set_discovery_filter, attribute))
                field.addWidget(combo)
                filters.addLayout(field, index // columns, index % columns)
            layout.addLayout(filters)
            matches = self._filtered_discovery_results()
            page_count = max(1, (len(matches) + 11) // 12)
            self._discovery_page = min(self._discovery_page, page_count - 1)
            summary_row = QHBoxLayout()
            summary_row.addWidget(label(f"{len(matches):,} matches • Page {self._discovery_page + 1} of {page_count}",
                                        "muted", wrap=False))
            summary_row.addStretch()
            if self._discovery_topic != CATALOG_TOPICS[0] or self._discovery_period != CATALOG_PERIODS[0]:
                clear = QPushButton("Clear filters")
                clear.setObjectName("secondary")
                clear.clicked.connect(self._clear_discovery_filters)
                summary_row.addWidget(clear)
            layout.addLayout(summary_row)
            if not self._discovery_results:
                layout.addWidget(label("No confident matches in the available metadata. Try a broader description or add books with descriptions.", "muted", wrap=True))
            elif not matches:
                layout.addWidget(label("No matching books fit these filters. Clear the filters or choose another genre or publication year.", "muted"))
            for match in matches[self._discovery_page * 12:(self._discovery_page + 1) * 12]:
                layout.addWidget(self._book_card(match.book, entries.get(match.book["id"]), match))
            if matches:
                controls = PageNavigator(self._discovery_page, page_count,
                                         compact=self._responsive_compact)
                controls.page_changed.connect(self._discovery_go_to)
                controls.jump_requested.connect(partial(self._jump_discovery_page, page_count))
                layout.addWidget(controls)
        else:
            hint, inside = surface()
            inside.addWidget(label("A little more than keywords", "sectionTitle"))
            inside.addWidget(label("BookMatch separates what you want from what you want to avoid, compares available book metadata with a local model when installed, and shows where evidence is missing.", "muted", wrap=True))
            layout.addWidget(hint)
        layout.addStretch()
        return page

    def _filtered_discovery_results(self):
        sort = "Most read" if self._discovery_sort in ("Popularity", "Best match") else self._discovery_sort
        eligible = self.store.catalog_books(topic=self._discovery_topic,
                                             period=self._discovery_period, sort=sort)
        order = {book["id"]: index for index, book in enumerate(eligible)}
        matches = [match for match in self._discovery_results if match.book["id"] in order]
        if self._discovery_sort == "Best match":
            matches.sort(key=lambda match: (-match.score, order[match.book["id"]]))
        else:
            matches.sort(key=lambda match: order[match.book["id"]])
        return matches

    def _set_discovery_filter(self, attribute: str, value: str) -> None:
        setattr(self, attribute, value)
        self._discovery_page = 0
        self.refresh(reset_page=2)
        self.navigate(2)

    def _clear_discovery_filters(self) -> None:
        self._discovery_topic = CATALOG_TOPICS[0]
        self._discovery_period = CATALOG_PERIODS[0]
        self._discovery_page = 0
        self.refresh(reset_page=2)
        self.navigate(2)

    def _discovery_go_to(self, page: int) -> None:
        count = max(1, (len(self._filtered_discovery_results()) + 11) // 12)
        destination = max(0, min(page, count - 1))
        if destination != self._discovery_page:
            self._discovery_page = destination
            self.refresh(reset_page=2)
            self.navigate(2)

    def _jump_discovery_page(self, count: int) -> None:
        dialog = PageJumpDialog(self._discovery_page, count, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._discovery_go_to(dialog.page_number.value() - 1)

    def _search_discover(self, query: str) -> None:
        if self._search_worker and self._search_worker.isRunning():
            return
        query = query.strip()
        if not query:
            QMessageBox.information(self, "Describe your next book", "Enter a few things you want in a book, or things you want to avoid.")
            return
        self._discovery_query = query
        self._discovery_draft = query
        self._discovery_running = True
        self._discovery_sort = self.DISCOVERY_SORTS[0]
        self._discovery_page = 0
        self.refresh(reset_page=2)
        self.navigate(2)
        self._search_worker = SearchWorker(query, self.store.discovery_books(), self.store.directory,
                                           self.store.catalog_books(), self.store.catalog_revision())
        self._search_worker.finished_search.connect(self._show_discovery_results)
        self._search_worker.failed.connect(self._discovery_failed)
        self._search_worker.start()

    def _show_discovery_results(self, matches, mode, prefs) -> None:
        self._discovery_results = matches
        self._discovery_mode = mode
        self._discovery_prefs = prefs
        self._discovery_running = False
        self._discovery_page = 0
        self.refresh(reset_page=2)
        self.navigate(2)

    def _discovery_failed(self, error: str) -> None:
        self._discovery_running = False
        self._discovery_results = []
        self._discovery_mode = "Unavailable"
        self.refresh()
        self.navigate(2)
        QMessageBox.warning(self, "Search could not finish", error)

    def _dismiss(self, book_id: str) -> None:
        self.store.dismiss_book(book_id)
        self._discovery_results = [match for match in self._discovery_results if match.book["id"] != book_id]
        self.refresh()
        self.navigate(2)

    def _settings(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("Settings", "Your space, your data.", "BookMatch keeps your library on this computer. No sign-in is needed.")
        card, inside = surface()
        inside.addWidget(label("LOCAL DATA FOLDER", "smallCaps"))
        location = label(str(self.store.directory), "muted", wrap=True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        inside.addWidget(location)
        inside.addWidget(label("This folder contains your BookMatch library database. Back up this file to keep a copy of your shelf.", "muted", wrap=True))
        layout.addWidget(card)
        transfer_card, transfer_layout = surface()
        transfer_layout.addWidget(label("YOUR LIBRARY, PORTABLE", "smallCaps"))
        transfer_layout.addWidget(label("Import a Goodreads CSV after reviewing its contents, or export your BookMatch library as JSON.", "muted", wrap=True))
        transfer_buttons = QVBoxLayout()
        import_button = QPushButton("Import Goodreads CSV…")
        import_button.setObjectName("secondary")
        import_button.clicked.connect(self._import_goodreads)
        transfer_buttons.addWidget(import_button, alignment=Qt.AlignmentFlag.AlignLeft)
        restore_button = QPushButton("Import BookMatch JSON…")
        restore_button.setObjectName("secondary")
        restore_button.clicked.connect(self._import_json)
        transfer_buttons.addWidget(restore_button, alignment=Qt.AlignmentFlag.AlignLeft)
        export_button = QPushButton("Export library JSON…")
        export_button.setObjectName("secondary")
        export_button.clicked.connect(self._export_library)
        transfer_buttons.addWidget(export_button, alignment=Qt.AlignmentFlag.AlignLeft)
        transfer_layout.addLayout(transfer_buttons)
        layout.addWidget(transfer_card)
        model_card, model_layout = surface()
        model_layout.addWidget(label("OFFLINE RECOMMENDATIONS", "smallCaps"))
        model_layout.addWidget(label(MODEL_CREDIT, "muted"))
        if self._install_worker and self._install_worker.isRunning():
            model_layout.addWidget(label("Preparing the free local model and its offline catalog index. This may take several minutes.", "muted", wrap=True))
        elif model_ready(self.store.directory):
            model_layout.addWidget(label("Installed locally. Your descriptions are never sent to a model service.", "muted", wrap=True))
        else:
            model_layout.addWidget(label("The app can download the free model once. Until then, Discover uses a clearly labeled metadata fallback.", "muted", wrap=True))
            model_button = QPushButton("Install local model")
            model_button.setObjectName("secondary")
            model_button.clicked.connect(self._install_model)
            model_layout.addWidget(model_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(model_card)
        note = QFrame()
        note.setObjectName("note")
        note_layout = QVBoxLayout(note)
        note_layout.setContentsMargins(17, 17, 17, 17)
        note_layout.addWidget(label("ABOUT RECOMMENDATIONS", "smallCaps"))
        note_layout.addWidget(label("Book subjects are community-contributed metadata. Recommendation quality depends on available subjects and descriptions; missing content details are never treated as verified content warnings.", "muted", wrap=True))
        layout.addWidget(note)
        erase_card, erase_layout = surface()
        erase_layout.addWidget(label("CLEAR SAVED BOOKS", "smallCaps"))
        erase_layout.addWidget(label(
            "Remove all books from your shelves and clear their read dates, ratings, "
            "reviews, and private notes. Your shelves, reading goals, downloaded covers, "
            "and recommendation model will stay. Goal progress will reset to zero.",
            "muted", wrap=True))
        erase_button = QPushButton("Clear saved books…")
        erase_button.setObjectName("danger")
        erase_button.setAccessibleName("Clear saved books and reading history")
        erase_button.clicked.connect(self._clear_saved_books)
        erase_layout.addWidget(erase_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(erase_card)
        layout.addStretch()
        return page

    def _clear_saved_books(self) -> None:
        if any(worker and worker.isRunning() for worker in
               (self._search_worker, self._install_worker)):
            QMessageBox.information(self, "Please wait",
                                    "A local search or model installation is still running. "
                                    "Try again when it finishes.")
            return
        message = (
            "This permanently removes all saved books from every shelf, including "
            "imported books, and clears their started and finished dates, ratings, "
            "reviews, and private notes.\n\n"
            "Your shelf names, reading goals and book selections, downloaded covers, "
            "cached book details, and recommendation model will stay. Goal progress "
            "will reset to zero. Existing backup and export files are unaffected.\n\n"
            "Type CLEAR to confirm."
        )
        # Keep the native confirmation readable in compact windows too.
        message = "\n\n".join(fill(paragraph, width=68) for paragraph in message.split("\n\n"))
        typed, accepted = QInputDialog.getText(self, "Clear saved books", message)
        if not accepted:
            return
        if typed.strip() != "CLEAR":
            QMessageBox.warning(self, "Saved books were not cleared",
                                "The confirmation did not match. Type CLEAR exactly, "
                                "in capital letters, to clear your saved books. "
                                "Nothing has been removed.")
            return
        try:
            count = self.store.clear_saved_books()
        except sqlite3.Error as error:
            QMessageBox.critical(self, "Could not clear saved books",
                                 f"Your saved books could not be cleared:\n{error}")
            return
        self._library_query = ""
        self._library_draft = ""
        self._library_filter = "All shelves"
        self.refresh(reset_page=1)
        QMessageBox.information(self, "Saved books cleared",
                                f"Removed {count:,} saved books and their reading history. "
                                "Your shelves, goals, and downloads are still available.")

    def _stats(self, entries: dict[str, str]) -> QWidget:
        page, layout = self._page("Stats & Goals", "See the shape of your reading.", "A clear view of the books and dates you have recorded, with no account or tracking service.")
        stats = self.store.stats()
        row = QVBoxLayout() if self._responsive_compact else QHBoxLayout()
        for value, title in ((stats["read_count"] or 0, "Books finished"),
                             (stats["total"] or 0, "On your shelves"),
                             (f"{stats['average_rating']:.1f} ★" if stats["average_rating"] is not None else "—", "Average rating")):
            card, inside = surface()
            inside.addWidget(label(str(value), "pageTitle"))
            inside.addWidget(label(title, "muted"))
            row.addWidget(card)
        layout.addLayout(row)
        layout.addWidget(label("READING GOALS", "smallCaps"))
        for goal in self.store.goals():
            card, inside = surface()
            heading = QHBoxLayout()
            heading.addWidget(label(goal["label"], "sectionTitle"), 1)
            heading.addWidget(self._goal_edit_button(goal))
            inside.addLayout(heading)
            inside.addWidget(label(f"{goal['completed']} of {goal['target_books']} books · {goal['start_on']} to {goal['end_on']}", "muted"))
            inside.addWidget(label(self._goal_scope_text(goal), "muted"))
            percentage = min(100, round(100 * goal["completed"] / goal["target_books"]))
            inside.addWidget(label(f"{percentage}% complete", "smallCaps"))
            layout.addWidget(card)
        add_goal = QPushButton("+  Set a reading goal")
        add_goal.setObjectName("primary")
        add_goal.clicked.connect(self._add_goal)
        layout.addWidget(add_goal, alignment=Qt.AlignmentFlag.AlignLeft)
        if stats["undated_read"]:
            layout.addWidget(label(f"{stats['undated_read']} finished books have no finish date, so they do not count toward dated goals.", "muted", wrap=True))
        layout.addSpacing(10)
        layout.addWidget(label("YOUR PATTERNS", "smallCaps"))
        pattern, inside = surface()
        genres = ", ".join(f"{item['genre']} ({item['count']})" for item in stats["genres"]) or "Add a genre to your books to see a pattern."
        inside.addWidget(label(f"Genres on your shelves: {genres}", "muted", wrap=True))
        months = ", ".join(f"{item['month']}: {item['count']}" for item in stats["months"]) or "Add finish dates to see reading activity over time."
        inside.addWidget(label(f"Finished over time: {months}", "muted", wrap=True))
        layout.addWidget(pattern)
        layout.addStretch()
        return page

    def _add_goal(self) -> None:
        dialog = GoalDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.navigate(3)

    def _goal_edit_button(self, goal: dict) -> QPushButton:
        button = QPushButton("Edit goal")
        button.setObjectName("secondary")
        button.setAccessibleName(f"Edit goal {goal['label']}")
        button.clicked.connect(partial(self._edit_goal, goal))
        return button

    @staticmethod
    def _goal_scope_text(goal: dict) -> str:
        if goal.get("scope") != "selected":
            return "All books in My Library count."
        count = len(goal["book_ids"])
        return f"Only {count:,} selected {'book counts' if count == 1 else 'books count'}."

    def _edit_goal(self, goal: dict) -> None:
        dialog = GoalDialog(self.store, self, goal=goal)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()

    def _change_status(self, book: dict) -> None:
        shelves_before = self.store.custom_shelves()
        current = self.store.entries().get(book["id"])
        saved = self.store.book(book["id"])
        dialog = ShelfDialog(book["title"], current, self, store=self.store,
                             selected=saved.get("shelves") or "")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            if self.store.custom_shelves() != shelves_before:
                self.refresh()
            return
        try:
            self.store.assign_shelves(book["id"], dialog.shelf.currentText(), dialog.custom.selected_shelves())
        except (OSError, sqlite3.Error, ValueError) as error:
            QMessageBox.critical(self, "Could not save book", str(error))
            return
        self._discovery_results = [match for match in self._discovery_results if match.book["id"] != book["id"]]
        self.refresh()

    def _install_model(self) -> None:
        if self._install_worker and self._install_worker.isRunning():
            return
        self._install_worker = ModelInstallWorker(self.store.directory, self.store.catalog_books(),
                                                   self.store.catalog_revision())
        self._install_worker.install_finished.connect(self._model_installed)
        self._install_worker.start()
        self.refresh()
        QMessageBox.information(self, "Preparing local recommendations", "The free model and offline catalog index are being prepared in BookMatch's data folder. You can continue using the app; Settings will update when it finishes.")

    def _model_installed(self, error: str) -> None:
        if error:
            QMessageBox.warning(self, "Model install failed", f"BookMatch will keep using metadata search.\n\n{error}")
        else:
            QMessageBox.information(self, "Model ready", "The local model is ready. Discovery searches will stay on this computer.")
        self.refresh()

    def _show_book(self, book_id: str) -> None:
        shelves_before = self.store.custom_shelves()
        dialog = BookDetailsDialog(self.store, book_id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._discovery_results = [match for match in self._discovery_results if match.book["id"] != book_id]
            self.refresh()
        elif self.store.custom_shelves() != shelves_before:
            self.refresh()

    def _add_book(self) -> None:
        shelves_before = self.store.custom_shelves()
        dialog = AddBookDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self.navigate(1)
        elif self.store.custom_shelves() != shelves_before:
            self.refresh()

    def _import_goodreads(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Choose your Goodreads export", "", "CSV files (*.csv)")
        if not name:
            return
        try:
            preview = parse_goodreads_csv(Path(name))
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "Could not read CSV", str(error))
            return
        summary = (f"{preview.valid_count} valid books · {len(preview.errors)} rows with issues\n\n"
                   "Existing library entries will be kept as they are. Repeated Goodreads IDs are skipped.\n\n")
        if preview.rows:
            summary += "First books in the file:\n" + "\n".join(
                f"• {row['title']} — {row['author']}" for row in preview.rows[:5]
            )
        if preview.errors:
            summary += "\n\nIssues:\n" + "\n".join(preview.errors[:5])
        if not preview.rows:
            QMessageBox.information(self, "Nothing to import", summary)
            return
        choice = QMessageBox.question(self, "Review Goodreads import", summary + "\n\nImport the valid books?")
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            result = import_goodreads(self.store, preview)
        except (sqlite3.Error, OSError, ValueError) as error:
            QMessageBox.critical(self, "Import failed", str(error))
            return
        self.refresh()
        self.navigate(1)
        QMessageBox.information(self, "Import complete", f"Added {result['added']} books. Skipped {result['skipped']} existing books. {result['invalid']} rows had issues.")

    def _export_library(self) -> None:
        suggested = Path.home() / "Documents" / "BookMatch-library.json"
        name, _ = QFileDialog.getSaveFileName(self, "Export your library", str(suggested), "JSON files (*.json)")
        if not name:
            return
        try:
            count = export_library(self.store, Path(name))
        except (OSError, ValueError) as error:
            QMessageBox.critical(self, "Export failed", str(error))
            return
        QMessageBox.information(self, "Export complete", f"Exported {count} books, your shelves, and reading goals to {name}.")

    def _import_json(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Choose a BookMatch export", "", "JSON files (*.json)")
        if not name:
            return
        try:
            preview = parse_bookmatch_json(Path(name))
        except (OSError, UnicodeError, ValueError) as error:
            QMessageBox.warning(self, "Could not read export", str(error))
            return
        summary = (f"{preview.valid_count} valid books · {len(preview.shelves or [])} shelves · {len(preview.goals or [])} goals · {len(preview.errors)} entries with issues\n\n"
                   "Books already in this library will be kept unchanged. Identical reading goals will be skipped.\n\n")
        if preview.rows:
            summary += "First books in the file:\n" + "\n".join(
                f"• {row['title']} — {row['author']}" for row in preview.rows[:5]
            )
        if preview.errors:
            summary += "\n\nIssues:\n" + "\n".join(preview.errors[:5])
        if not preview.rows and not preview.shelves and not preview.goals:
            QMessageBox.information(self, "Nothing to import", summary)
            return
        if QMessageBox.question(self, "Review BookMatch import", summary + "\n\nImport these books, shelves, and goals?") != QMessageBox.StandardButton.Yes:
            return
        try:
            result = import_bookmatch_json(self.store, preview)
        except (sqlite3.Error, OSError, ValueError) as error:
            QMessageBox.critical(self, "Import failed", str(error))
            return
        self.refresh()
        self.navigate(1)
        QMessageBox.information(self, "Import complete", f"Added {result['added']} books and {result['goals_added']} goals. Skipped {result['skipped']} existing books and {result['goals_skipped']} identical goals. {result['invalid']} entries had issues.")

    def closeEvent(self, event) -> None:
        if any(worker and worker.isRunning() for worker in (self._search_worker, self._install_worker)):
            event.ignore()
            QMessageBox.information(self, "Please wait", "BookMatch is finishing a local search or catalog index. Please close the window again when that work is done.")
            return
        if not self._store_closed:
            self.store.close()
        super().closeEvent(event)


class SearchWorker(QThread):
    finished_search = Signal(object, str, object)
    failed = Signal(str)

    def __init__(self, query: str, books: list[dict], directory: Path,
                 catalog_books: list[dict], catalog_revision: str):
        super().__init__()
        self.query = query
        self.books = books
        self.directory = directory
        self.catalog_books = catalog_books
        self.catalog_revision = catalog_revision

    def run(self) -> None:
        try:
            result = recommend(self.query, self.books, self.directory, limit=None,
                               catalog_books=self.catalog_books,
                               catalog_revision=self.catalog_revision)
            self.finished_search.emit(*result)
        except Exception as error:
            self.failed.emit(str(error))


class ModelInstallWorker(QThread):
    install_finished = Signal(str)

    def __init__(self, directory: Path, catalog_books: list[dict], catalog_revision: str):
        super().__init__()
        self.directory = directory
        self.catalog_books = catalog_books
        self.catalog_revision = catalog_revision

    def run(self) -> None:
        try:
            install_model(self.directory, self.catalog_books, self.catalog_revision)
            self.install_finished.emit("")
        except Exception as error:
            self.install_finished.emit(str(error))
