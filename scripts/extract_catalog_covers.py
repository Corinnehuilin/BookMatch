"""Extract public cover IDs for bundled works from the already downloaded dump."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKS = ROOT / ".catalog-source" / "works.txt.gz"
CATALOG = ROOT / "data" / "catalog.json"
OUTPUT = ROOT / "data" / "cover_ids.json"


def extract() -> None:
    payload = json.loads(CATALOG.read_text(encoding="utf-8"))
    wanted = {f"/works/{book['id']}" for book in payload["books"]}
    covers: dict[str, int] = {}
    description_count = 0
    found = 0
    with gzip.open(WORKS, "rt", encoding="utf-8") as stream:
        for line in stream:
            parts = line.split("\t", 4)
            if len(parts) != 5 or parts[1] not in wanted:
                continue
            try:
                work = json.loads(parts[4])
            except json.JSONDecodeError:
                continue
            found += 1
            description = work.get("description")
            if isinstance(description, dict):
                description = description.get("value")
            if isinstance(description, str) and description.strip():
                description_count += 1
            ids = work.get("covers")
            if isinstance(ids, list):
                cover_id = next((value for value in ids if type(value) is int and value > 0), None)
                if cover_id:
                    covers[parts[1].removeprefix("/works/")] = cover_id
    OUTPUT.write_text(json.dumps(covers, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Matched {found:,} works; {description_count:,} have descriptions; "
          f"{len(covers):,} have cover IDs. Saved {OUTPUT}", flush=True)


if __name__ == "__main__":
    extract()
