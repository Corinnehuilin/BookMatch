"""Cache selected medium covers from Archive.org's public cover archives.

This uses Archive.org's archived ZIP members, never Open Library's display API.
It is resumable: valid covers already present in BookMatch's private cache are skipped.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QImage

from bookmatch_app.storage import data_directory

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
COVER_IDS = ROOT / "data" / "cover_ids.json"
MAX_BYTES = 2_000_000
MAX_TOTAL_BYTES = 2_800_000_000  # Leaves room below the owner's 3 GB transfer limit.
BATCH_SIZE = 40
UNAVAILABLE_GROUPS = {7, 15}


def archive_url(cover_id: int) -> str:
    if type(cover_id) is not int or cover_id <= 0:
        raise ValueError("Expected a positive public cover ID")
    group = cover_id // 1_000_000
    shard = (cover_id % 1_000_000) // 10_000
    extension = "tar" if group in (0, 6) else "zip"
    return (f"https://archive.org/download/m_covers_{group:04d}/"
            f"m_covers_{group:04d}_{shard:02d}.{extension}/{cover_id:010d}-M.jpg")


def valid_cover(raw: bytes) -> bool:
    if not (100 < len(raw) <= MAX_BYTES and raw.startswith(b"\xff\xd8")):
        return False
    image = QImage.fromData(raw)
    return not image.isNull() and 1 < image.width() <= 2000 and 1 < image.height() <= 3000


def download_one(cover_id: int, destination: Path) -> tuple[int, str, int]:
    path = destination / f"{cover_id}-M.jpg"
    if path.is_file() and valid_cover(path.read_bytes()):
        return cover_id, "cached", path.stat().st_size
    if cover_id // 1_000_000 in UNAVAILABLE_GROUPS:
        return cover_id, "archive group unavailable", 0
    request = Request(archive_url(cover_id), headers={
        "User-Agent": "BookMatch/0.2.5 (personal offline cover cache)",
        "Accept": "image/jpeg",
    })
    for attempt in range(3):
        try:
            with urlopen(request, timeout=40) as response:
                raw = response.read(MAX_BYTES + 1)
            if not valid_cover(raw):
                return cover_id, "invalid image", len(raw)
            temporary = path.with_suffix(".jpg.tmp")
            temporary.write_bytes(raw)
            temporary.replace(path)
            return cover_id, "downloaded", len(raw)
        except HTTPError as error:
            if error.code in (400, 403, 404):
                return cover_id, f"unavailable ({error.code})", 0
            reason = f"HTTP {error.code}"
        except (URLError, TimeoutError, OSError) as error:
            reason = str(error)
        if attempt < 2:
            time.sleep(2 ** attempt)
    return cover_id, f"failed ({reason})", 0


def main() -> None:
    QCoreApplication.setApplicationName("BookMatch")
    QCoreApplication.setOrganizationName("BookMatch")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=data_directory() / "covers")
    parser.add_argument("--limit", type=int, default=0, help="Only process this many ranked covers")
    parser.add_argument("--workers", type=int, choices=(1, 2), default=2)
    parser.add_argument("--max-total-mb", type=int, default=2800,
                        help="Stop before this many MB of images are cached (default 2800)")
    arguments = parser.parse_args()
    cover_ids = json.loads(COVER_IDS.read_text(encoding="utf-8"))
    ranked = json.loads(CATALOG.read_text(encoding="utf-8"))["books"]
    selected = [cover_ids[book["id"]] for book in ranked if book["id"] in cover_ids]
    if arguments.limit:
        selected = selected[:arguments.limit]
    destination = arguments.output.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    max_total_bytes = min(arguments.max_total_mb * 1_000_000, MAX_TOTAL_BYTES)
    bytes_present = sum(path.stat().st_size for path in destination.glob("*-M.jpg"))
    bytes_counted = bytes_present
    print(f"Checking {len(selected):,} public covers for {destination}", flush=True)
    print(f"Cover payload limit: {max_total_bytes / 1_000_000:.0f} MB; "
          f"already cached: {bytes_present / 1_000_000:.1f} MB", flush=True)
    counts: dict[str, int] = {}
    bytes_downloaded = 0
    processed = 0
    with ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        for start in range(0, len(selected), BATCH_SIZE):
            batch = selected[start:start + BATCH_SIZE]
            # Reserve the maximum possible image payload for every request in
            # the batch, so concurrent requests cannot pass the transfer cap.
            if bytes_counted + len(batch) * MAX_BYTES > max_total_bytes:
                print("Stopped before the cover download limit.", flush=True)
                break
            futures = [pool.submit(download_one, cover_id, destination) for cover_id in batch]
            for future in as_completed(futures):
                _cover_id, outcome, size = future.result()
                counts[outcome] = counts.get(outcome, 0) + 1
                if outcome == "downloaded":
                    bytes_downloaded += size
                    bytes_counted += size
                elif outcome == "invalid image":
                    bytes_counted += size
                processed += 1
            if processed % 200 == 0 or processed == len(selected):
                print(f"{processed:,}/{len(selected):,} checked; "
                      f"{counts.get('downloaded', 0):,} new, {counts.get('cached', 0):,} cached, "
                      f"{bytes_downloaded / 1_000_000:.1f} MB downloaded", flush=True)
    print("Results:", json.dumps(counts, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
