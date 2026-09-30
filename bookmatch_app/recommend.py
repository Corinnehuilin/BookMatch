"""Private local recommendation search with a transparent fallback."""

from __future__ import annotations

import json
import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

MODEL_NAME = "BAAI/bge-small-en-v1.5"
MODEL_CREDIT = "FastEmbed (Apache 2.0) / BAAI bge-small-en-v1.5 (MIT)"
WORD_RE = re.compile(r"[a-z][a-z'-]{2,}")
STOP = {"the", "and", "for", "with", "from", "this", "that", "book", "books", "story", "want", "liked", "loved", "read", "about", "but", "not", "into", "more", "less", "very", "have", "like"}
NEGATIVE_START = re.compile(r"\b(?:but\s+)?(?:i\s+)?(?:don'?t\s+want|do\s+not\s+want|avoid|without|no|less\s+of|disliked|hated)\b", re.I)
SYNONYMS = {
    "eerie": {"haunting", "spooky", "atmospheric", "mysterious"},
    "cozy": {"gentle", "warm", "comforting"},
    "friendship": {"friends", "friendships", "reunion"},
    "friendships": {"friends", "friendship", "reunion"},
    "magic": {"magical", "fantasy", "enchanting"},
    "romance": {"love", "romantic", "relationship"},
    "violence": {"violent", "brutal", "blood", "gore"},
    "graphic": {"gory", "explicit", "brutal"},
    "town": {"village", "hometown", "community"},
}


@dataclass(frozen=True)
class Preferences:
    wanted: str
    avoided: str


@dataclass(frozen=True)
class Match:
    book: dict
    score: float
    explanation: str
    conflict: str
    metadata_note: str


def parse_preferences(query: str) -> Preferences:
    query = query.strip()
    marker = NEGATIVE_START.search(query)
    if marker:
        positive = query[:marker.start()].strip(" ,.;")
        negative = query[marker.end():].strip(" ,.;")
    else:
        positive, negative = query, ""
    return Preferences(positive, negative)


def _words(value: str) -> set[str]:
    return {word for word in WORD_RE.findall(value.casefold()) if word not in STOP}


def book_text(book: dict) -> str:
    return " ".join((book.get("title") or "", book.get("author") or "",
                     book.get("genre") or "", book.get("subjects") or "",
                     book.get("description") or ""))


def _evidence(tokens: set[str], text: str) -> list[str]:
    available = _words(text)
    return sorted(token for token in tokens if token in available or SYNONYMS.get(token, set()) & available)


def model_ready(directory: Path) -> bool:
    return (directory / "models" / "ready.json").is_file()


def catalog_index_ready(directory: Path, revision: str, count: int) -> bool:
    vectors_path, ids_path, manifest_path = _index_paths(directory)
    if not all(path.is_file() for path in (vectors_path, ids_path, manifest_path)):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return manifest == {"revision": revision, "model": MODEL_NAME, "count": count}


def _index_paths(directory: Path) -> tuple[Path, Path, Path]:
    cache = directory / "models"
    return cache / "catalog-vectors.npy", cache / "catalog-ids.json", cache / "catalog-index.json"


def _revision(books: list[dict], revision: str | None) -> str:
    if revision:
        return revision
    value = "\n".join(book["id"] + ":" + book_text(book) for book in books)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ensure_index(directory: Path, books: list[dict], revision: str, model) -> tuple[list[str], object]:
    import numpy as np

    vectors_path, ids_path, manifest_path = _index_paths(directory)
    if vectors_path.is_file() and ids_path.is_file() and manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest == {"revision": revision, "model": MODEL_NAME, "count": len(books)}:
                ids = json.loads(ids_path.read_text(encoding="utf-8"))
                vectors = np.load(vectors_path, mmap_mode="r")
                if len(ids) == len(books) and vectors.shape == (len(books), 384):
                    return ids, vectors
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            pass
    ids = [book["id"] for book in books]
    vectors = np.asarray(list(model.embed((book_text(book) for book in books), batch_size=64)), dtype=np.float32)
    if vectors.shape != (len(books), 384):
        raise RuntimeError("Local model returned an incomplete catalog index")
    vectors_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_vectors = vectors_path.with_suffix(".npy.tmp")
    temporary_ids = ids_path.with_suffix(".json.tmp")
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    with temporary_vectors.open("wb") as stream:
        np.save(stream, vectors)
    temporary_ids.write_text(json.dumps(ids), encoding="utf-8")
    temporary_manifest.write_text(json.dumps({"revision": revision, "model": MODEL_NAME,
                                              "count": len(books)}), encoding="utf-8")
    temporary_vectors.replace(vectors_path)
    temporary_ids.replace(ids_path)
    temporary_manifest.replace(manifest_path)
    return ids, vectors


