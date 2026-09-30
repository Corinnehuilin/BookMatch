"""Shared controls with predictable colors across macOS appearance modes."""

from __future__ import annotations

from math import cos, pi, sin

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QLineEdit, QListView,
                               QHBoxLayout, QPushButton, QProxyStyle, QSizePolicy, QStyle, QStyleFactory,
                               QStyledItemDelegate, QVBoxLayout, QLabel, QDialog, QWidget)


NORMAL_BG = QColor("#fffefa")
NORMAL_TEXT = QColor("#26332e")
HOVER_BG = QColor("#dcebdc")
HOVER_TEXT = QColor("#234e3b")
SELECTED_BG = QColor("#315c47")
SELECTED_TEXT = QColor("#ffffff")


def page_numbers(current: int, count: int) -> list[int | None]:
    """Visible one-based pages, with None marking a gap."""
    if count <= 7:
        return list(range(1, count + 1))
    if current <= 4:
        return [1, 2, 3, 4, 5, None, count]
    if current >= count - 3:
        return [1, None, *range(count - 4, count + 1)]
    return [1, None, current - 1, current, current + 1, None, count]


class PageNavigator(QWidget):
    page_changed = Signal(int)
    jump_requested = Signal()

    def __init__(self, current: int, count: int, *, compact: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("pageNavigator")
        self.current, self.count = current, count
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        previous = QPushButton("←" if compact else "← Previous")
        previous.setObjectName("pageArrow")
        previous.setAccessibleName("Previous page")
        previous.setToolTip("Previous page")
        previous.setEnabled(current > 0)
        previous.clicked.connect(lambda: self.page_changed.emit(current - 1))
        layout.addWidget(previous)
        layout.addStretch()
        for number in page_numbers(current + 1, count):
            button = QPushButton(str(number) if number is not None else "…")
            button.setObjectName("pageNumber")
            button.setProperty("current", number == current + 1)
            button.setProperty("page", number)
            button.setAccessibleName(f"Page {number}" if number is not None else "Jump to a page")
            button.setToolTip(f"Go to page {number}" if number is not None else "Jump to any page")
            if number is None:
                button.clicked.connect(self.jump_requested.emit)
            else:
                button.clicked.connect(lambda _checked=False, page=number:
                                       self.page_changed.emit(page - 1))
            layout.addWidget(button)
        layout.addStretch()
        following = QPushButton("→" if compact else "Next →")
        following.setObjectName("pageArrow")
        following.setAccessibleName("Next page")
        following.setToolTip("Next page")
        following.setEnabled(current < count - 1)
        following.clicked.connect(lambda: self.page_changed.emit(current + 1))
        layout.addWidget(following)


class ShelfCheckBox(QCheckBox):
    """Rounded choices with stable colors and native keyboard/check semantics."""

    def __init__(self, name: str, parent=None):
        super().__init__(name.replace("&", "&&"), parent)
        self.name = name
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(min(420, self.fontMetrics().horizontalAdvance(self.name) + 48), 34)

    def minimumSizeHint(self):
        return QSize(120, 34)

    def hitButton(self, position):
        return self.rect().contains(position)

    def enterEvent(self, event):
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.underMouse():
            painter.setBrush(HOVER_BG)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        if self.hasFocus():
            painter.setPen(QPen(QColor("#5a8569"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 8, 8)
        indicator = QRectF(7, (self.height() - 20) / 2, 20, 20)
        painter.setPen(QPen(SELECTED_BG if self.isChecked() else QColor("#b7c6b6"), 1))
        painter.setBrush(SELECTED_BG if self.isChecked() else NORMAL_BG)
        painter.drawRoundedRect(indicator, 5, 5)
        if self.isChecked():
            painter.setPen(QPen(SELECTED_TEXT, 2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath()
            path.moveTo(indicator.left() + 5, indicator.top() + 10)
            path.lineTo(indicator.left() + 9, indicator.top() + 14)
            path.lineTo(indicator.left() + 15, indicator.top() + 6)
            painter.drawPath(path)
        painter.setPen(NORMAL_TEXT)
        text = self.fontMetrics().elidedText(self.name, Qt.TextElideMode.ElideRight,
                                            max(0, self.width() - 43))
        painter.drawText(self.rect().adjusted(37, 0, -6, 0), Qt.AlignmentFlag.AlignVCenter, text)


class ShelfSection(QWidget):
    collapsed_changed = Signal(str, bool)

    def __init__(self, name: str, books: list[dict], card_factory, *, collapsed: bool,
                 compact: bool, current: int = 0, parent=None):
        super().__init__(parent)
        self.setObjectName("shelfSection")
        self.setProperty("shelfName", name)
        self.name, self.books = name, books
        self.card_factory, self.compact = card_factory, compact
        self.page = max(0, min(current, max(0, (len(books) - 1) // 12)))
        self._built_page = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.header = QPushButton()
        self.header.setObjectName("shelfHeader")
        self.header.setCheckable(True)
        self.header.setChecked(not collapsed)
        self.header.setAccessibleName(f"{name}, {len(books)} books")
        self.header.setToolTip(name)
        self.header.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.header.setMinimumWidth(0)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.header)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(12)
        layout.addWidget(self.body)
        self.header.toggled.connect(self._toggle)
        self._display(not collapsed)

    def _toggle(self, expanded):
        self._display(expanded)
        self.collapsed_changed.emit(self.name, not expanded)

    def _display(self, expanded):
        self._update_header_text()
        if expanded and self._built_page != self.page:
            self._build_body()
        self.body.setVisible(expanded)

    def _update_header_text(self):
        prefix = '▾  ' if self.header.isChecked() else '▸  '
        suffix = f" • {len(self.books):,}"
        metrics = self.header.fontMetrics()
        space = max(50, self.header.width() - 38 - metrics.horizontalAdvance(prefix + suffix))
        name = (metrics.elidedText(self.name, Qt.TextElideMode.ElideRight, space)
                if self.isVisible() else self.name)
        self.header.setText((prefix + name + suffix).replace('&', '&&'))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_header_text()

    def _build_body(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for book in self.books[self.page * 12:(self.page + 1) * 12]:
            self.body_layout.addWidget(self.card_factory(book))
        if not self.books:
            empty = QLabel("No books on this shelf yet.")
            empty.setObjectName("muted")
            self.body_layout.addWidget(empty)
        count = max(1, (len(self.books) + 11) // 12)
        if count > 1:
            pager = PageNavigator(self.page, count, compact=self.compact)
            pager.page_changed.connect(self._go_to)
            pager.jump_requested.connect(lambda: self._jump(count))
            self.body_layout.addWidget(pager)
        self._built_page = self.page

    def _go_to(self, page):
        count = max(1, (len(self.books) + 11) // 12)
        self.page = max(0, min(page, count - 1))
        self._build_body()

    def _jump(self, count):
        from .dialogs import PageJumpDialog
        dialog = PageJumpDialog(self.page, count, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._go_to(dialog.page_number.value() - 1)


class RatingSummary(QWidget):
    """A compact, noninteractive five-star view of a saved quarter-star rating."""

    def __init__(self, rating: float, parent=None):
        super().__init__(parent)
        self.rating = rating
        self.setFixedHeight(25)
        self.setMinimumWidth(170)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setObjectName("ratingSummary")
        self.setAccessibleName(f"Your rating: {rating:g} out of 5 stars")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gold = QColor("#a87b31")
        for number in range(5):
            center_x, center_y = 10 + number * 22, 12
            path = QPainterPath()
            for point in range(10):
                angle = -pi / 2 + point * pi / 5
                radius = 8 if point % 2 == 0 else 3.5
                x = center_x + cos(angle) * radius
                y = center_y + sin(angle) * radius
                if point == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            path.closeSubpath()
            fraction = max(0.0, min(1.0, self.rating - number))
            if fraction:
                painter.save()
                painter.setClipRect(center_x - 8, center_y - 8,
                                    round(16 * fraction), 16)
                painter.fillPath(path, gold)
                painter.restore()
            painter.setPen(QPen(gold, 1.1))
            painter.drawPath(path)
        painter.setPen(QColor("#647167"))
        painter.drawText(self.rect().adjusted(120, 0, 0, 0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{self.rating:g} / 5")


class CatalogSearchLineEdit(QLineEdit):
    """Keep the search hint visible even when macOS focuses an empty field."""

    HINT = "Title, author, genre, or subject"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAccessibleName("Search catalog by title, author, genre, or subject")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.text():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#87928b"))
        middle = self.height() // 2
        painter.drawEllipse(17, middle - 6, 9, 9)
        painter.drawLine(24, middle + 2, 29, middle + 7)
        hint_rect = self.rect().adjusted(37, 0, -14, 0)
        hint = painter.fontMetrics().elidedText(
            self.HINT, Qt.TextElideMode.ElideRight, max(0, hint_rect.width()))
        painter.drawText(hint_rect,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, hint)


def _blend(start: QColor, end: QColor, fraction: float) -> QColor:
    fraction = max(0.0, min(1.0, fraction))
    return QColor(
        round(start.red() + (end.red() - start.red()) * fraction),
        round(start.green() + (end.green() - start.green()) * fraction),
        round(start.blue() + (end.blue() - start.blue()) * fraction),
    )


class OptionListView(QListView):
    def __init__(self, combo: "BookMatchComboBox"):
        super().__init__(combo)
        self.combo = combo
        self.hovered_row = -1
        self.hover_fraction = 0.0
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSpacing(0)
        self.animation = QVariantAnimation(self)
        self.animation.setDuration(140)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.valueChanged.connect(self._animate)

    def _animate(self, value: float) -> None:
        self.hover_fraction = float(value)
        self.viewport().update()

    def _set_hovered(self, row: int, *, animate: bool = True) -> None:
        if row == self.hovered_row:
            return
        self.hovered_row = row
        self.animation.stop()
        self.hover_fraction = 0.0 if animate and row >= 0 else 1.0
        if animate and row >= 0:
            self.animation.start()
        self.viewport().update()

    def mouseMoveEvent(self, event) -> None:
        self._set_hovered(self.indexAt(event.position().toPoint()).row())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._set_hovered(-1, animate=False)
        super().leaveEvent(event)

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_Home,
                           Qt.Key.Key_End, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self._set_hovered(self.currentIndex().row(), animate=False)


class OptionDelegate(QStyledItemDelegate):
    def __init__(self, view: OptionListView):
        super().__init__(view)
        self.view = view

    def sizeHint(self, option, index) -> QSize:
        size = super().sizeHint(option, index)
        size.setHeight(max(32, size.height()))
        return size

    def paint(self, painter: QPainter, option, index) -> None:
        selected = index.row() == self.view.combo.currentIndex()
        hovered = index.row() == self.view.hovered_row
        if selected:
            background, foreground = SELECTED_BG, SELECTED_TEXT
        elif hovered:
            background = _blend(NORMAL_BG, HOVER_BG, self.view.hover_fraction)
            foreground = HOVER_TEXT
        else:
            background, foreground = NORMAL_BG, NORMAL_TEXT
        if not option.state & QStyle.StateFlag.State_Enabled:
            foreground = QColor("#839087")
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(option.rect, NORMAL_BG)
        if selected or hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(QRectF(option.rect).adjusted(2, 2, -2, -2), 9, 9)
        painter.setPen(foreground)
        text_rect = option.rect.adjusted(12, 0, -10, 0)
        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        title = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight,
                                                  max(0, text_rect.width()))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         title)
        painter.restore()


class OptionPopupStyle(QProxyStyle):
    """Use a list popup so the shared delegate controls every option on macOS."""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint in (QStyle.StyleHint.SH_ComboBox_Popup,
                    QStyle.StyleHint.SH_ComboBox_UseNativePopup):
            return 0
        return super().styleHint(hint, option, widget, returnData)


class OptionPopupPainter(QObject):
    """Paint translucent popup edges with antialiasing, without a binary mask."""

    def eventFilter(self, popup, event):
        if event.type() == QEvent.Type.Paint:
            painter = QPainter(popup)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(NORMAL_BG)
            painter.setPen(QPen(QColor("#d9e0d6"), 1))
            painter.drawRoundedRect(QRectF(popup.rect()).adjusted(.5, .5, -.5, -.5), 10, 10)
            return True
        return super().eventFilter(popup, event)


class BookMatchComboBox(QComboBox):
    """A combo whose popup visibly distinguishes normal, hover, and selection."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup_style = OptionPopupStyle(QStyleFactory.create("Fusion"))
        self._popup_style.setParent(self)
        self.setStyle(self._popup_style)
        self.setMaxVisibleItems(12)
        view = OptionListView(self)
        view.setItemDelegate(OptionDelegate(view))
        self.setView(view)
        self._popup_painter = OptionPopupPainter(self)
        view.window().installEventFilter(self._popup_painter)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#315c47" if self.isEnabled() else "#a0a79f"), 1.7))
        x, y = self.width() - 18, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)

    def showPopup(self) -> None:
        view = self.view()
        if isinstance(view, OptionListView):
            view._set_hovered(-1, animate=False)
        popup = view.window()
        popup.setObjectName("optionPopup")
        popup.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        popup.setAutoFillBackground(False)
        popup.setFrameShape(QFrame.Shape.NoFrame)
        # Inset the option rows so they cannot paint over the smooth outer curve.
        popup.layout().setContentsMargins(5, 5, 5, 5)
        popup.setStyleSheet("QFrame#optionPopup { background: #fffefa; "
                            "border: 1px solid #d9e0d6; border-radius: 10px; }")
        super().showPopup()
        # Leave room for the rounded frame instead of clipping the last row.
        if self.count() <= self.maxVisibleItems():
            available = popup.screen().availableGeometry()
            height = min(sum(view.sizeHintForRow(row) for row in range(self.count())) + 12,
                         available.height())
            popup.resize(popup.width(), height)
            if popup.geometry().bottom() > available.bottom():
                popup.move(popup.x(), available.bottom() - height + 1)
