"""Focused dialogs for personal books and reading activity."""

from __future__ import annotations

import sqlite3
from datetime import date
from html import escape
from math import ceil, cos, pi, sin

from PySide6.QtGui import QColor, QIntValidator, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from shiboken6 import isValid

from .metadata import (cached_work_metadata, fetch_work_summary, genre_from_subjects,
                       public_field_locks)
from .storage import LibraryStore, STATUSES
from .messages import MessageBox as QMessageBox
from .widgets import BookMatchComboBox, ShelfCheckBox


PUBLIC_FIELD_STYLE = """
QLineEdit, QPlainTextEdit, QSpinBox {
    background: #e9eee8;
    color: #5e6d63;
    border: 1px solid #cfdbcf;
    border-radius: 9px;
    padding: 8px 10px;
}
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: 0; }
"""


class NewShelfDialog(QDialog):
    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.name = None
        self.setWindowTitle("Add a shelf")
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.addWidget(QLabel("Give your new shelf a name"))
        self.name_field = QLineEdit()
        self.name_field.setMaxLength(60)
        self.name_field.setPlaceholderText("e.g. Favorites or Book club")
        self.name_field.setAccessibleName("New shelf name")
        layout.addWidget(self.name_field)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self):
        try:
            self.name = self.store.create_shelf(self.name_field.text())
        except (ValueError, sqlite3.Error) as error:
            self.error.setText(str(error))
            return
        self.accept()


