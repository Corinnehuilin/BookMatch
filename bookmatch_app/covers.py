"""Load public Open Library covers only when a visible card needs one."""

from __future__ import annotations

import json
import os
import sys
from collections import deque
from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import QLabel
from shiboken6 import isValid
from . import __version__

COVER_IDS_PATH = Path(__file__).resolve().parent.parent / "data" / "cover_ids.json"
MAX_IMAGE_BYTES = 2_000_000


class CoverCache:
    def __init__(self, directory: Path):
        self.directory = directory / "covers"
        self.ids = json.loads(COVER_IDS_PATH.read_text(encoding="utf-8")) if COVER_IDS_PATH.exists() else {}
        self.network = QNetworkAccessManager()
        self.pending: dict[int, list[CoverLabel]] = {}
        self.queue: deque[int] = deque()
        self.active = 0
        self.failed: set[int] = set()
        self.download_enabled = not (os.environ.get("BOOKMATCH_DISABLE_COVER_DOWNLOADS") or
                                     "--self-test" in sys.argv or "--self-test-model" in sys.argv)

    def request(self, book_id: str, target: "CoverLabel") -> None:
        cover_id = self.ids.get(book_id)
        if type(cover_id) is not int or cover_id <= 0:
            return
        cached = self.directory / f"{cover_id}-M.jpg"
        if cached.is_file():
            image = QPixmap(str(cached))
            if not image.isNull():
                target.show_cover(image)
                return
        if not self.download_enabled or cover_id in self.failed:
            return
        if cover_id in self.pending:
            self.pending[cover_id].append(target)
            return
        self.pending[cover_id] = [target]
        self.queue.append(cover_id)
        self._pump()

    def _pump(self) -> None:
        while self.active < 2 and self.queue:
            cover_id = self.queue.popleft()
            targets = self.pending.get(cover_id, [])
            if not any(isValid(target) and target.isVisible() for target in targets):
                self.pending.pop(cover_id, None)
                continue
            cached = self.directory / f"{cover_id}-M.jpg"
            url = QUrl(f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg?default=false")
            request = QNetworkRequest(url)
            request.setRawHeader(b"User-Agent", f"BookMatch/{__version__} (local desktop cover display)".encode())
            request.setTransferTimeout(10_000)
            reply = self.network.get(request)
            self.active += 1
            reply.finished.connect(lambda cid=cover_id, path=cached, response=reply:
                                   self._finished(cid, path, response))

    def _finished(self, cover_id: int, cached: Path, reply: QNetworkReply) -> None:
        targets = self.pending.pop(cover_id, [])
        image = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            raw = bytes(reply.readAll())
            if len(raw) <= MAX_IMAGE_BYTES and image.loadFromData(raw) and 1 < image.width() <= 2000 and 1 < image.height() <= 3000:
                try:
                    self.directory.mkdir(parents=True, exist_ok=True)
                    temporary = cached.with_suffix(".jpg.tmp")
                    temporary.write_bytes(raw)
                    temporary.replace(cached)
                except OSError:
                    pass
        reply.deleteLater()
        self.active -= 1
        if image.isNull():
            self.failed.add(cover_id)
            self._pump()
            return
        for target in targets:
            if isValid(target):
                target.show_cover(image)
        self._pump()


class CoverLabel(QLabel):
    def __init__(self, book_id: str, placeholder: QPixmap, cache: CoverCache):
        super().__init__()
        self.book_id = book_id
        self.cache = cache
        self._requested = False
        self.setPixmap(placeholder)
        self.setFixedSize(placeholder.size())
        self.setAccessibleName(f"Cover for {book_id}")

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._requested:
            self._requested = True
            self.cache.request(self.book_id, self)

    def show_cover(self, image: QPixmap) -> None:
        canvas = QPixmap(self.size())
        canvas.fill(Qt.GlobalColor.white)
        scaled = image.scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        painter = QPainter(canvas)
        painter.drawPixmap((canvas.width() - scaled.width()) // 2,
                           (canvas.height() - scaled.height()) // 2, scaled)
        painter.end()
        self.setPixmap(canvas)
