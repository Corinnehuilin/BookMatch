"""Private SQLite library and the bundled offline catalog."""

from __future__ import annotations

import os
import json
import sqlite3
import uuid
from pathlib import Path

from PySide6.QtCore import QStandardPaths

STATUSES = ("Want to Read", "Currently Reading", "Read", "Did Not Finish")
CATALOG_TOPICS = ("All genres", "Fantasy", "Mystery", "Romance", "Science fiction",
                  "Biography & memoir", "History", "Self-help", "Business", "Psychology",
                  "Poetry", "Horror")
CATALOG_PERIODS = ("Any publication year", "Before 1950", "1950–1999", "2000–2009",
                   "2010–2019", "2020 or later", "Year unknown")
CATALOG_SHELVES = ("All books", "On my shelves", "Not on my shelves")
CATALOG_SORTS = ("Most read", "Title A–Z", "Newest first", "Oldest first")
CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "catalog.json"


def data_directory() -> Path:
    override = os.environ.get("BOOKMATCH_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    location = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    if not location:
        raise RuntimeError("The operating system did not provide an application data folder.")
    return Path(location)


class LibraryStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "library.sqlite3"
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA secure_delete = ON")
        self._migrate()

    def _migrate(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > 12:
            raise RuntimeError("This library was created by a newer version of BookMatch.")
        if version == 0:
            with self.connection:
                self.connection.executescript(
                    """CREATE TABLE library_entries (
                        book_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL CHECK (status IN
                            ('Want to Read', 'Currently Reading', 'Read', 'Did Not Finish')),
                        added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    PRAGMA user_version = 1;"""
                )
        if version < 2:
            with self.connection:
                self.connection.executescript(
                    """CREATE TABLE books (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                        author TEXT NOT NULL CHECK (length(trim(author)) > 0),
                        description TEXT NOT NULL DEFAULT '',
                        genre TEXT NOT NULL DEFAULT '',
                        pages INTEGER CHECK (pages IS NULL OR pages > 0),
                        publication_year INTEGER,
                        isbn TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL CHECK (source IN ('sample', 'manual', 'goodreads')),
                        source_id TEXT,
                        UNIQUE(source, source_id)
                    );
                    ALTER TABLE library_entries ADD COLUMN rating REAL
                        CHECK (rating IS NULL OR (rating >= 0.25 AND rating <= 5
                        AND rating * 4 = CAST(rating * 4 AS INTEGER)));
                    ALTER TABLE library_entries ADD COLUMN notes TEXT NOT NULL DEFAULT '';
                    ALTER TABLE library_entries ADD COLUMN review TEXT NOT NULL DEFAULT '';
                    ALTER TABLE library_entries ADD COLUMN pages_read INTEGER NOT NULL DEFAULT 0
                        CHECK (pages_read >= 0);
                    ALTER TABLE library_entries ADD COLUMN started_on TEXT;
                    ALTER TABLE library_entries ADD COLUMN finished_on TEXT;
                    PRAGMA user_version = 2;"""
                )
        if version < 3:
            with self.connection:
                self.connection.executescript(
                    """ALTER TABLE library_entries ADD COLUMN source_shelf TEXT NOT NULL DEFAULT '';
                    CREATE TABLE goodreads_links (
                        goodreads_id TEXT PRIMARY KEY,
                        book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE
                    );
                    PRAGMA user_version = 3;"""
                )
        if version < 4:
            with self.connection:
                self.connection.executescript(
                    """CREATE TABLE goals (
                        id INTEGER PRIMARY KEY,
                        label TEXT NOT NULL,
                        start_on TEXT NOT NULL,
                        end_on TEXT NOT NULL,
                        target_books INTEGER NOT NULL CHECK (target_books > 0)
                    );
                    PRAGMA user_version = 4;"""
                )
        if version < 5:
            with self.connection:
                self.connection.executescript(
                    """CREATE TABLE dismissed_books (
                        book_id TEXT PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
                        dismissed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    PRAGMA user_version = 5;"""
                )
        if version < 6:
            if version > 0:
                backup_path = self.directory / "library-before-catalog-v6.sqlite3"
                if not backup_path.exists():
                    with sqlite3.connect(backup_path) as backup:
                        self.connection.backup(backup)
            self.connection.commit()
            self.connection.execute("PRAGMA foreign_keys = OFF")
            try:
                self.connection.executescript(
                    """BEGIN;
                    CREATE TABLE books_new (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL CHECK (length(trim(title)) > 0),
                        author TEXT NOT NULL CHECK (length(trim(author)) > 0),
                        description TEXT NOT NULL DEFAULT '',
                        genre TEXT NOT NULL DEFAULT '',
                        pages INTEGER CHECK (pages IS NULL OR pages > 0),
                        publication_year INTEGER,
                        isbn TEXT NOT NULL DEFAULT '',
                        source TEXT NOT NULL CHECK (source IN
                            ('sample', 'manual', 'goodreads', 'openlibrary')),
                        source_id TEXT,
                        subjects TEXT NOT NULL DEFAULT '',
                        source_url TEXT NOT NULL DEFAULT '',
                        UNIQUE(source, source_id)
                    );
                    INSERT INTO books_new
                    (id, title, author, description, genre, pages,
                     publication_year, isbn, source, source_id)
                    SELECT id, title, author, description, genre, pages,
                           publication_year, isbn, source, source_id FROM books;
                    DROP TABLE books;
                    ALTER TABLE books_new RENAME TO books;
                    PRAGMA user_version = 6;
                    COMMIT;"""
                )
            except sqlite3.Error:
                if self.connection.in_transaction:
                    self.connection.rollback()
                raise
            finally:
                self.connection.execute("PRAGMA foreign_keys = ON")
            if self.connection.execute("PRAGMA foreign_key_check").fetchone():
                raise sqlite3.IntegrityError("Catalog migration left a broken reference")
        if version < 7:
            with self.connection:
                self.connection.executescript(
                    """ALTER TABLE library_entries ADD COLUMN shelves TEXT NOT NULL DEFAULT '';
                    PRAGMA user_version = 7;"""
                )
        if version < 8:
            with self.connection:
                self.connection.executescript(
                    """ALTER TABLE books ADD COLUMN read_count INTEGER;
                    ALTER TABLE books ADD COLUMN popularity_rank INTEGER;
                    CREATE INDEX books_popularity_rank ON books(popularity_rank);
                    CREATE TABLE catalog_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                    PRAGMA user_version = 8;"""
                )
        if version < 9:
            with self.connection:
                self.connection.execute(
                    """DELETE FROM books WHERE source='sample' AND NOT EXISTS
                       (SELECT 1 FROM library_entries e WHERE e.book_id=books.id)"""
                )
                self.connection.execute("PRAGMA user_version = 9")
        if version < 10:
            # Legacy work lookups cached edition page counts and ISBNs.
            for cache_file in (self.directory / "metadata-cache").glob("OL*W.json"):
                cache_file.unlink()
            with self.connection:
                self.connection.execute("ALTER TABLE books DROP COLUMN pages")
                self.connection.execute("ALTER TABLE books DROP COLUMN isbn")
                self.connection.execute("ALTER TABLE library_entries DROP COLUMN pages_read")
                self.connection.execute("PRAGMA user_version = 10")
        if version < 11:
            with self.connection:
                self.connection.execute("""CREATE TABLE IF NOT EXISTS shelf_definitions (
                    name TEXT PRIMARY KEY COLLATE NOCASE,
                    builtin INTEGER NOT NULL DEFAULT 0,
                    library_collapsed INTEGER NOT NULL DEFAULT 1,
                    home_collapsed INTEGER NOT NULL DEFAULT 1)""")
                self.connection.executemany(
                    "INSERT OR IGNORE INTO shelf_definitions (name,builtin,library_collapsed) VALUES (?,1,0)",
                    ((name,) for name in STATUSES))
                self.connection.execute("PRAGMA user_version = 11")
            self.sync_shelves()
            self.connection.execute("VACUUM")
        if version < 12:
            with self.connection:
                columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(goals)")}
                if "scope" not in columns:
                    self.connection.execute("ALTER TABLE goals ADD COLUMN scope TEXT NOT NULL DEFAULT 'all' CHECK (scope IN ('all','selected'))")
                self.connection.execute("""CREATE TABLE IF NOT EXISTS goal_books (
                    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
                    book_id TEXT NOT NULL REFERENCES books(id) ON DELETE CASCADE,
                    PRIMARY KEY (goal_id,book_id))""")
                self.connection.execute("PRAGMA user_version = 12")
        with self.connection:
            if CATALOG_PATH.exists():
                payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
                revision = payload.get("catalog_revision") or payload.get("retrieved_at_utc") or "legacy"
                current = self.connection.execute(
                    "SELECT value FROM catalog_meta WHERE key='revision'"
                ).fetchone()
                if not current or current["value"] != revision:
                    self.connection.execute(
                        "UPDATE books SET popularity_rank=NULL, read_count=NULL WHERE source='openlibrary'"
                    )
                    rows = [
                        (book["id"], book["title"], book["author"], book.get("genre") or "",
                         book.get("publication_year"), book["id"],
                         ", ".join(book.get("subjects") or []), book["url"],
                         book.get("read_count"), book.get("rank", index))
                        for index, book in enumerate(payload["books"], start=1)
                    ]
                    self.connection.executemany(
                        """INSERT INTO books
                           (id, title, author, genre, publication_year,
                            source, source_id, subjects, source_url, read_count, popularity_rank)
                           VALUES (?, ?, ?, ?, ?, 'openlibrary', ?, ?, ?, ?, ?)
                           ON CONFLICT(id) DO UPDATE SET
                             read_count=excluded.read_count,
                             popularity_rank=excluded.popularity_rank""",
                        rows,
                    )
                    self.connection.execute(
                        "INSERT OR REPLACE INTO catalog_meta (key, value) VALUES ('revision', ?)",
                        (revision,),
                    )

    def entries(self) -> dict[str, str]:
        rows = self.connection.execute("SELECT book_id, status FROM library_entries").fetchall()
        return {row["book_id"]: row["status"] for row in rows}

    def library_books(self, query: str = "", status: str | None = None) -> list[dict]:
        sql = """SELECT b.*, e.status, e.rating, e.notes, e.review,
                        e.started_on, e.finished_on, e.source_shelf, e.shelves, e.added_at
                 FROM library_entries e JOIN books b ON b.id = e.book_id WHERE 1=1"""
        args: list[str] = []
        if query.strip():
            sql += " AND (b.title LIKE ? OR b.author LIKE ? OR b.genre LIKE ?)"
            pattern = f"%{query.strip()}%"
            args.extend((pattern, pattern, pattern))
        if status:
            sql += " AND e.status = ?"
            args.append(status)
        sql += " ORDER BY e.updated_at DESC, b.title COLLATE NOCASE"
        return [dict(row) for row in self.connection.execute(sql, args)]

    def _catalog_where(self, query: str, topic: str, period: str,
                       shelf: str) -> tuple[str, list[str]]:
        if topic not in CATALOG_TOPICS or period not in CATALOG_PERIODS or shelf not in CATALOG_SHELVES:
            raise ValueError("Choose valid catalog filters")
        sql = "source='openlibrary' AND popularity_rank IS NOT NULL"
        args: list[str] = []
        if query.strip():
            sql += " AND (title LIKE ? OR author LIKE ? OR genre LIKE ? OR subjects LIKE ?)"
            pattern = f"%{query.strip()}%"
            args.extend((pattern,) * 4)
        topic_terms = {
            "Fantasy": ("fantasy",), "Mystery": ("mystery", "detective"),
            "Romance": ("romance", "love stories"),
            "Science fiction": ("science fiction", "sci-fi"),
            "Biography & memoir": ("biograph", "memoir", "autobiograph"),
            "History": ("history", "historical"), "Self-help": ("self-help", "self help"),
            "Business": ("business", "entrepreneurship"), "Psychology": ("psychology",),
            "Poetry": ("poetry", "poems"), "Horror": ("horror",),
        }
        if topic != "All genres":
            terms = topic_terms[topic]
            sql += " AND (" + " OR ".join("(genre LIKE ? OR subjects LIKE ?)" for _ in terms) + ")"
            for term in terms:
                args.extend((f"%{term}%", f"%{term}%"))
        period_bounds = {"Before 1950": (None, 1949), "1950–1999": (1950, 1999),
                         "2000–2009": (2000, 2009), "2010–2019": (2010, 2019),
                         "2020 or later": (2020, None)}
        if period == "Year unknown":
            sql += " AND publication_year IS NULL"
        elif period in period_bounds:
            start, end = period_bounds[period]
            if start is not None:
                sql += " AND publication_year >= ?"
                args.append(start)
            if end is not None:
                sql += " AND publication_year <= ?"
                args.append(end)
        if shelf != "All books":
            sql += (" AND EXISTS" if shelf == "On my shelves" else " AND NOT EXISTS") + \
                   " (SELECT 1 FROM library_entries e WHERE e.book_id = books.id)"
        return sql, args

    def catalog_count(self, query: str = "", *, topic: str = "All genres",
                      period: str = "Any publication year", shelf: str = "All books") -> int:
        where, args = self._catalog_where(query, topic, period, shelf)
        return self.connection.execute("SELECT COUNT(*) FROM books WHERE " + where, args).fetchone()[0]

    def catalog_revision(self) -> str:
        row = self.connection.execute("SELECT value FROM catalog_meta WHERE key='revision'").fetchone()
        return row["value"] if row else ""

    def catalog_books(self, query: str = "", limit: int | None = None,
                      offset: int = 0, *, topic: str = "All genres",
                      period: str = "Any publication year", shelf: str = "All books",
                      sort: str = "Most read") -> list[dict]:
        if sort not in CATALOG_SORTS:
            raise ValueError("Choose a valid catalog sort order")
        where, args = self._catalog_where(query, topic, period, shelf)
        order = {
            "Most read": "popularity_rank, title COLLATE NOCASE",
            "Title A–Z": "title COLLATE NOCASE, popularity_rank",
            "Newest first": "publication_year IS NULL, publication_year DESC, popularity_rank",
            "Oldest first": "publication_year IS NULL, publication_year ASC, popularity_rank",
        }[sort]
        sql = "SELECT * FROM books WHERE " + where + " ORDER BY " + order
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend((limit, offset))
        return [dict(row) for row in self.connection.execute(sql, args)]

    def book(self, book_id: str) -> dict | None:
        row = self.connection.execute(
            """SELECT b.*, e.status, e.rating, e.notes, e.review,
                      e.started_on, e.finished_on, e.source_shelf, e.shelves FROM books b
               LEFT JOIN library_entries e ON e.book_id = b.id WHERE b.id = ?""",
            (book_id,),
        ).fetchone()
        return dict(row) if row else None

    def add_book(self, title: str, author: str, *, genre: str = "", description: str = "",
                 publication_year: int | None = None,
                 status: str = "Want to Read") -> str:
        title, author = title.strip(), author.strip()
        if not title or not author:
            raise ValueError("Title and author are required")
        if status not in STATUSES:
            raise ValueError("Choose a valid reading status")
        duplicate = self.connection.execute(
            "SELECT id, source FROM books WHERE lower(title) = lower(?) AND lower(author) = lower(?)",
            (title, author),
        ).fetchone()
        if duplicate:
            if duplicate["id"] in self.entries():
                raise ValueError("This title and author are already in BookMatch")
            if duplicate["source"] == "openlibrary":
                raise ValueError("This book is in the offline catalog. Use “Find in offline catalog” to add it with its available metadata.")
        # Reuse unshelved metadata without breaking existing goal selections.
        book_id = duplicate["id"] if duplicate else f"manual-{uuid.uuid4().hex}"
        with self.connection:
            self.connection.execute(
                """INSERT INTO books (id, title, author, genre, description,
                                      publication_year, source)
                   VALUES (?, ?, ?, ?, ?, ?, 'manual')
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title,
                   author=excluded.author, genre=excluded.genre,
                   description=excluded.description,
                   publication_year=excluded.publication_year""",
                (book_id, title, author, genre.strip(), description.strip(),
                 publication_year),
            )
            self.connection.execute(
                "INSERT INTO library_entries (book_id, status) VALUES (?, ?)",
                (book_id, status),
            )
        return book_id

    def add_catalog_book(self, book_id: str, *, title: str, author: str, genre: str,
                         description: str, publication_year: int | None,
                         status: str) -> None:
        book = self.book(book_id)
        if book is None or book["source"] != "openlibrary" or book["popularity_rank"] is None:
            raise ValueError("Choose a book from the catalog")
        if book["status"] is not None:
            raise ValueError("This book is already on your shelf")
        title, author = title.strip(), author.strip()
        if not title or not author:
            raise ValueError("Title and author are required")
        if publication_year is not None and not 1 <= publication_year <= 3000:
            raise ValueError("Published year must be between 1 and 3000")
        if status not in STATUSES:
            raise ValueError("Choose a valid reading status")
        with self.connection:
            self.connection.execute(
                """UPDATE books SET title=?, author=?, genre=?, description=?,
                   publication_year=? WHERE id=?""",
                (title, author, genre.strip(), description.strip(), publication_year,
                 book_id),
            )
            self.connection.execute(
                "INSERT INTO library_entries (book_id, status) VALUES (?, ?)",
                (book_id, status),
            )

    def set_status(self, book_id: str, status: str) -> None:
        if not self.book(book_id):
            raise ValueError("Unknown book")
        if status not in STATUSES:
            raise ValueError("Unknown reading status")
        with self.connection:
            self.connection.execute(
                """INSERT INTO library_entries (book_id, status) VALUES (?, ?)
                   ON CONFLICT(book_id) DO UPDATE SET
                   status = excluded.status, updated_at = CURRENT_TIMESTAMP""",
                (book_id, status),
            )

    def update_entry(self, book_id: str, *, status: str, rating: float | None,
                     notes: str, review: str,
                     started_on: str | None, finished_on: str | None,
                     shelves: str = "") -> None:
        if status not in STATUSES:
            raise ValueError("Choose a valid reading status")
        if rating is not None and (rating < 0.25 or rating > 5 or rating * 4 != int(rating * 4)):
            raise ValueError("Rating must be in quarter-star steps between 0.25 and 5")
        book = self.book(book_id)
        if book is None:
            raise ValueError("Unknown book")
        with self.connection:
            normalized_shelves = self._normalize_shelves(shelves)
            self.connection.execute(
                "INSERT OR IGNORE INTO library_entries (book_id, status) VALUES (?, ?)",
                (book_id, status),
            )
            self.connection.execute(
                """UPDATE library_entries SET status = ?, rating = ?, notes = ?, review = ?,
                   started_on = ?, finished_on = ?, shelves = ?,
                   updated_at = CURRENT_TIMESTAMP
                   WHERE book_id = ?""",
                (status, rating, notes.strip(), review.strip(),
                 started_on, finished_on, normalized_shelves, book_id),
            )

    def custom_shelves(self) -> list[str]:
        self.sync_shelves()
        return [row["name"] for row in self.connection.execute(
            "SELECT name FROM shelf_definitions WHERE builtin=0 ORDER BY name COLLATE NOCASE")]

    def sync_shelves(self) -> None:
        rows = self.connection.execute("SELECT shelves FROM library_entries WHERE shelves != ''").fetchall()
        with self.connection:
            for row in rows:
                self._normalize_shelves(row["shelves"])

    def _normalize_shelves(self, value: str) -> str:
        names = []
        seen = set()
        for part in value.split(","):
            name = part.strip()
            if not name or name.casefold() in seen or name.casefold() in {s.casefold() for s in STATUSES}:
                continue
            self.connection.execute("INSERT OR IGNORE INTO shelf_definitions (name) VALUES (?)", (name,))
            canonical = self.connection.execute(
                "SELECT name FROM shelf_definitions WHERE name=? COLLATE NOCASE", (name,)).fetchone()[0]
            names.append(canonical)
            seen.add(name.casefold())
        return ", ".join(names)

    def create_shelf(self, name: str) -> str:
        name = name.strip()
        if not name or len(name) > 60 or "," in name:
            raise ValueError("Use a shelf name from 1 to 60 characters, without commas.")
        if self.connection.execute("SELECT 1 FROM shelf_definitions WHERE name=? COLLATE NOCASE", (name,)).fetchone():
            raise ValueError("A shelf with this name already exists.")
        with self.connection:
            self.connection.execute("INSERT INTO shelf_definitions (name) VALUES (?)", (name,))
        return name

    def delete_shelf(self, name: str) -> None:
        shelf = self.connection.execute(
            "SELECT * FROM shelf_definitions WHERE name=? COLLATE NOCASE", (name,)).fetchone()
        if shelf is None:
            raise ValueError("Unknown shelf.")
        if shelf["builtin"]:
            raise ValueError("The four reading-status shelves cannot be deleted.")
        with self.connection:
            for row in self.connection.execute("SELECT book_id,shelves FROM library_entries").fetchall():
                remaining = [part.strip() for part in row["shelves"].split(",")
                             if part.strip() and part.strip().casefold() != shelf["name"].casefold()]
                self.connection.execute("UPDATE library_entries SET shelves=? WHERE book_id=?",
                                        (", ".join(remaining), row["book_id"]))
            self.connection.execute("DELETE FROM shelf_definitions WHERE name=?", (shelf["name"],))

    def shelf_definitions(self) -> list[dict]:
        self.sync_shelves()
        rows = [dict(row) for row in self.connection.execute("SELECT * FROM shelf_definitions")]
        return sorted(rows, key=lambda row: (0, STATUSES.index(row["name"])) if row["builtin"]
                      else (1, row["name"].casefold()))

    def set_shelf_collapsed(self, name: str, page: str, collapsed: bool) -> None:
        if page not in ("home", "library"):
            raise ValueError("Unknown shelf view.")
        with self.connection:
            self.connection.execute(f"UPDATE shelf_definitions SET {page}_collapsed=? WHERE name=? COLLATE NOCASE",
                                    (int(collapsed), name))

    def assign_shelves(self, book_id: str, status: str, custom_names: list[str]) -> None:
        if status not in STATUSES or self.book(book_id) is None:
            raise ValueError("Choose a valid book and reading status.")
        definitions = {name.casefold(): name for name in self.custom_shelves()}
        if any(name.casefold() not in definitions for name in custom_names):
            raise ValueError("Choose existing custom shelves.")
        names = list(dict.fromkeys(definitions[name.casefold()] for name in custom_names))
        with self.connection:
            self.connection.execute("""INSERT INTO library_entries (book_id,status,shelves) VALUES (?,?,?)
                ON CONFLICT(book_id) DO UPDATE SET status=excluded.status,shelves=excluded.shelves,
                updated_at=CURRENT_TIMESTAMP""", (book_id, status, ", ".join(names)))

    def update_book(self, book_id: str, *, title: str, author: str, genre: str,
                    description: str, publication_year: int | None) -> None:
        title, author = title.strip(), author.strip()
        if not title or not author:
            raise ValueError("Title and author are required")
        current = self.book(book_id)
        if current is None:
            raise ValueError("Unknown book")
        with self.connection:
            self.connection.execute(
                """UPDATE books SET title = ?, author = ?, genre = ?, description = ?,
                   publication_year = ? WHERE id = ?""",
                (title, author, genre.strip(), description.strip(), publication_year,
                 book_id),
            )

    def fill_missing_catalog_details(self, book_id: str, *, genre: str = "",
                                     description: str = "") -> None:
        """Add public metadata to blank fields without replacing a reader's edits."""
        with self.connection:
            self.connection.execute(
                """UPDATE books SET
                     genre = CASE WHEN trim(genre) = '' THEN ? ELSE genre END,
                     description = CASE WHEN trim(description) = '' THEN ? ELSE description END
                   WHERE id = ? AND source = 'openlibrary'""",
                (genre.strip(), description.strip(), book_id),
            )

    def remove_from_library(self, book_id: str) -> None:
        with self.connection:
            self.connection.execute("DELETE FROM library_entries WHERE book_id = ?", (book_id,))

    def goals(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT g.*, (SELECT COUNT(*) FROM library_entries e
               WHERE e.status = 'Read' AND e.finished_on BETWEEN g.start_on AND g.end_on
               AND (g.scope='all' OR EXISTS (SELECT 1 FROM goal_books gb
                    WHERE gb.goal_id=g.id AND gb.book_id=e.book_id)))
               AS completed FROM goals g ORDER BY g.end_on DESC"""
        ).fetchall()
        selections = {}
        for row in self.connection.execute("SELECT goal_id,book_id FROM goal_books ORDER BY book_id"):
            selections.setdefault(row["goal_id"], []).append(row["book_id"])
        return [{**dict(row), "book_ids": selections.get(row["id"], [])} for row in rows]

    def _goal_book_ids(self, book_ids: list[str] | None) -> list[str]:
        if book_ids is None:
            return []
        selected = sorted(set(book_ids))
        if any(self.book(book_id) is None for book_id in selected):
            raise ValueError("One of the selected books could not be found")
        return selected

    def add_goal(self, label: str, start_on: str, end_on: str, target_books: int,
                 *, book_ids: list[str] | None = None) -> int:
        if not label.strip() or start_on > end_on or target_books <= 0:
            raise ValueError("Enter a name, a valid date range, and a target above zero")
        selected = self._goal_book_ids(book_ids)
        with self.connection:
            result = self.connection.execute(
                "INSERT INTO goals (label, start_on, end_on, target_books, scope) VALUES (?, ?, ?, ?, ?)",
                (label.strip(), start_on, end_on, target_books, 'all' if book_ids is None else 'selected'),
            )
            goal_id = result.lastrowid
            self.connection.executemany("INSERT INTO goal_books (goal_id,book_id) VALUES (?,?)",
                                        ((goal_id, book_id) for book_id in selected))
        return goal_id

    def update_goal(self, goal_id: int, label: str, start_on: str, end_on: str,
                    target_books: int, *, book_ids: list[str] | None = None) -> None:
        if not label.strip() or start_on > end_on or target_books <= 0:
            raise ValueError("Enter a name, a valid date range, and a target above zero")
        selected = self._goal_book_ids(book_ids)
        with self.connection:
            result = self.connection.execute(
                "UPDATE goals SET label=?, start_on=?, end_on=?, target_books=?, scope=? WHERE id=?",
                (label.strip(), start_on, end_on, target_books, 'all' if book_ids is None else 'selected', goal_id),
            )
            if result.rowcount != 1:
                raise ValueError("This reading goal could not be found")
            self.connection.execute("DELETE FROM goal_books WHERE goal_id=?", (goal_id,))
            self.connection.executemany("INSERT INTO goal_books (goal_id,book_id) VALUES (?,?)",
                                        ((goal_id, book_id) for book_id in selected))

    def delete_goal(self, goal_id: int) -> None:
        with self.connection:
            result = self.connection.execute("DELETE FROM goals WHERE id=?", (goal_id,))
            if result.rowcount != 1:
                raise ValueError("This reading goal could not be found")

    def stats(self) -> dict:
        row = self.connection.execute(
            """SELECT COUNT(*) AS total,
                      SUM(status = 'Read') AS read_count,
                      SUM(status = 'Currently Reading') AS reading_count,
                      AVG(e.rating) AS average_rating,
                      SUM(status = 'Read' AND finished_on IS NULL) AS undated_read
               FROM library_entries e JOIN books b ON b.id = e.book_id"""
        ).fetchone()
        genres = self.connection.execute(
            """SELECT b.genre, COUNT(*) AS count FROM library_entries e
               JOIN books b ON b.id = e.book_id WHERE b.genre != ''
               GROUP BY b.genre ORDER BY count DESC, b.genre LIMIT 6"""
        ).fetchall()
        months = self.connection.execute(
            """SELECT substr(finished_on, 1, 7) AS month, COUNT(*) AS count
               FROM library_entries WHERE status = 'Read' AND finished_on IS NOT NULL
               GROUP BY month ORDER BY month DESC LIMIT 12"""
        ).fetchall()
        return {**dict(row), "genres": [dict(item) for item in genres],
                "months": [dict(item) for item in months]}

    def discovery_books(self) -> list[dict]:
        rows = self.connection.execute(
            """SELECT b.* FROM books b
               WHERE b.source='openlibrary' AND b.popularity_rank IS NOT NULL
               AND NOT EXISTS (SELECT 1 FROM library_entries e WHERE e.book_id = b.id)
               AND NOT EXISTS (SELECT 1 FROM dismissed_books d WHERE d.book_id = b.id)
               ORDER BY b.popularity_rank"""
        ).fetchall()
        return [dict(row) for row in rows]

    def dismiss_book(self, book_id: str) -> None:
        with self.connection:
            self.connection.execute("INSERT OR IGNORE INTO dismissed_books (book_id) VALUES (?)", (book_id,))

    def close(self) -> None:
        self.connection.close()

    def clear_saved_books(self) -> int:
        """Clear shelf memberships and activity, preserving shelves and goals."""
        with self.connection:
            result = self.connection.execute("DELETE FROM library_entries")
        return result.rowcount