def install_model(directory: Path, books: list[dict] | None = None,
                  catalog_revision: str | None = None) -> None:
    """Explicit one-time download. Search itself never downloads or sends queries."""
    from fastembed import TextEmbedding

    cache = directory / "models"
    cache.mkdir(parents=True, exist_ok=True)
    model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(cache), local_files_only=False)
    next(iter(model.embed(["A book about friendship."])))
    if books:
        _ensure_index(directory, books, _revision(books, catalog_revision), model)
    (cache / "ready.json").write_text(json.dumps({"model": MODEL_NAME}) + "\n", encoding="utf-8")


def recommend(query: str, books: list[dict], directory: Path, limit: int | None = 12,
              catalog_books: list[dict] | None = None,
              catalog_revision: str | None = None) -> tuple[list[Match], str, Preferences]:
    prefs = parse_preferences(query)
    if not prefs.wanted and not prefs.avoided:
        return [], "No query", prefs
    wanted = _words(prefs.wanted)
    avoided = _words(prefs.avoided)
    semantic_scores: dict[str, float] = {}
    mode = "Metadata fallback"
    if model_ready(directory) and prefs.wanted:
        try:
            from fastembed import TextEmbedding
            import numpy as np
            model = TextEmbedding(model_name=MODEL_NAME, cache_dir=str(directory / "models"), local_files_only=True)
            query_vector = next(iter(model.query_embed(prefs.wanted)))
            all_books = catalog_books if catalog_books is not None else books
            ids, vectors = _ensure_index(directory, all_books,
                                         _revision(all_books, catalog_revision), model)
            eligible = {book["id"] for book in books}
            similarities = np.asarray(vectors @ query_vector, dtype=np.float32)
            semantic_scores = {book_id: float(similarity) for book_id, similarity in zip(ids, similarities)
                               if book_id in eligible}
            mode = "Local semantic model"
        except (ImportError, OSError, RuntimeError, ValueError):
            semantic_scores = {}
    matches = []
    for book in books:
        text = book_text(book)
        positive_evidence = _evidence(wanted, text)
        negative_evidence = _evidence(avoided, text)
        lexical = len(positive_evidence) / max(1, len(wanted))
        semantic = max(0.0, semantic_scores.get(book["id"], 0.0))
        score = (semantic * 0.6 + lexical * 0.4 if semantic_scores else lexical)
        if not wanted:
            score = 0.25
        score -= 0.45 * len(negative_evidence)
        metadata_rich = bool(book.get("description") or book.get("genre") or book.get("subjects"))
        if not metadata_rich:
            score -= 0.1
        if score <= 0 and wanted:
            continue
        if positive_evidence:
            explanation = "Metadata connects to: " + ", ".join(positive_evidence[:4]) + "."
        elif book["id"] in semantic_scores:
            explanation = "Its available book metadata is broadly similar to your request."
        else:
            explanation = "Limited direct evidence in the available metadata."
        conflict = "Possible conflict in metadata: " + ", ".join(negative_evidence[:4]) + "." if negative_evidence else ""
        if not metadata_rich:
            metadata_note = "Description and genre are missing; this match is uncertain."
        elif not book.get("description"):
            metadata_note = "Only subjects or genre are available; themes and content details are unverified."
        else:
            metadata_note = "Metadata can miss themes or content details."
        matches.append(Match(book, score, explanation, conflict, metadata_note))
    matches.sort(key=lambda match: (-match.score, match.book["title"].casefold()))
    return matches[:limit], mode, prefs
