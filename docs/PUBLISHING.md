# Publishing the reviewed source

Target repository: [Corinnehuilin/BookMatch](https://github.com/Corinnehuilin/BookMatch).

The initial source preparation uses `codex/github-prep`, intended to become the remote `main` branch after owner approval. Publication retains the repository's current visibility. The prepared commit credits `Corinnehuilin` using GitHub's private noreply author email, configured for this repository only.

## Included

- Python app source and packaging entry point.
- Public 20,000-work catalog, aggregate reading-log counts, public cover IDs, and attribution.
- Original app icon and the nine screenshots supplied and approved by the owner on 2026-10-02.
- Tests, packaging/data/demo scripts, pinned dependencies, Mac dependency lock, documentation, and ignore rules.

## Kept local

- Goodreads exports, reading-log source records, personal JSON backups, SQLite databases, and their journals.
- User ratings, reviews, dates, notes, and shelf memberships.
- Bulk source dumps, downloaded covers, metadata caches, model weights and indexes.
- Virtual environments, app bundles, ZIP installers, build folders, packaging caches, and publication manifests.

Source publication does not publish an installer or create a GitHub Release. App-code licensing remains unassigned. Raw Goodreads exports, personal backups, and private databases stay local. Publishing screenshots that display reading activity requires the owner's explicit authorization; the current gallery was supplied and authorized by the owner. Test fixtures and generated demo screenshots continue to use synthetic reading activity.

## Review the exact commit

```sh
.venv/bin/python -m scripts.check_repository --staged
# After the prepared commit exists:
.venv/bin/python -m scripts.check_repository --revision HEAD \
  --manifest .local/publish-manifest.json
git status --short
git log -1 --oneline
git ls-tree -r --name-only HEAD
```

The manifest records file paths, byte sizes, and SHA-256 hashes. It belongs in the ignored `.local/` directory. The checker adds a publication gate but does not replace reviewing the source and screenshots.

## Owner approval and upload

Review the README, source contents, release limits, and file manifest before authorizing publication. Upload only this reviewed branch to the intended repository and branch. When local Git authentication is available, the explicit first push is:

```sh
git push origin codex/github-prep:main
```

Do not use `--all`, `--mirror`, or include development checkpoint refs. The initial reviewed branch is a new root commit containing only the audited files. Local Codex checkpoints are separate refs and are outside this publication scope. If terminal authentication is not configured, use the connected GitHub account to upload the same reviewed contents after approval; do not store tokens in the source tree.

Repository visibility changes, assigning an app-code license, and publishing binary releases each need the owner's explicit choice.
