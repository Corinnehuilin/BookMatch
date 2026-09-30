"""Local Goodreads CSV import and portable JSON export."""

from __future__ import annotations

import csv
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .storage import LibraryStore

REQUIRED_COLUMNS = {"Book Id", "Title", "Author"}


def _number(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    number = int(float(value))
    return number if number > 0 else None


def _rating(value: str) -> float | None:
    value = value.strip()
    if not value or value in ("0", "0.0"):
        return None
    number = float(value)
    if number < 0.25 or number > 5 or number * 4 != int(number * 4):
        raise ValueError("rating must be between 0.25 and 5 in quarter-star steps")
    return number


def _date(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    for format_string in ("%Y/%m/%d", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, format_string).date().isoformat()
        except ValueError:
            continue
    raise ValueError("date is not in a recognized format")


def _status(shelf: str) -> str:
    normalized = shelf.strip().casefold().replace("_", "-")
    return {
        "read": "Read",
        "currently-reading": "Currently Reading",
        "to-read": "Want to Read",
        "want-to-read": "Want to Read",
        "did-not-finish": "Did Not Finish",
        "dnf": "Did Not Finish",
    }.get(normalized, "Want to Read")


@dataclass
class ImportPreview:
    rows: list[dict]
    errors: list[str]
    file_name: str
    shelves: list[dict] | None = None
    goals: list[dict] | None = None
    goal_books: list[dict] | None = None

    @property
    def valid_count(self) -> int:
        return len(self.rows)


def parse_goodreads_csv(path: Path) -> ImportPreview:
    if path.stat().st_size > 20_000_000:
        raise ValueError("The CSV is larger than the 20 MB import limit")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not REQUIRED_COLUMNS.issubset(set(reader.fieldnames)):
            raise ValueError("This is not a Goodreads library export: Book Id, Title, and Author are required")
        rows: list[dict] = []
        errors: list[str] = []
        seen_ids: set[str] = set()
        for line, raw in enumerate(reader, start=2):
            try:
                book_id = (raw.get("Book Id") or "").strip()
                title = (raw.get("Title") or "").strip()
                author = (raw.get("Author") or "").strip()
                if not book_id or not title or not author:
                    raise ValueError("Book Id, Title, or Author is missing")
                if book_id in seen_ids:
                    raise ValueError("duplicate Goodreads Book Id in file")
                seen_ids.add(book_id)
                shelf = (raw.get("Exclusive Shelf") or "to-read").strip()
                year = _number(raw.get("Original Publication Year") or raw.get("Year Published") or "")
                if year is not None and year > 3000:
                    raise ValueError("publication year must be between 1 and 3000")
                rows.append({
                    "goodreads_id": book_id, "title": title, "author": author,
                    "publication_year": year,
                    "rating": _rating(raw.get("My Rating") or ""),
                    "status": _status(shelf), "source_shelf": shelf,
                    "shelves": (raw.get("Bookshelves") or "").strip(),
                    "review": (raw.get("My Review") or "").strip(),
                    "notes": (raw.get("Private Notes") or "").strip(),
                    "finished_on": _date(raw.get("Date Read") or ""),
                })
            except (ValueError, TypeError, OverflowError) as error:
                errors.append(f"Row {line}: {error}")
    return ImportPreview(rows, errors, path.name)


def import_goodreads(store: LibraryStore, preview: ImportPreview) -> dict[str, int]:
    added = skipped = 0
    with store.connection:
        for row in preview.rows:
            linked = store.connection.execute(
                "SELECT book_id FROM goodreads_links WHERE goodreads_id = ?",
                (row["goodreads_id"],),
            ).fetchone()
            existing = linked or store.connection.execute(
                """SELECT id FROM books WHERE lower(trim(title)) = lower(?)
                   AND lower(trim(author)) = lower(?) LIMIT 1""",
                (row["title"], row["author"]),
            ).fetchone()
            if existing:
                book_id = existing["book_id"] if linked else existing["id"]
            else:
                book_id = f"goodreads-{row['goodreads_id']}"
                store.connection.execute(
                    """INSERT INTO books (id, title, author, publication_year,
                                          source, source_id)
                       VALUES (?, ?, ?, ?, 'goodreads', ?)""",
                    (book_id, row["title"], row["author"],
                     row["publication_year"], row["goodreads_id"]),
                )
            if not linked:
                store.connection.execute(
                    "INSERT INTO goodreads_links (goodreads_id, book_id) VALUES (?, ?)",
                    (row["goodreads_id"], book_id),
                )
            present = store.connection.execute(
                "SELECT 1 FROM library_entries WHERE book_id = ?", (book_id,)
            ).fetchone()
            if present:
                skipped += 1
                continue
            store.connection.execute(
                """INSERT INTO library_entries
                   (book_id, status, rating, notes, review, finished_on, source_shelf, shelves)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (book_id, row["status"], row["rating"], row["notes"],
                 row["review"], row["finished_on"], row["source_shelf"], row["shelves"]),
            )
            added += 1
    return {"added": added, "skipped": skipped, "invalid": len(preview.errors)}


def export_library(store: LibraryStore, path: Path) -> int:
    books = store.library_books()
    goals = store.goals()
    owned = {book["id"] for book in books}
    selected = {book_id for goal in goals for book_id in goal["book_ids"]}
    # Keep metadata for selected books removed from the library, without adding
    # them back to the library on restore.
    goal_books = [store.book(book_id) for book_id in sorted(selected - owned)]
    payload = {"format": "bookmatch-library", "version": 1, "books": books,
               "shelves": store.shelf_definitions(), "goals": goals,
               "goal_book_details": [book for book in goal_books if book]}
    # Replace only after the full new backup has been written successfully.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".bookmatch-backup-", suffix=".tmp",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return len(books)


def _validated_book_metadata(row: dict) -> dict:
    value = dict(row)
    for field in ("id", "title", "author"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValueError(f"{field} is missing")
        value[field] = value[field].strip()
    for field in ("description", "genre", "source", "source_id", "subjects", "source_url",
                  "notes", "review", "source_shelf", "shelves"):
        if value.get(field) is not None and not isinstance(value[field], str):
            raise ValueError(f"{field} must be text")
    year = value.get("publication_year")
    if year is not None and (type(year) is not int or not 1 <= year <= 3000):
        raise ValueError("publication year is invalid")
    return value


def parse_bookmatch_json(path: Path) -> ImportPreview:
    if path.stat().st_size > 20_000_000:
        raise ValueError("The JSON is larger than the 20 MB import limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("format") != "bookmatch-library" or payload.get("version") != 1:
        raise ValueError("This is not a supported BookMatch library export")
    source_rows = payload.get("books")
    if not isinstance(source_rows, list):
        raise ValueError("The export has no books list")
    rows: list[dict] = []
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(source_rows, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("book is not an object")
            row = _validated_book_metadata(row)
            book_id = row.get("id")
            title = row.get("title")
            author = row.get("author")
            status = row.get("status")
            if not all(isinstance(value, str) and value.strip() for value in (book_id, title, author, status)):
                raise ValueError("id, title, author, or status is missing")
            if status not in ("Want to Read", "Currently Reading", "Read", "Did Not Finish"):
                raise ValueError("reading status is not recognized")
            if book_id in seen:
                raise ValueError("duplicate book ID")
            seen.add(book_id)
            rating = row.get("rating")
            if rating is not None and (type(rating) not in (int, float) or
                                       rating < 0.25 or rating > 5 or rating * 4 != int(rating * 4)):
                raise ValueError("rating is invalid")
            for field in ("started_on", "finished_on"):
                if row.get(field) is not None and not isinstance(row[field], str):
                    raise ValueError(f"{field} must be a date")
                row[field] = _date(row.get(field) or "")
            if row["started_on"] and row["finished_on"] and row["finished_on"] < row["started_on"]:
                raise ValueError("finished date is before started date")
            rows.append(row)
        except (ValueError, OverflowError) as error:
            errors.append(f"Book {index}: {error}")
    definitions = payload.get("shelves", [])
    if not isinstance(definitions, list):
        raise ValueError("The shelves list is invalid")
    valid_shelves = []
    for shelf in definitions:
        if (not isinstance(shelf, dict) or not isinstance(shelf.get("name"), str)
                or not 1 <= len(shelf["name"].strip()) <= 60 or "," in shelf["name"]):
            errors.append("A shelf has an invalid name")
            continue
        valid_shelves.append({"name": shelf["name"].strip(),
                              "home_collapsed": bool(shelf.get("home_collapsed", 1)),
                              "library_collapsed": bool(shelf.get("library_collapsed", 1))})
    goals = payload.get("goals", [])
    if not isinstance(goals, list):
        raise ValueError("The goals list is invalid")
    valid_goals = []
    for index, goal in enumerate(goals, start=1):
        try:
            if not isinstance(goal, dict) or not isinstance(goal.get("label"), str) or not goal["label"].strip():
                raise ValueError("a goal name is required")
            start = _date(goal["start_on"])
            end = _date(goal["end_on"])
            target = goal["target_books"]
            if not start or not end or start > end or type(target) is not int or not 1 <= target <= 2**31 - 1:
                raise ValueError("dates or book target are invalid")
            scope = goal.get("scope", "all")
            book_ids = goal.get("book_ids", [])
            if scope not in ("all", "selected") or not isinstance(book_ids, list) or any(
                    not isinstance(book_id, str) or not book_id.strip() for book_id in book_ids):
                raise ValueError("the book selection is invalid")
            valid_goals.append({"label": goal["label"].strip(), "start_on": start,
                                "end_on": end, "target_books": target, "scope": scope,
                                "book_ids": sorted(set(book_ids)) if scope == "selected" else []})
        except (KeyError, TypeError, AttributeError, ValueError) as error:
            errors.append(f"Goal {index}: {error}")
    extra_books = payload.get("goal_book_details", [])
    if not isinstance(extra_books, list):
        raise ValueError("The goal book details list is invalid")
    valid_extra_books = []
    for book in extra_books:
        try:
            if not isinstance(book, dict):
                raise ValueError("a goal book must be an object")
            book = _validated_book_metadata(book)
        except ValueError:
            errors.append("A goal book has invalid details")
            continue
        valid_extra_books.append(book)
    return ImportPreview(rows, errors, path.name, valid_shelves, valid_goals, valid_extra_books)


def _goal_signature(goal: dict) -> tuple:
    return (goal["label"], goal["start_on"], goal["end_on"], goal["target_books"],
            goal["scope"], tuple(sorted(goal["book_ids"])))


def import_bookmatch_json(store: LibraryStore, preview: ImportPreview) -> dict[str, int]:
    added = skipped = 0
    with store.connection:
        for row in preview.rows:
            existing = store.connection.execute("SELECT id FROM books WHERE id = ?", (row["id"],)).fetchone()
            if not existing:
                store.connection.execute(
                    """INSERT INTO books (id, title, author, description, genre,
                                          publication_year, source, source_id,
                                          subjects, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (row["id"], row["title"], row["author"], row.get("description") or "",
                     row.get("genre") or "", row.get("publication_year"),
                     row.get("source") if row.get("source") in ("sample", "manual", "goodreads", "openlibrary") else "manual",
                     row.get("source_id"), row.get("subjects") or "", row.get("source_url") or ""),
                )
            present = store.connection.execute(
                "SELECT 1 FROM library_entries WHERE book_id = ?", (row["id"],)
            ).fetchone()
            if present:
                skipped += 1
                continue
            store.connection.execute(
                """INSERT INTO library_entries
                   (book_id, status, rating, notes, review,
                    started_on, finished_on, source_shelf, shelves)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["id"], row["status"], row.get("rating"), row.get("notes") or "",
                 row.get("review") or "", row.get("started_on"), row.get("finished_on"),
                 row.get("source_shelf") or "", row.get("shelves") or ""),
            )
            added += 1
    store.sync_shelves()
    known = {row["name"].casefold() for row in store.shelf_definitions()}
    for shelf in preview.shelves or []:
        if shelf["name"].casefold() not in known:
            store.create_shelf(shelf["name"])
            known.add(shelf["name"].casefold())
        for page in ("home", "library"):
            store.set_shelf_collapsed(shelf["name"], page, shelf[f"{page}_collapsed"])
    with store.connection:
        for book in preview.goal_books or []:
            store.connection.execute("""INSERT OR IGNORE INTO books
                (id,title,author,description,genre,publication_year,source,source_id,subjects,source_url)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (book["id"], book["title"], book["author"], book.get("description") or "",
                 book.get("genre") or "", book.get("publication_year"),
                 book.get("source") if book.get("source") in ("sample", "manual", "goodreads", "openlibrary") else "manual",
                 book.get("source_id"), book.get("subjects") or "", book.get("source_url") or ""))
    known_goals = {_goal_signature(goal) for goal in store.goals()}
    goals_added = goals_skipped = goal_errors = 0
    for goal in preview.goals or []:
        signature = _goal_signature(goal)
        if signature in known_goals:
            goals_skipped += 1
            continue
        try:
            store.add_goal(goal["label"], goal["start_on"], goal["end_on"], goal["target_books"],
                           book_ids=goal["book_ids"] if goal["scope"] == "selected" else None)
        except ValueError:
            goal_errors += 1
            continue
        known_goals.add(signature)
        goals_added += 1
    return {"added": added, "skipped": skipped, "invalid": len(preview.errors) + goal_errors,
            "goals_added": goals_added, "goals_skipped": goals_skipped}