class ShelfChecklist(QWidget):
    def __init__(self, store: LibraryStore, selected: str = "", parent=None):
        super().__init__(parent)
        self.store = store
        self.checkboxes = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll)
        self.add_button = QPushButton("+ Add a shelf…")
        self.add_button.setObjectName("secondary")
        self.add_button.clicked.connect(self._add)
        layout.addWidget(self.add_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self._reload({name.strip().casefold() for name in selected.split(",") if name.strip()})

    def _reload(self, selected):
        content = QWidget()
        content.setObjectName("formContent")
        boxes = QVBoxLayout(content)
        boxes.setContentsMargins(8, 4, 8, 4)
        boxes.setSpacing(5)
        self.checkboxes = {}
        for name in self.store.custom_shelves():
            box = ShelfCheckBox(name)
            box.setToolTip(name)
            box.setAccessibleName(f"Custom shelf {name}")
            box.setChecked(name.casefold() in selected)
            box.setMinimumHeight(30)
            boxes.addWidget(box)
            self.checkboxes[name] = box
        if not self.checkboxes:
            hint = QLabel("Add a custom shelf to organize books in more than one place.")
            hint.setWordWrap(True)
            boxes.addWidget(hint)
        boxes.addStretch()
        self.scroll.setWidget(content)
        self.scroll.setFixedHeight(min(175, max(55, len(self.checkboxes) * 35 + 10)))

    def selected_shelves(self) -> list[str]:
        return [name for name, box in self.checkboxes.items() if box.isChecked()]

    def text(self) -> str:
        return ", ".join(self.selected_shelves())

    def _add(self):
        dialog = NewShelfDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = {name.casefold() for name in self.selected_shelves()}
            selected.add(dialog.name.casefold())
            self._reload(selected)


class ManageShelvesDialog(QDialog):
    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle("Manage shelves")
        self.setMinimumSize(430, 350)
        layout = QVBoxLayout(self)
        hint = QLabel("The four reading-status shelves stay in your library. Deleting a custom shelf keeps all its books.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        layout.addWidget(self.scroll, 1)
        add = QPushButton("+ Add a shelf…")
        add.clicked.connect(self._add)
        layout.addWidget(add)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._reload()

    def _reload(self):
        content = QWidget()
        content.setObjectName("formContent")
        rows = QVBoxLayout(content)
        for shelf in self.store.shelf_definitions():
            row = QHBoxLayout()
            title = QLabel(shelf["name"])
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            row.addWidget(title, 1)
            if shelf["builtin"]:
                row.addWidget(QLabel("Built in"))
            else:
                delete = QPushButton("Delete")
                delete.setObjectName("danger")
                delete.setAccessibleName(f"Delete shelf {shelf['name']}")
                delete.clicked.connect(lambda _checked=False, name=shelf["name"]: self._delete(name))
                row.addWidget(delete)
            rows.addLayout(row)
        rows.addStretch()
        self.scroll.setWidget(content)

    def _add(self):
        if NewShelfDialog(self.store, self).exec() == QDialog.DialogCode.Accepted:
            self._reload()

    def _delete(self, name):
        if QMessageBox.question(self, "Delete shelf", f'Delete “{name}”? Its books will stay in your library.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                                QMessageBox.StandardButton.Cancel) == QMessageBox.StandardButton.Yes:
            try:
                self.store.delete_shelf(name)
            except (ValueError, sqlite3.Error) as error:
                QMessageBox.warning(self, "Could not delete shelf", str(error))
                return
            self._reload()


class ShelfDialog(QDialog):
    def __init__(self, title: str, current: str | None, parent=None, *, store: LibraryStore, selected: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Choose a shelf")
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(15)
        heading = QLabel(f"Where should {title} go?")
        heading.setWordWrap(True)
        heading.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(heading)
        layout.addWidget(QLabel("Reading status · choose one"))
        self.shelf = BookMatchComboBox()
        self.shelf.setAccessibleName("Choose a reading shelf")
        self.shelf.addItems(STATUSES)
        if current in STATUSES:
            self.shelf.setCurrentText(current)
        layout.addWidget(self.shelf)
        layout.addWidget(QLabel("Custom shelves · choose any"))
        self.custom = ShelfChecklist(store, selected)
        layout.addWidget(self.custom)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class PageJumpDialog(QDialog):
    def __init__(self, current: int, count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Go to page")
        self.setMinimumWidth(300)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(15)
        layout.addWidget(QLabel(f"Choose a page from 1 to {count:,}."))
        self.page_number = QSpinBox()
        self.page_number.setRange(1, count)
        self.page_number.setValue(current + 1)
        self.page_number.setAccessibleName("Page number")
        layout.addWidget(self.page_number)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Go to page")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.page_number.selectAll()


def _set_public_field(field: QWidget, locked: bool) -> None:
    """Show a sourced value as read only while retaining text selection."""
    if isinstance(field, (QLineEdit, QPlainTextEdit, QSpinBox)):
        field.setReadOnly(locked)
    field.setStyleSheet(PUBLIC_FIELD_STYLE if locked else "")
    field.setToolTip("Provided by Open Library · read only in BookMatch" if locked else "")


class ExpandingTextEdit(QPlainTextEdit):
    """Show short descriptions in full and scroll inside the field for very long ones."""

    def __init__(self, minimum_height: int, maximum_height: int):
        super().__init__()
        self.base_height = minimum_height
        self.setMinimumHeight(minimum_height)
        self.setMaximumHeight(maximum_height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.textChanged.connect(self._schedule_fit)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._schedule_fit()

    def _schedule_fit(self) -> None:
        QTimer.singleShot(0, self._fit_content)

    def _fit_content(self) -> None:
        if not isValid(self):
            return
        document = self.document()
        block = document.firstBlock()
        content_height = 0.0
        while block.isValid():
            content_height += document.documentLayout().blockBoundingRect(block).height()
            block = block.next()
        chrome = max(20, self.height() - self.viewport().height())
        wanted = max(self.base_height, ceil(content_height + chrome + 8))
        wanted = min(wanted, self.maximumHeight())
        if wanted != self.minimumHeight():
            self.setMinimumHeight(wanted)


class CompactNotesEdit(QPlainTextEdit):
    """Keep empty personal writing fields small, then scroll after they expand."""

    def __init__(self, text: str):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setPlainText(text)
        self.textChanged.connect(self._sync_height)
        self._sync_height()

    def _sync_height(self) -> None:
        wanted = 120 if self.toPlainText().strip() else 52
        if self.height() != wanted:
            self.setFixedHeight(wanted)


def _text_box(text: str = "", height: int = 70, *, grow: bool = False) -> QPlainTextEdit:
    box = ExpandingTextEdit(height, 420) if grow else QPlainTextEdit()
    box.setPlainText(text)
    if not grow:
        box.setFixedHeight(height)
    return box


def _optional_date(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as error:
        raise ValueError("Enter dates as YYYY-MM-DD, or leave them blank") from error


def _optional_int(value: str, name: str, maximum: int) -> int | None:
    value = value.strip()
    if not value:
        return None
    if not value.isdecimal() or not 1 <= int(value) <= maximum:
        raise ValueError(f"{name} must be a number between 1 and {maximum:,}")
    return int(value)


class RatingStar(QPushButton):
    """A star that can display any quarter of its filled area."""

    previewed = Signal(int, float)
    preview_ended = Signal()

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        self.number = number
        self.fraction = 0.0
        self.hover_fraction = 1.0
        self.setFixedSize(36, 36)
        self.setFlat(True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"Rate {number - 0.5:g} or {number} stars")
        self.setToolTip(f"Left half: {number - 0.5:g} stars · Right half: {number} stars")

    def set_fraction(self, fraction: float) -> None:
        fraction = max(0.0, min(1.0, fraction))
        if self.fraction != fraction:
            self.fraction = fraction
            self.update()

    def _preview_at(self, x: float) -> None:
        self.hover_fraction = 0.5 if x < self.width() / 2 else 1.0
        self.previewed.emit(self.number, self.hover_fraction)

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        self._preview_at(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        super().mouseMoveEvent(event)
        self._preview_at(event.position().x())

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.hover_fraction = 1.0
        self.preview_ended.emit()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        outer_radius, inner_radius = 13.0, 5.7
        path = QPainterPath()
        for point in range(10):
            angle = -pi / 2 + point * pi / 5
            radius = outer_radius if point % 2 == 0 else inner_radius
            vertex = QPointF(center.x() + cos(angle) * radius,
                             center.y() + sin(angle) * radius)
            if point == 0:
                path.moveTo(vertex)
            else:
                path.lineTo(vertex)
        path.closeSubpath()
        gold = QColor("#a87b31")
        if self.fraction:
            painter.save()
            painter.setClipRect(QRectF(center.x() - outer_radius,
                                       center.y() - outer_radius,
                                       outer_radius * 2 * self.fraction,
                                       outer_radius * 2))
            painter.fillPath(path, gold)
            painter.restore()
        painter.setPen(QPen(gold, 1.5))
        painter.drawPath(path)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#5a8569"), 1.5, Qt.PenStyle.DotLine))
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)


class RatingPicker(QWidget):
    """Five direct star choices with optional quarter-star adjustment."""

    def __init__(self, rating: float | None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(2)
        self.stars: list[RatingStar] = []
        self._preview_active = False
        for number in range(1, 6):
            star = RatingStar(number)
            star.previewed.connect(self._preview)
            star.preview_ended.connect(self._end_preview)
            star.clicked.connect(lambda _checked=False, value=number, button=star:
                                 self.slider.setValue((value - 1) * 4 + round(button.hover_fraction * 4)))
            self.stars.append(star)
            row.addWidget(star)
        self.value_label = QLabel()
        self.value_label.setMinimumWidth(85)
        row.addWidget(self.value_label)
        self.fine_button = QPushButton("Fine tune")
        self.fine_button.setObjectName("secondary")
        self.fine_button.setCheckable(True)
        self.fine_button.toggled.connect(self._toggle_fine)
        row.addWidget(self.fine_button)
        clear = QPushButton("Clear")
        clear.setObjectName("secondary")
        clear.setAccessibleName("Clear rating")
        clear.clicked.connect(lambda: self.slider.setValue(0))
        row.addWidget(clear)
        row.addStretch()
        layout.addLayout(row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 20)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(4)
        self.slider.setTickInterval(4)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setAccessibleName("Fine tune rating in quarter-star steps")
        self.slider.setValue(round((rating or 0) * 4))
        layout.addWidget(self.slider)
        self.slider.hide()
        self.slider.valueChanged.connect(self._show_value)
        self._show_value(self.slider.value())

    def _show_value(self, quarter: int) -> None:
        if not self._preview_active:
            self._render_value(quarter)

    def _render_value(self, quarter: int) -> None:
        for index, star in enumerate(self.stars, start=1):
            star.set_fraction((quarter - (index - 1) * 4) / 4)
        if not quarter:
            self.value_label.setText("Unrated")
        else:
            self.value_label.setText(f"{quarter / 4:g} / 5")

    def _preview(self, star_number: int, fraction: float) -> None:
        self._preview_active = True
        self._render_value((star_number - 1) * 4 + round(fraction * 4))

    def _end_preview(self) -> None:
        self._preview_active = False
        self._render_value(self.slider.value())

    def _toggle_fine(self, visible: bool) -> None:
        self.slider.setVisible(visible)
        self.fine_button.setText("Hide fine tune" if visible else "Fine tune")

    def rating(self) -> float | None:
        return self.slider.value() / 4 if self.slider.value() else None


class CatalogPickerDialog(QDialog):
    def __init__(self, store: LibraryStore, query: str = "", parent=None):
        super().__init__(parent)
        self.store = store
        self.book_id: str | None = None
        self.setWindowTitle("Find a book in the offline catalog")
        self.setMinimumSize(650, 430)
        layout = QVBoxLayout(self)
        intro = QLabel("Search the 20,000 books already stored on this Mac. No search text is sent online.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.search = QLineEdit(query)
        self.search.setPlaceholderText("Search title, author, or subject")
        self.search.setAccessibleName("Search offline book catalog")
        layout.addWidget(self.search)
        self.results = QListWidget()
        self.results.setAccessibleName("Matching catalog books")
        self.results.setStyleSheet("""
            QListWidget { background: #fffefa; color: #26332e; border: 1px solid #d9e0d6;
                          border-radius: 9px; padding: 5px; }
            QListWidget::item { padding: 7px 10px; }
            QListWidget::item:selected { background: #d5e3d5; color: #234e3b; border-radius: 6px; }
        """)
        layout.addWidget(self.results, 1)
        self.summary = QLabel()
        layout.addWidget(self.summary)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use selected book")
        buttons.accepted.connect(self._choose)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.results.itemDoubleClicked.connect(lambda _item: self._choose())
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._refresh)
        self.search.textChanged.connect(lambda _text: self.timer.start(180))
        self.search.returnPressed.connect(self._refresh)
        self._refresh()
        self.search.setFocus()

    def _refresh(self) -> None:
        query = self.search.text().strip()
        self.results.clear()
        owned = self.store.entries()
        for book in self.store.catalog_books(query, limit=30):
            suffix = "  ·  On your shelf" if book["id"] in owned else ""
            item = QListWidgetItem(f"{book['title']}  —  {book['author']}{suffix}")
            item.setToolTip(f"{book['title']} — {book['author']}")
            item.setData(Qt.ItemDataRole.UserRole, book["id"])
            self.results.addItem(item)
        if self.results.count():
            self.results.setCurrentRow(0)
        count = self.store.catalog_count(query)
        self.summary.setText(f"Showing {min(count, 30):,} of {count:,} matches")

    def _choose(self) -> None:
        item = self.results.currentItem()
        if item is None:
            QMessageBox.information(self, "Choose a book", "Select a matching title first.")
            return
        self.book_id = item.data(Qt.ItemDataRole.UserRole)
        self.accept()


class WorkMetadataWorker(QThread):
    loaded = Signal(object)
    failed = Signal(str)

    def __init__(self, work_id: str, directory, parent=None):
        super().__init__(parent)
        self.work_id = work_id
        self.directory = directory

    def run(self) -> None:
        try:
            self.loaded.emit(fetch_work_summary(self.work_id, self.directory))
        except Exception as error:
            self.failed.emit(str(error))


class AddBookDialog(QDialog):
    def __init__(self, store: LibraryStore, parent=None):
        super().__init__(parent)
        self.store = store
        self.book_id: str | None = None
        self.selected_book_id: str | None = None
        self._lookup_worker: WorkMetadataWorker | None = None
        self.setWindowTitle("Add a book")
        self.setMinimumSize(650, 500)
        self.resize(760, 690)
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("formContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 16, 6)
        content_layout.setSpacing(14)
        content_layout.addWidget(QLabel("Add a book to your library"))
        picker_row = QHBoxLayout()
        self.pick_button = QPushButton("Find in offline catalog…")
        self.pick_button.setObjectName("secondary")
        self.pick_button.clicked.connect(self._choose_catalog)
        picker_row.addWidget(self.pick_button)
        self.lookup_button = QPushButton("Look up more details")
        self.lookup_button.setObjectName("secondary")
        self.lookup_button.setEnabled(False)
        self.lookup_button.clicked.connect(self._lookup_more)
        picker_row.addWidget(self.lookup_button)
        self.manual_button = QPushButton("Enter manually")
        self.manual_button.setObjectName("secondary")
        self.manual_button.clicked.connect(self._use_manual_entry)
        self.manual_button.hide()
        picker_row.addWidget(self.manual_button)
        picker_row.addStretch()
        content_layout.addLayout(picker_row)
        self.source_note = QLabel("Or enter a book manually below.")
        self.source_note.setTextFormat(Qt.TextFormat.PlainText)
        self.source_note.setWordWrap(True)
        content_layout.addWidget(self.source_note)
        form = QFormLayout()
        form.setSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title_field = QLineEdit()
        self.title_field.setPlaceholderText("Book title")
        self.author_field = QLineEdit()
        self.author_field.setPlaceholderText("Author")
        self.genre_field = QLineEdit()
        self.genre_field.setPlaceholderText("Optional genre or subjects")
        self.description_field = _text_box(height=160, grow=True)
        self.description_field.setPlaceholderText("Optional description")
        self.year_field = QLineEdit()
        self.year_field.setPlaceholderText("Optional publication year (YYYY)")
        self.year_field.setValidator(QIntValidator(1, 3000, self))
        self.status_field = BookMatchComboBox()
        self.status_field.addItems(STATUSES)
        self.shelves_field = ShelfChecklist(store)
        for name, field in (("Title", self.title_field), ("Author", self.author_field),
                            ("Genre", self.genre_field), ("Description", self.description_field),
                            ("Published", self.year_field), ("Reading status", self.status_field),
                            ("Custom shelves", self.shelves_field)):
            form.addRow(name, field)
        content_layout.addLayout(form)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.title_field.setFocus()

    def _choose_catalog(self) -> None:
        picker = CatalogPickerDialog(self.store, self.title_field.text(), self)
        if picker.exec() != QDialog.DialogCode.Accepted or not picker.book_id:
            return
        book = self.store.book(picker.book_id)
        if book is None:
            return
        if book["status"] is not None:
            QMessageBox.information(self, "Already on your shelf", "This book is already in My Library. Open its Details there to edit it.")
            return
        self.selected_book_id = book["id"]
        self.title_field.setText(book["title"])
        self.author_field.setText(book["author"])
        self.genre_field.setText(book["genre"] or genre_from_subjects(book["subjects"]))
        self.description_field.setPlainText(book["description"] or "")
        self.year_field.setText(str(book["publication_year"]) if book["publication_year"] else "")
        self.lookup_button.setEnabled(True)
        self.manual_button.show()
        subject_count = len([part for part in (book["subjects"] or "").split(", ") if part])
        self.source_note.setText(
            f"Selected Open Library work · {subject_count} subject tags stored locally. "
            "Shaded public details are read only; missing details can be entered. "
            "The optional lookup may find a description and first publication year.")
        self._sync_public_fields()

    def _use_manual_entry(self) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            return
        self.selected_book_id = None
        for field in (self.title_field, self.author_field, self.genre_field,
                      self.year_field):
            field.clear()
        self.description_field.clear()
        self._sync_public_fields()
        self.lookup_button.setEnabled(False)
        self.manual_button.hide()
        self.source_note.setText("Enter a book manually below.")
        self.title_field.setFocus()

    def _sync_public_fields(self) -> None:
        book = self.store.book(self.selected_book_id) if self.selected_book_id else None
        if book:
            book = {**book, "title": self.title_field.text(),
                    "author": self.author_field.text(), "genre": self.genre_field.text(),
                    "description": self.description_field.toPlainText(),
                    "publication_year": int(self.year_field.text())
                    if self.year_field.text().isdecimal() else None}
            cached = cached_work_metadata(self.selected_book_id, self.store.directory)
            locks = public_field_locks(book, cached)
        else:
            locks = dict.fromkeys(("title", "author", "genre", "description",
                                   "publication_year"), False)
        for name, field in (("title", self.title_field), ("author", self.author_field),
                            ("genre", self.genre_field),
                            ("description", self.description_field),
                            ("publication_year", self.year_field)):
            _set_public_field(field, locks[name])
        title = self.title_field.text()
        self.title_field.setToolTip(
            f"{title}\n\nProvided by Open Library · read only in BookMatch"
            if locks["title"] else title)

    def _lookup_more(self) -> None:
        if not self.selected_book_id or (self._lookup_worker and self._lookup_worker.isRunning()):
            return
        self.lookup_button.setEnabled(False)
        self.pick_button.setEnabled(False)
        self.manual_button.setEnabled(False)
        self.source_note.setText("Looking up this public work ID on Open Library…")
        worker = WorkMetadataWorker(self.selected_book_id, self.store.directory, self)
        self._lookup_worker = worker
        worker.loaded.connect(self._metadata_loaded)
        worker.failed.connect(self._metadata_failed)
        worker.finished.connect(lambda worker=worker: self._lookup_finished(worker))
        worker.start()

    def _lookup_finished(self, worker: WorkMetadataWorker | None) -> None:
        if worker is not None:
            worker.deleteLater()
        if self._lookup_worker is worker:
            self._lookup_worker = None

    def _metadata_loaded(self, result: dict) -> None:
        self.lookup_button.setEnabled(True)
        self.pick_button.setEnabled(True)
        self.manual_button.setEnabled(True)
        if result.get("work_id") != self.selected_book_id:
            return
        if result.get("description") and not self.description_field.toPlainText().strip():
            self.description_field.setPlainText(result["description"])
        if result.get("genre") and not self.genre_field.text().strip():
            self.genre_field.setText(result["genre"])
        if result.get("publication_year") and not self.year_field.text().strip():
            self.year_field.setText(str(result["publication_year"]))
        self._sync_public_fields()
        available = []
        if result.get("description"):
            available.append("description")
        if result.get("publication_year"):
            available.append("first publication year")
        summary = ", ".join(available) if available else "no additional fields"
        self.source_note.setText(f"Open Library lookup found {summary}.")

    def _metadata_failed(self, message: str) -> None:
        self.lookup_button.setEnabled(bool(self.selected_book_id))
        self.pick_button.setEnabled(True)
        self.manual_button.setEnabled(True)
        self.source_note.setText("The online lookup could not finish. The local catalog fields are still available.")
        QMessageBox.warning(self, "Book details unavailable", message)

    def _save(self) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            self.source_note.setText("Please wait for the Open Library lookup to finish before saving.")
            return
        try:
            fields = dict(title=self.title_field.text(), author=self.author_field.text(),
                          genre=self.genre_field.text(), description=self.description_field.toPlainText(),
                          publication_year=_optional_int(self.year_field.text(), "Published year", 3000),
                          status=self.status_field.currentText())
            if self.selected_book_id:
                self.store.add_catalog_book(self.selected_book_id, **fields)
                self.book_id = self.selected_book_id
            else:
                self.book_id = self.store.add_book(**fields)
            self.store.assign_shelves(self.book_id, self.status_field.currentText(),
                                     self.shelves_field.selected_shelves())
        except (ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Could not add book", str(error))
            return
        self.accept()

    def reject(self) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            self.source_note.setText("Please wait for the Open Library lookup to finish before closing this window.")
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            event.ignore()
            self.source_note.setText("Please wait for the Open Library lookup to finish before closing this window.")
            return
        super().closeEvent(event)


class BookDetailsDialog(QDialog):
    def __init__(self, store: LibraryStore, book_id: str, parent=None):
        super().__init__(parent)
        self.store = store
        self.book_id = book_id
        self._lookup_worker: WorkMetadataWorker | None = None
        self.book = store.book(book_id)
        if self.book is None:
            raise ValueError("Book not found")
        self._work_id = (self.book["source_id"] or "") if self.book["source"] == "openlibrary" else ""
        cached = cached_work_metadata(self._work_id, store.directory) if self._work_id else None
        self._public_metadata = cached or {}
        original_genre = self.book["genre"]
        original_description = self.book["description"]
        if self._work_id:
            store.fill_missing_catalog_details(
                book_id, genre=genre_from_subjects(self.book["subjects"]) or
                ((cached or {}).get("genre") or ""),
                description=(cached or {}).get("description") or "",
            )
            self.book = store.book(book_id)
        self._needs_lookup = bool(self._work_id and not self.book["description"] and cached is None)
        prefilled = []
        if not original_genre and self.book["genre"]:
            prefilled.append("genre from Open Library subjects")
        if not original_description and self.book["description"]:
            prefilled.append("description from Open Library")
        self.setWindowTitle(self.book["title"])
        self.setMinimumSize(700, 540)
        self.resize(790, 720)
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("formContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 8, 18, 8)
        self.metadata_note = QLabel()
        self.metadata_note.setWordWrap(True)
        self.metadata_note.setTextFormat(Qt.TextFormat.PlainText)
        if self._needs_lookup:
            self.metadata_note.setText("Looking up a missing description on Open Library…")
        elif prefilled:
            self.metadata_note.setText("Filled missing " + " and ".join(prefilled) + ". Your existing details were kept.")
        else:
            self.metadata_note.hide()
        content_layout.addWidget(self.metadata_note)
        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.title_field = QLineEdit(self.book["title"])
        self.title_field.setToolTip(self.book["title"])
        self.title_field.setMinimumWidth(480)
        self.title_field.setCursorPosition(0)
        self.author_field = QLineEdit(self.book["author"])
        self.genre_field = QLineEdit(self.book["genre"] or "")
        self.description_field = _text_box(self.book["description"] or "", 160, grow=True)
        self.year_field = QSpinBox()
        self.year_field.setRange(0, 3000)
        self.year_field.setSpecialValueText("Unknown")
        self.year_field.setValue(self.book["publication_year"] or 0)
        self.year_field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.status_field = BookMatchComboBox()
        self.status_field.addItems(STATUSES)
        if self.book["status"] in STATUSES:
            self.status_field.setCurrentText(self.book["status"])
        self.rating_field = RatingPicker(self.book["rating"])
        self.started_field = QLineEdit(self.book["started_on"] or "")
        self.started_field.setPlaceholderText("YYYY-MM-DD")
        self.finished_field = QLineEdit(self.book["finished_on"] or "")
        self.finished_field.setPlaceholderText("YYYY-MM-DD")
        self.notes_field = CompactNotesEdit(self.book["notes"] or "")
        self.review_field = CompactNotesEdit(self.book["review"] or "")
        self.shelves_field = ShelfChecklist(store, self.book["shelves"] or "")
        self.notes_field.setPlaceholderText("Private notes, visible only here")
        self.review_field.setPlaceholderText("Your review")
        fields = (("Title", self.title_field), ("Author", self.author_field),
                  ("Genre", self.genre_field), ("Description", self.description_field),
                  ("Published", self.year_field),
                  ("Reading status", self.status_field), ("Rating", self.rating_field),
                  ("Started", self.started_field),
                  ("Finished", self.finished_field), ("Private notes", self.notes_field),
                  ("Review", self.review_field), ("Custom shelves", self.shelves_field))
        for name, field in fields:
            form.addRow(name, field)
        self._sync_public_fields()
        content_layout.addLayout(form)
        if self.book.get("subjects"):
            subjects = QLabel("Open Library subjects: " + self.book["subjects"])
            subjects.setWordWrap(True)
            content_layout.addWidget(subjects)
        if (self.book.get("source_url") or "").startswith("https://openlibrary.org/works/"):
            source_link = QLabel(f'<a style="color: #315c47;" href="{escape(self.book["source_url"], quote=True)}">View this work on Open Library ↗</a>')
            source_link.setOpenExternalLinks(True)
            content_layout.addWidget(source_link)
        if self.book["source_shelf"]:
            shelf_note = QLabel(f"Imported Goodreads shelf: {self.book['source_shelf']}")
            shelf_note.setTextFormat(Qt.TextFormat.PlainText)
            content_layout.addWidget(shelf_note)
        content_layout.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if self._needs_lookup:
            QTimer.singleShot(0, self._start_metadata_lookup)

    def _start_metadata_lookup(self) -> None:
        if not self._work_id or self._lookup_worker is not None:
            return
        worker = WorkMetadataWorker(self._work_id, self.store.directory, self)
        self._lookup_worker = worker
        worker.loaded.connect(self._metadata_loaded)
        worker.failed.connect(self._metadata_failed)
        worker.finished.connect(lambda worker=worker: self._lookup_finished(worker))
        worker.start()

    def _lookup_finished(self, worker: WorkMetadataWorker) -> None:
        worker.deleteLater()
        if self._lookup_worker is worker:
            self._lookup_worker = None

    def _sync_public_fields(self) -> None:
        locks = public_field_locks(self.book, self._public_metadata)
        for name, field in (("title", self.title_field), ("author", self.author_field),
                            ("genre", self.genre_field),
                            ("description", self.description_field),
                            ("publication_year", self.year_field)):
            _set_public_field(field, locks[name])
        title = self.title_field.text()
        self.title_field.setToolTip(
            f"{title}\n\nProvided by Open Library · read only in BookMatch"
            if locks["title"] else title)
        if any(locks.values()):
            explanation = "Shaded details come from Open Library and are read only. Your reading details remain editable."
            current = self.metadata_note.text()
            if explanation not in current:
                self.metadata_note.setText(f"{current} {explanation}".strip())
            self.metadata_note.show()

    def _metadata_loaded(self, result: dict) -> None:
        if result.get("work_id") != self._work_id:
            return
        try:
            self.store.fill_missing_catalog_details(
                self.book_id,
                genre=result.get("genre") or genre_from_subjects(self.book["subjects"]),
                description=result.get("description") or "",
            )
        except (sqlite3.Error, OSError) as error:
            self._metadata_failed(str(error))
            return
        self.book = self.store.book(self.book_id)
        self._public_metadata = result
        if not self.genre_field.text().strip() and self.book["genre"]:
            self.genre_field.setText(self.book["genre"])
        if not self.description_field.toPlainText().strip() and self.book["description"]:
            self.description_field.setPlainText(self.book["description"])
        if self.book["description"]:
            self.metadata_note.setText("Filled missing public details from Open Library. Your existing details were kept.")
        else:
            self.metadata_note.setText("Open Library has no description for this work. You can add one yourself.")
        self._sync_public_fields()

    def _metadata_failed(self, message: str) -> None:
        self.metadata_note.setText(f"Could not look up missing details: {message}. You can still edit unshaded fields and your reading details.")
        self._sync_public_fields()

    def _save(self) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            self.metadata_note.setText("Please wait for the Open Library lookup to finish before saving.")
            return
        try:
            started = _optional_date(self.started_field.text())
            finished = _optional_date(self.finished_field.text())
            if started and finished and finished < started:
                raise ValueError("Finished date cannot be before started date")
            if self.book["source"] != "sample":
                self.store.update_book(
                    self.book_id, title=self.title_field.text(), author=self.author_field.text(),
                    genre=self.genre_field.text(), description=self.description_field.toPlainText(),
                    publication_year=self.year_field.value() or None,
                )
            self.store.update_entry(
                self.book_id, status=self.status_field.currentText(),
                rating=self.rating_field.rating(),
                notes=self.notes_field.toPlainText(), review=self.review_field.toPlainText(),
                started_on=started, finished_on=finished,
                shelves=self.shelves_field.text(),
            )
        except (ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Could not save book", str(error))
            return
        self.accept()

    def reject(self) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            self.metadata_note.setText("Please wait for the Open Library lookup to finish before closing this window.")
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self._lookup_worker and self._lookup_worker.isRunning():
            event.ignore()
            self.metadata_note.setText("Please wait for the Open Library lookup to finish before closing this window.")
            return
        super().closeEvent(event)


class GoalBooksDialog(QDialog):
    """Choose a fixed set of books; shelf shortcuts never become live rules."""

    def __init__(self, store: LibraryStore, selected_ids: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Choose books for your goal")
        self.setMinimumSize(520, 420)
        self.resize(650, 560)
        self.selected_ids = set(selected_ids)
        self.books = store.library_books()
        available = {book["id"] for book in self.books}
        for book_id in selected_ids:
            if book_id not in available:
                book = store.book(book_id)
                if book:
                    self.books.append(book)
        self.books.sort(key=lambda book: (book["title"].casefold(), book["author"].casefold()))
        self.boxes = {}
        self.shown_books = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        hint = QLabel("Choose books from My Library. To add a shelf’s current books, choose the shelf and click Select all shown. New books on that shelf won’t be added automatically.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search title, author, or genre")
        self.search.setAccessibleName("Search books for this goal")
        self.search.textChanged.connect(self._render)
        layout.addWidget(self.search)
        self.shelf_filter = BookMatchComboBox()
        self.shelf_filter.setAccessibleName("Goal book shelf filter")
        self.shelf_filter.addItems(("All shelves",) + STATUSES +
                                   tuple(f"Custom: {name}" for name in store.custom_shelves()))
        self.shelf_filter.currentTextChanged.connect(self._render)
        layout.addWidget(self.shelf_filter)
        actions = QHBoxLayout()
        self.select_shown = QPushButton("Select all shown")
        self.select_shown.setObjectName("secondary")
        self.select_shown.clicked.connect(lambda: self._select_shown(True))
        actions.addWidget(self.select_shown)
        self.clear_shown = QPushButton("Clear shown")
        self.clear_shown.setObjectName("secondary")
        self.clear_shown.clicked.connect(lambda: self._select_shown(False))
        actions.addWidget(self.clear_shown)
        actions.addStretch()
        layout.addLayout(actions)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll, 1)
        self.selection_count = QLabel()
        layout.addWidget(self.selection_count)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Use selected books")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._render()

    def _render(self, _value=None):
        query = self.search.text().strip().casefold()
        shelf = self.shelf_filter.currentText()
        custom = shelf.removeprefix("Custom: ").casefold()
        self.shown_books = [book for book in self.books if
                            (not query or query in " ".join(book.get(field) or "" for field in ("title", "author", "genre")).casefold())
                            and (shelf == "All shelves" or book["status"] == shelf or
                                 (shelf.startswith("Custom: ") and custom in
                                  {part.strip().casefold() for part in (book["shelves"] or "").split(",")}))]
        content = QWidget()
        content.setObjectName("formContent")
        rows = QVBoxLayout(content)
        rows.setContentsMargins(0, 4, 4, 4)
        rows.setSpacing(6)
        self.boxes = {}
        for book in self.shown_books:
            caption = f"{book['title']} — {book['author']}"
            if book["status"] is None:
                caption += " (outside My Library)"
            box = ShelfCheckBox(caption)
            box.setToolTip(caption)
            box.setAccessibleName(f"Include {caption} in goal")
            box.setChecked(book["id"] in self.selected_ids)
            box.toggled.connect(lambda checked, book_id=book["id"]: self._toggle(book_id, checked))
            rows.addWidget(box)
            self.boxes[book["id"]] = box
        if not self.shown_books:
            hint = QLabel("No books match. Try another search or shelf." if self.books else
                          "Add books to My Library first, then choose them for your goal.")
            hint.setWordWrap(True)
            rows.addWidget(hint)
        rows.addStretch()
        self.scroll.setWidget(content)
        self.select_shown.setEnabled(bool(self.shown_books))
        self.clear_shown.setEnabled(bool(self.shown_books))
        self._update_count()

    def _toggle(self, book_id, checked):
        if checked:
            self.selected_ids.add(book_id)
        else:
            self.selected_ids.discard(book_id)
        self._update_count()

    def _update_count(self):
        self.selection_count.setText(f"{len(self.selected_ids):,} selected · {len(self.shown_books):,} shown")

    def _select_shown(self, checked):
        for box in self.boxes.values():
            box.setChecked(checked)


class GoalDialog(QDialog):
    def __init__(self, store: LibraryStore, parent=None, *, goal: dict | None = None):
        super().__init__(parent)
        self.store = store
        self.goal_id = goal["id"] if goal else None
        self.goal_label = goal["label"] if goal else ""
        self.setWindowTitle("Edit reading goal" if goal else "Set a reading goal")
        self.setMinimumSize(440, 400)
        self.resize(540, 580)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 22, 22, 22)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        content.setObjectName("formContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)
        hint = QLabel("Choose a yearly goal or edit the dates for your own reading period.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        form = QFormLayout()
        form.setSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        year = date.today().year
        self.name_field = QLineEdit(goal["label"] if goal else f"{year} reading goal")
        self.start_field = QLineEdit(goal["start_on"] if goal else f"{year}-01-01")
        self.end_field = QLineEdit(goal["end_on"] if goal else f"{year}-12-31")
        self.target_field = QSpinBox()
        self.target_field.setRange(1, max(1000, goal["target_books"] if goal else 1000))
        self.target_field.setValue(goal["target_books"] if goal else 12)
        for name, field in (("Name", self.name_field), ("Start (YYYY-MM-DD)", self.start_field),
                            ("End (YYYY-MM-DD)", self.end_field), ("Books to finish", self.target_field)):
            field.setAccessibleName(name)
            field.setMinimumHeight(44)
            form.addRow(name, field)
        layout.addLayout(form)
        layout.addWidget(QLabel("Which books count?"))
        self.scope_field = BookMatchComboBox()
        self.scope_field.setAccessibleName("Books that count toward this goal")
        self.scope_field.addItems(("All books in My Library", "Only selected books"))
        self.book_ids = list(goal.get("book_ids", [])) if goal else []
        self.scope_field.setCurrentIndex(1 if goal and goal.get("scope") == "selected" else 0)
        self.scope_field.currentIndexChanged.connect(self._sync_selection)
        layout.addWidget(self.scope_field)
        self.selection_panel = QWidget()
        selection_layout = QVBoxLayout(self.selection_panel)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        self.selected_note = QLabel()
        self.selected_note.setWordWrap(True)
        selection_layout.addWidget(self.selected_note)
        self.choose_button = QPushButton("Choose books…")
        self.choose_button.setObjectName("secondary")
        self.choose_button.clicked.connect(self._choose_books)
        selection_layout.addWidget(self.choose_button, alignment=Qt.AlignmentFlag.AlignLeft)
        self.selection_target = QPushButton("Use selected count as target")
        self.selection_target.setObjectName("secondary")
        self.selection_target.clicked.connect(self._use_selected_target)
        selection_layout.addWidget(self.selection_target, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.selection_panel)
        hint = QLabel("A book counts when marked Read with a finish date inside this goal’s date range.")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self._sync_selection()
        layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        if self.goal_id is not None:
            self.delete_button = QPushButton("Delete goal…")
            self.delete_button.setObjectName("danger")
            self.delete_button.setAccessibleName(f"Delete goal {self.goal_label}")
            buttons.addButton(self.delete_button, QDialogButtonBox.ButtonRole.DestructiveRole)
            self.delete_button.clicked.connect(self._delete)
        outer.addWidget(buttons)

    def _delete(self) -> None:
        if self.goal_id is None:
            return
        choice = QMessageBox.question(
            self, "Delete reading goal",
            f'Delete “{self.goal_label}”? Your books, shelves, ratings, dates, '
            "reviews, and notes will stay.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if choice != QMessageBox.StandardButton.Yes:
            return
        try:
            self.store.delete_goal(self.goal_id)
        except (ValueError, sqlite3.Error) as error:
            QMessageBox.warning(self, "Could not delete goal", str(error))
            return
        self.accept()

    def _sync_selection(self, _index=None):
        self.selection_panel.setVisible(self.scope_field.currentIndex() == 1)
        count = len(self.book_ids)
        self.selected_note.setText(f"{count:,} {'book' if count == 1 else 'books'} selected. Only these books can count toward this goal.")
        self.selection_target.setEnabled(bool(count))

    def _choose_books(self):
        dialog = GoalBooksDialog(self.store, self.book_ids, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.book_ids = sorted(dialog.selected_ids)
            self._sync_selection()

    def _use_selected_target(self):
        self.target_field.setMaximum(max(self.target_field.maximum(), len(self.book_ids)))
        self.target_field.setValue(len(self.book_ids))

    def _save(self) -> None:
        try:
            start = _optional_date(self.start_field.text())
            end = _optional_date(self.end_field.text())
            if not start or not end:
                raise ValueError("A start and end date are required")
            selected = self.book_ids if self.scope_field.currentIndex() == 1 else None
            if selected == []:
                raise ValueError("Choose at least one book, or choose All books in My Library.")
            if self.goal_id is None:
                self.store.add_goal(self.name_field.text(), start, end, self.target_field.value(),
                                    book_ids=selected)
            else:
                self.store.update_goal(self.goal_id, self.name_field.text(), start, end,
                                       self.target_field.value(), book_ids=selected)
        except (ValueError, sqlite3.Error, OSError) as error:
            QMessageBox.warning(self, "Could not save goal", str(error))
            return
        self.accept()
