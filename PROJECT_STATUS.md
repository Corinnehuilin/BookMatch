# Review and release status

Reviewed: 2026-09-30 · Version: 0.2.22 · Schema: 12

## Source readiness

- Source, public catalog metadata, synthetic screenshots, and design concepts are separated from private application data and local build outputs.
- The catalog contains 20,000 unique Open Library works and aggregate read counts from the 2026-08-31 snapshot. The public cover-ID index has 19,351 entries. Catalog provenance and rights information are documented in `data/SOURCE.md`.
- README, usage guide, architecture guide, publishing procedure, and third-party notices describe current behavior and limitations.
- The app version and Mac build number have one definition in `bookmatch_app/__init__.py`. Mac packaging reads it; optional lookup User-Agent strings use the same version.
- Direct dependencies are pinned. The reviewed Python 3.14 / macOS arm64 environment is also recorded in a platform-specific dependency lock.
- BookMatch's own application code remains unlicensed. Dependencies retain their separate terms. No hosted AI API, paid service, or billing-dependent automation is configured.

## Review fixes

- Clearing saved books no longer prevents reimporting the same Goodreads export. Existing saved records are still skipped; reimport after clearing restores reading activity only when explicitly selected and confirmed.
- JSON import validates optional text, publication year, ratings, and reading dates before importing a record. Extreme CSV publication years are reported as invalid rather than overflowing during import.
- JSON backup export writes to a temporary file, flushes it, and replaces the destination after writing succeeds. A failed replacement leaves the existing backup intact.
- Shared popups omit icons; incorrect CLEAR confirmation gives feedback; goal deletion preserves library books and other goals; Genre labels are consistent across Catalog and Discover.
- Source screenshots use temporary synthetic reading history and disable cover downloads. Private library counts, personal machine paths, and session-specific import details have been removed from publishable documentation.

## Verification

- 60 unit and Qt UI tests pass, covering storage/migrations, imports and backups, clearing and fresh re-addition, custom goal selection/deletion, shelves, catalog navigation, discovery filters, metadata lookup, responsive layout, sidebar behavior, rating displays, and popup semantics.
- The local dependency checker reports no broken requirements.
- Packaged Mac launch checks use an isolated temporary library. Mac signature verification and ZIP integrity checks pass.
- The repository audit validates source paths, file modes, catalog schema/checksum, public cover IDs, and common credential or personal-path patterns. The exact staged/committed files are reviewed before publishing.

## Release limits

- Apple Silicon Mac is the verified packaging target. The local build uses an ad hoc signature; there is no paid Developer ID signature or Apple notarization.
- Windows packaging is prepared but has not been run on Windows. Linux packaging and Intel Mac packages are not validated.
- Dark mode is a design concept; the current app uses its light theme.
- The optional model's first catalog index can take several minutes. Missing catalog descriptions/genres/covers remain possible; recommendation matches are not verified content warnings.
- The SQLite database and exported JSON backups are unencrypted local files. No online account or syncing service exists.
- Public binary distribution is a separate step, including verification of dependency notices and platform installation behavior. This review prepares the source repository.

See [publishing procedure](docs/PUBLISHING.md) for the approved source-only scope. Repository visibility and app-code licensing are separate owner decisions.
