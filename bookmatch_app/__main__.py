"""Launch BookMatch."""

import sys
import sqlite3

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .messages import MessageBox as QMessageBox
from . import __version__

from .storage import LibraryStore
from .ui import BookMatchWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("BookMatch")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("BookMatch")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f7f5ef"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#26332e"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#fffefa"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#26332e"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#edf2eb"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#26332e"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#d5e3d5"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#234e3b"))
    app.setPalette(palette)
    try:
        store = LibraryStore()
    except (OSError, RuntimeError, sqlite3.Error) as error:
        QMessageBox.critical(None, "BookMatch could not open", f"Could not open your local library:\n{error}")
        return 1
    window = BookMatchWindow(store)
    if "--self-test" in sys.argv or "--self-test-model" in sys.argv:
        window.show()
        app.processEvents()
        for index in range(len(window.PAGES)):
            window.navigate(index)
            app.processEvents()
        if store.catalog_count() != 20_000:
            window.close()
            return 2
        if "--self-test-model" in sys.argv:
            from .recommend import recommend
            matches, mode, _ = recommend("eerie friendships but no violence",
                                         store.discovery_books(), store.directory,
                                         catalog_books=store.catalog_books(),
                                         catalog_revision=store.catalog_revision())
            if mode != "Local semantic model" or not matches:
                window.close()
                return 3
        window.close()
        return 0
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
