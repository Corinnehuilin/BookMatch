"""Render a dark-mode design proposal without changing the installed app.

Uses a temporary synthetic library, bundled public metadata, and existing public
cover-cache images. Downloads are disabled. Run with QT_QPA_PLATFORM=offscreen.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

os.environ["BOOKMATCH_DISABLE_COVER_DOWNLOADS"] = "1"

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPixmap
from PySide6.QtWidgets import QApplication, QPlainTextEdit

from bookmatch_app import dialogs, ui, widgets
from bookmatch_app.recommend import recommend
from bookmatch_app.storage import LibraryStore, data_directory


COLORS = {
    "#f7f5ef": "#151d19", "#26332e": "#e5ebe4", "#fffefa": "#202b25",
    "#edf2eb": "#293b30", "#315c47": "#b6d6bd", "#d5e1d3": "#405647",
    "#e2ecdf": "#354c3d", "#5a8569": "#85af91", "#eeeee9": "#242d27",
    "#a0a79f": "#64746a", "#dedfd8": "#344238", "#e9ede5": "#1c2821",
    "#d9dfd5": "#33453a", "#284b3f": "#deebe0", "#73837a": "#a1b7a8",
    "#233a30": "#edf1e8", "#263b31": "#e3ebe1", "#69756d": "#a8b8ac",
    "#4b6054": "#a9bdad", "#dfe7dc": "#2d4033", "#d5e3d5": "#304b39",
    "#234e3b": "#d8eadc", "#254b39": "#4e7c60", "#f8eeea": "#392a27",
    "#8a3f35": "#e5afa2", "#e6c9c1": "#66443a", "#f1ded8": "#50352e",
    "#e8e7dd": "#344238", "#dce6d7": "#294133", "#d4dfcf": "#3a5943",
    "#f2ebdc": "#302d24", "#e8dec9": "#4b4431", "#d9e0d6": "#3e5144",
    "#dde5d9": "#3a4c3d", "#c3cec0": "#536b59", "#94ab96": "#8daf94",
    "#e9eee8": "#253129", "#5e6d63": "#b0c0b3", "#cfdbcf": "#3c5040",
    "#87928b": "#94a79a", "#647167": "#a8b8ac", "#a87b31": "#d5af67",
    "#dcebdc": "#354c3d", "#315c47:selected": "#416c52",
}


def dark_style(style: str) -> str:
    # One substitution pass avoids replacing colors introduced by the mapping.
    import re
    return re.sub(r"#[0-9a-fA-F]{6}", lambda match: COLORS.get(match[0].lower(), match[0]), style)


def settle(app):
    for _ in range(8):
        app.processEvents()


def framed_capture(widget, output: Path, title: str, app):
    settle(app)
    body = widget.grab()
    ratio = body.devicePixelRatio()
    width, height = widget.width(), widget.height() + 42
    canvas = QPixmap(round(width * ratio), round(height * ratio))
    canvas.setDevicePixelRatio(ratio)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), 14, 14)
    painter.setClipPath(path)
    painter.fillRect(0, 0, width, height, QColor("#151d19"))
    painter.fillRect(0, 0, width, 42, QColor("#222c25"))
    for x, color in ((20, "#ff6059"), (42, "#ffbd2d"), (64, "#28c840")):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(x - 6, 15, 12, 12)
    painter.setFont(QFont("Avenir Next", 12, QFont.Weight.DemiBold))
    painter.setPen(QColor("#bac9bd"))
    painter.drawText(90, 0, width - 110, 42, Qt.AlignmentFlag.AlignVCenter, title)
    painter.drawPixmap(0, 42, body)
    painter.end()
    canvas.save(str(output))


def main():
    app = QApplication([])
    app.setApplicationName("BookMatch")
    app.setOrganizationName("BookMatch")
    public_covers = data_directory() / "covers"
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, "#151d19"),
                        (QPalette.ColorRole.WindowText, "#e5ebe4"),
                        (QPalette.ColorRole.Base, "#202b25"),
                        (QPalette.ColorRole.Text, "#e5ebe4"),
                        (QPalette.ColorRole.Button, "#293b30"),
                        (QPalette.ColorRole.ButtonText, "#b6d6bd"),
                        (QPalette.ColorRole.PlaceholderText, "#94a79a"),
                        (QPalette.ColorRole.Highlight, "#416c52"),
                        (QPalette.ColorRole.HighlightedText, "#ffffff")):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    ui.STYLE = dark_style(ui.STYLE) + """
        QPushButton#primary, QPushButton#pageNumber[current="true"] {
            background: #416c52; color: #ffffff; border-color: #416c52;
        }
        QPushButton#primary:hover { background: #4e7c60; }
        QPlainTextEdit { selection-background-color: #416c52; selection-color: white; }
    """
    dialogs.PUBLIC_FIELD_STYLE = dark_style(dialogs.PUBLIC_FIELD_STYLE)
    real_color = QColor

    def mapped_color(value, *args):
        return real_color(COLORS.get(value, value) if isinstance(value, str) else value, *args)

    widgets.QColor = mapped_color
    dialogs.QColor = mapped_color
    for name, color in (("NORMAL_BG", "#202b25"), ("NORMAL_TEXT", "#e5ebe4"),
                        ("HOVER_BG", "#354c3d"), ("HOVER_TEXT", "#d8eadc"),
                        ("SELECTED_BG", "#416c52"), ("SELECTED_TEXT", "#ffffff")):
        setattr(widgets, name, real_color(color))
    output = Path(__file__).resolve().parent.parent / "mockups" / "dark-mode"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bookmatch-dark-proposal-") as folder:
        store = LibraryStore(Path(folder))
        catalog = store.catalog_books()
        for book, status, rating in (("OL5738147W", "Read", 4.25),
                                     ("OL262150W", "Currently Reading", None),
                                     (catalog[0]["id"], "Want to Read", None)):
            if store.book(book):
                store.set_status(book, status)
                store.update_entry(book, status=status, rating=rating, notes="", review="",
                                   started_on=None, finished_on="2026-09-20" if rating else None)
        store.add_goal("A year of good books", "2026-01-01", "2026-12-31", 24)
        cover_ids = json.loads((Path(__file__).resolve().parent.parent / "data" / "cover_ids.json").read_text())
        destination = store.directory / "covers"
        destination.mkdir()
        # Copy only public cover artwork, never the real user's database or notes.
        for book in catalog[:200] + store.library_books():
            cover_id = cover_ids.get(book["id"])
            source = public_covers / f"{cover_id}-M.jpg"
            if source.is_file():
                shutil.copyfile(source, destination / source.name)
        cache = store.directory / "metadata-cache"
        cache.mkdir()
        for book in store.library_books():
            (cache / f"{book['id']}.json").write_text(json.dumps({"work_id": book["id"], "description": ""}))
        window = ui.BookMatchWindow(store)
        window.resize(1180, 820)
        window.show()
        settle(app)
        window.findChild(QPlainTextEdit).clearFocus()
        framed_capture(window, output / "home.png", "BookMatch — Home · Dark mode concept", app)
        window.navigate(1)
        framed_capture(window, output / "my-library.png", "BookMatch — My Library · Dark mode concept", app)
        window.navigate(4)
        framed_capture(window, output / "catalog.png", "BookMatch — Catalog · Dark mode concept", app)
        window._discovery_query = window._discovery_draft = "Fantasy and friendship, but no graphic violence"
        matches, mode, prefs = recommend(window._discovery_query, store.discovery_books(), store.directory, limit=None)
        window._show_discovery_results(matches, mode, prefs)
        settle(app)
        window.stack.widget(2).verticalScrollBar().setValue(280)
        framed_capture(window, output / "discover.png", "BookMatch — Discover · Dark mode concept", app)
        details = dialogs.BookDetailsDialog(store, "OL5738147W", window)
        details.show()
        framed_capture(details, output / "book-details.png", "BookMatch — Book details · Dark mode concept", app)
        details.close()
        shelf = dialogs.ShelfDialog("Elantris", "Read", window, store=store)
        shelf.show()
        settle(app)
        shelf.shelf.showPopup()
        popup = shelf.shelf.view().window()
        popup.setStyleSheet(dark_style(popup.styleSheet()))
        shelf.shelf.view()._set_hovered(1, animate=False)
        settle(app)
        popup.grab().save(str(output / "dropdown.png"))
        shelf.shelf.hidePopup()
        shelf.close()
        window.close()
    # A compact overview; full-resolution screenshots are saved separately.
    overview = QPixmap(1600, 1240)
    overview.fill(QColor("#111813"))
    painter = QPainter(overview)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    painter.setFont(QFont("Avenir Next", 18, QFont.Weight.DemiBold))
    for index, (file, title) in enumerate((("home", "Home"), ("my-library", "My Library"),
                                          ("catalog", "Catalog"), ("discover", "Discover"))):
        x, y = 20 + (index % 2) * 800, 15 + (index // 2) * 620
        painter.setPen(QColor("#bac9bd"))
        painter.drawText(x, y + 24, title)
        picture = QPixmap(str(output / f"{file}.png"))
        picture.setDevicePixelRatio(1)
        picture = picture.scaled(760, 570, Qt.AspectRatioMode.KeepAspectRatio,
                                  Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(x, y + 40, picture)
    painter.end()
    overview.save(str(output / "overview.png"))
    print(f"Saved seven dark-mode proposal images to {output}")


if __name__ == "__main__":
    main()
