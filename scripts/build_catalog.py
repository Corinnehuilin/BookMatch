"""Build a compact, ranked catalog from Open Library's monthly bulk dumps.

The source dumps stay in the ignored .catalog-source folder. Only aggregate
read counts and a small set of work metadata enter data/catalog.json.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / ".catalog-source"
OUTPUT = ROOT / "data" / "catalog.json"
WORK_KEY = re.compile(r"^/works/OL\d+W$")
YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
MAX_CANDIDATES = 40_000
CATALOG_SIZE = 20_000


def read_counts(path: Path) -> list[tuple[str, int]]:
    counts: Counter[str] = Counter()
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            parts = line.rstrip("\n").split("\t", 3)
            if len(parts) == 4 and parts[2] == "Already Read" and WORK_KEY.fullmatch(parts[0]):
                counts[parts[0]] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:MAX_CANDIDATES]


def work_authors(work: dict) -> list[str]:
    keys: list[str] = []
    entries = work.get("authors") or []
    if not isinstance(entries, list):
        return keys
    for entry in entries[:3]:
        if not isinstance(entry, dict):
            continue
        author = entry.get("author")
        key = author.get("key") if isinstance(author, dict) else entry.get("key")
        if isinstance(key, str) and key.startswith("/authors/"):
            keys.append(key)
    return keys


def selected_records(path: Path, wanted: set[str]) -> dict[str, dict]:
    works: dict[str, dict] = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            parts = line.split("\t", 4)
            if len(parts) != 5 or parts[1] not in wanted:
                continue
            try:
                work = json.loads(parts[4])
            except json.JSONDecodeError:
                continue
            if not isinstance(work, dict):
                continue
            title = work.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            author_keys = work_authors(work)
            if not author_keys:
                continue
            raw_subjects = work.get("subjects")
            if not isinstance(raw_subjects, list):
                raw_subjects = []
            subjects = [value.strip() for value in raw_subjects
                        if isinstance(value, str) and 2 <= len(value.strip()) <= 70]
            date = work.get("first_publish_date") or ""
            year_match = YEAR.search(date) if isinstance(date, str) else None
            works[parts[1]] = {
                "title": title.strip(),
                "author_keys": author_keys,
                "subjects": list(dict.fromkeys(subjects))[:24],
                "publication_year": int(year_match.group(1)) if year_match else None,
            }
    return works


def author_names(path: Path, wanted: set[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        for line in stream:
            parts = line.split("\t", 4)
            if len(parts) != 5 or parts[1] not in wanted:
                continue
            try:
                record = json.loads(parts[4])
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            value = record.get("name")
            if isinstance(value, str) and value.strip():
                names[parts[1]] = value.strip()
    return names


def build(snapshot: str) -> list[dict]:
    ranked = read_counts(SOURCE / "reading-log.txt.gz")
    print(f"Ranked {len(ranked):,} candidate works", flush=True)
    works = selected_records(SOURCE / "works.txt.gz", {key for key, _ in ranked})
    print(f"Found metadata for {len(works):,} works", flush=True)
    names = author_names(SOURCE / "authors.txt.gz", {
        key for work in works.values() for key in work["author_keys"]
    })
    print(f"Found {len(names):,} author names", flush=True)
    books: list[dict] = []
    for key, count in ranked:
        work = works.get(key)
        if not work:
            continue
        authors = [names[author_key] for author_key in work["author_keys"] if author_key in names]
        if not authors:
            continue
        books.append({
            "id": key.removeprefix("/works/"),
            "title": work["title"],
            "author": ", ".join(authors),
            "genre": "",
            "subjects": work["subjects"],
            "publication_year": work["publication_year"],
            "read_count": count,
            "rank": len(books) + 1,
            "url": "https://openlibrary.org" + key,
        })
        if len(books) == CATALOG_SIZE:
            break
    if len(books) != CATALOG_SIZE:
        raise RuntimeError(f"Only {len(books):,} complete records; need {CATALOG_SIZE:,}")
    serialized = json.dumps(books, ensure_ascii=False, separators=(",", ":"))
    payload = {
        "source": "Open Library monthly data dumps",
        "ranking": "Already Read reading-log entries per work, descending",
        "snapshot": snapshot,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "catalog_revision": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "books": books,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Saved {len(books):,} ranked works to {OUTPUT}", flush=True)
    return books


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", default="2026-08-31")
    arguments = parser.parse_args()
    build(arguments.snapshot)
