# Architecture

BookMatch is a single-process Qt desktop application. It starts without a server, cloud database, or hosted recommendation API.

## Modules

| Path | Responsibility |
| --- | --- |
| `bookmatch_app/__main__.py` | Application startup, palette, isolated packaged launch checks |
| `bookmatch_app/__init__.py` | Single app version and Mac build number |
| `bookmatch_app/ui.py` | Six main pages, navigation, catalog/discovery session state, worker coordination |
| `bookmatch_app/dialogs.py` | Add/details forms, shelf and goal editors, local catalog and selected-book pickers |
| `bookmatch_app/widgets.py` | Rounded option menus, animated highlights, shelf sections, pagination, search hint |
| `bookmatch_app/messages.py` | Icon-free notices and confirmations with shared button semantics |
| `bookmatch_app/storage.py` | SQLite schema migrations, catalog ingestion, library/shelves/goals, aggregates |
| `bookmatch_app/transfer.py` | Import previews, validation, duplicate handling, atomic JSON backup replacement |
| `bookmatch_app/recommend.py` | Preference parsing, lexical evidence, optional local embeddings and persisted index |
| `bookmatch_app/metadata.py` | Bounded public work lookups, cache, genre derivation, public-field locking |
| `bookmatch_app/covers.py` | Visible-card cover retrieval, two-request concurrency, local cache and fallbacks |
| `data/` | Public catalog, public cover IDs, and provenance |
| `scripts/` | Packaging, synthetic screenshots, catalog preparation, optional cover caching, repository audit |
| `tests/` | Temporary-library unit and Qt interaction tests |
| `screenshots/` | Current app demos with synthetic reading history |
| `mockups/dark-mode/` | Design concepts, not a runtime theme |

## Data boundaries

Bundled catalog metadata is separate from each user’s application data. The catalog contains works, not editions, and has no pages or ISBNs. Public catalog IDs use `OL…W`; manual/imported records keep stable local IDs.

`library_entries` stores the one reading status, custom shelf assignments, rating, dates, notes, and review. `shelf_definitions` keeps shelf names and independent Home/Library collapse preferences. Built-in statuses are protected. `goals` and `goal_books` represent all-books or fixed selected-book goals; changing shelf contents does not silently change a goal selection. Removing books from shelves clears their reading entries while retaining metadata needed by goals.

The current schema version is 12. Older schemas migrate sequentially, with a backup before the catalog schema rebuild. SQLite foreign keys protect goal and import links; library mutations use transactions. Reading goals count only Read entries with finish dates inside their period. No private data enters the bundled catalog.

## Recommendation flow

The UI snapshots eligible public metadata for a worker thread. Wanted and avoided phrases are separated. Without the model, metadata token evidence scores matches. With the optional BAAI embedding model, local query vectors are compared against a persisted catalog matrix, combined with lexical evidence, and reduced for explicit avoided terms. The UI defaults to popularity sorting and lets users switch to best match. Missing evidence is displayed as uncertainty.

The cache identifies its model, catalog revision, and record count. Model installation is explicit; subsequent search requests load local files only. Network metadata lookups use public work IDs. Cover requests use public cover IDs. Worker completion updates the Qt UI without sharing a SQLite connection across worker threads.

## Review boundary

The repository checker examines candidate, staged, or committed source files. It rejects unexpected paths/file modes, oversized files, common credential patterns, personal machine paths, and catalog fields outside the public schema. It verifies the catalog checksum, 20,000 distinct works, and public cover index. It is an additional publication check, not a comprehensive security certification.
