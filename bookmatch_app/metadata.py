"""Optional, low-volume Open Library work lookup by public work ID only."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .storage import CATALOG_PATH
from . import __version__

WORK_ID = re.compile(r"OL\d+W\Z")
YEAR = re.compile(r"\b(1[4-9]\d\d|20\d\d)\b")
BASE = "https://openlibrary.org/works/"
USER_AGENT = f"BookMatch/{__version__} (local desktop book lookup)"
MAX_RESPONSE = 2_000_000


@lru_cache(maxsize=1)
def _public_catalog_index() -> dict[str, dict]:
    """Keep original public values separate from editable library records."""
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {book["id"]: book for book in catalog["books"]}


def public_catalog_book(work_id: str) -> dict | None:
    return _public_catalog_index().get(work_id) if WORK_ID.fullmatch(work_id) else None


def public_field_locks(book: dict, cached: dict | None = None) -> dict[str, bool]:
    """Lock values only when they still match a known public source."""
    fields = ("title", "author", "genre", "description", "publication_year")
    unlocked = dict.fromkeys(fields, False)
    if book.get("source") != "openlibrary":
        return unlocked
    public = public_catalog_book(book.get("id", ""))
    if public is None:
        return unlocked
    cached = cached or {}

    def matches(value: object, choices: tuple[object, ...]) -> bool:
        normalized = str(value or "").strip().casefold()
        return bool(normalized and any(
            normalized == str(choice).strip().casefold() for choice in choices if choice))

    return {
        "title": matches(book.get("title"), (public.get("title"),)),
        "author": matches(book.get("author"), (public.get("author"),)),
        "genre": matches(book.get("genre"), (
            public.get("genre"), genre_from_subjects(public.get("subjects")),
            cached.get("genre"))),
        "description": matches(book.get("description"), (cached.get("description"),)),
        "publication_year": matches(book.get("publication_year"), (
            public.get("publication_year"), cached.get("publication_year"))),
    }
GENRE_PATTERNS = (
    ("Self-help", r"\bself[- ]help\b|\bpersonal growth\b"),
    ("Science fiction", r"\bscience fiction\b|\bsci[- ]fi\b"),
    ("Historical fiction", r"\bhistorical fiction\b"),
    ("Literary fiction", r"\bliterary fiction\b"),
    ("Fantasy", r"\bfantasy\b"),
    ("Mystery", r"\bmyster(?:y|ies)\b|\bdetective fiction\b"),
    ("Thriller", r"\bthriller\b|\bsuspense fiction\b"),
    ("Horror", r"\bhorror\b"),
    ("Romance", r"\bromance\b|\blove stories\b"),
    ("Memoir", r"\bmemoirs?\b|\bautobiograph(?:y|ies)\b"),
    ("Biography", r"\bbiograph(?:y|ies)\b"),
    ("History", r"\bhistory\b"),
    ("Psychology", r"\bpsychology\b"),
    ("Business", r"\bbusiness\b|\bentrepreneurship\b"),
    ("Poetry", r"\bpoetry\b|\bpoems\b"),
)


def genre_from_subjects(subjects: str | list[str] | None) -> str:
    """Suggest a broad genre only when public subject tags state one clearly."""
    tags = subjects.split(", ") if isinstance(subjects, str) else subjects or []
    for genre, pattern in GENRE_PATTERNS:
        if any(isinstance(tag, str) and re.search(pattern, tag, re.IGNORECASE)
               for tag in tags):
            return genre
    return ""


def cached_work_metadata(work_id: str, directory: Path) -> dict | None:
    if not WORK_ID.fullmatch(work_id):
        return None
    cache = directory / "metadata-cache" / f"{work_id}.json"
    if cache.is_file():
        try:
            value = json.loads(cache.read_text(encoding="utf-8"))
            if (isinstance(value, dict) and value.get("work_id") == work_id
                    and isinstance(value.get("description", ""), str)
                    and isinstance(value.get("genre", ""), str)):
                return value
        except (OSError, ValueError):
            pass
    return None


def _cache_work_metadata(work_id: str, directory: Path, result: dict) -> None:
    cache = directory / "metadata-cache" / f"{work_id}.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    temporary.replace(cache)


def _read_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=12) as response:
            raw = response.read(MAX_RESPONSE + 1)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError(f"Open Library is unavailable: {error}") from error
    if len(raw) > MAX_RESPONSE:
        raise ValueError("Open Library returned more metadata than BookMatch can display")
    try:
        value = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Open Library returned unreadable metadata") from error
    if not isinstance(value, dict):
        raise ValueError("Open Library returned an unexpected response")
    return value


def _description(value: object) -> str:
    if isinstance(value, dict):
        value = value.get("value")
    return value.strip()[:12_000] if isinstance(value, str) else ""


def _year(value: object) -> int | None:
    match = YEAR.search(value) if isinstance(value, str) else None
    return int(match.group(1)) if match else None


def fetch_work_summary(work_id: str, directory: Path) -> dict:
    """Fetch one public work for its description and subject-based genre."""
    if not WORK_ID.fullmatch(work_id):
        raise ValueError("Choose a catalog book before looking up details")
    cached = cached_work_metadata(work_id, directory)
    if cached is not None:
        return cached
    work = _read_json(BASE + work_id + ".json")
    subjects = [tag.strip() for tag in work.get("subjects", [])
                if isinstance(tag, str) and tag.strip()] if isinstance(work.get("subjects"), list) else []
    result = {
        "work_id": work_id,
        "description": _description(work.get("description")),
        "genre": genre_from_subjects(subjects),
        "publication_year": _year(work.get("first_publish_date")),
    }
    _cache_work_metadata(work_id, directory, result)
    return result
