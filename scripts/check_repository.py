"""Check the exact source files proposed for GitHub; never inspect private app data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = {'.gitignore', 'README.md', 'PROJECT_STATUS.md', 'THIRD_PARTY_NOTICES.md',
              'requirements.txt', 'requirements-build.txt', 'requirements-lock-macos-arm64.txt',
              'run_bookmatch.py'}
SOURCE_ROOTS = {'bookmatch_app', 'scripts', 'tests', 'docs'}
ASSET_ROOTS = {'assets', 'screenshots', 'mockups'}
DATA_FILES = {'data/catalog.json', 'data/cover_ids.json', 'data/SOURCE.md'}
NOTICE_FILES = {'third_party/README.md', 'third_party/licenses/LGPL-3.0-only.txt',
                'third_party/licenses/GPL-3.0-only.txt'}
SECRETS = re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|'
                     rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|'
                     rb'AKIA[0-9A-Z]{16}|' + b'/' + rb'Users/[^/\s]+/)')
WORK_ID = re.compile(r'OL\d+W\Z')


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def audit(staged=False, revision=None):
    names = git('ls-tree', '-r', '--name-only', '-z', revision) if revision else git(
        'ls-files', '-z', '--cached', *([] if staged else ['--others', '--exclude-standard']))
    paths = sorted(set(name.decode('utf-8') for name in names.split(b'\0') if name))
    errors, files = [], []
    payloads = {}
    for name in paths:
        parts = PurePosixPath(name).parts
        allowed = (name in ROOT_FILES or name in DATA_FILES or name in NOTICE_FILES or
                   parts[0] in SOURCE_ROOTS and Path(name).suffix in ('.py', '.sh', '.ps1', '.md') or
                   parts[0] in ASSET_ROOTS and Path(name).suffix in ('.png', '.ico', '.md'))
        if not allowed or '__pycache__' in parts:
            errors.append(f'Unexpected file: {name}')
            continue
        path = ROOT / name
        if not revision and not staged and path.is_symlink():
            errors.append(f'Symlink is not publishable: {name}')
            continue
        if revision or staged:
            entry = git('ls-tree', revision, '--', name) if revision else git('ls-files', '--stage', '--', name)
            if not entry.startswith(b'100644 ') and not entry.startswith(b'100755 '):
                errors.append(f'Unexpected Git file mode: {name}')
                continue
        raw = git('show', f'{revision}:{name}' if revision else f':{name}') if revision or staged else path.read_bytes()
        if len(raw) > 20_000_000:
            errors.append(f'File too large for the source repository: {name}')
        if SECRETS.search(raw):
            errors.append(f'Possible credential or personal machine path: {name}')
        files.append({'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
        if name in DATA_FILES and name.endswith('.json'):
            payloads[name] = json.loads(raw)
    required = ROOT_FILES | DATA_FILES | NOTICE_FILES
    errors.extend(f'Missing required file: {name}' for name in sorted(required - set(paths)))
    catalog = payloads.get('data/catalog.json', {})
    if set(catalog) != {'source', 'ranking', 'snapshot', 'retrieved_at_utc', 'catalog_revision', 'books'}:
        errors.append('Unexpected catalog header fields')
    books = catalog.get('books', [])
    expected = {'id', 'title', 'author', 'genre', 'subjects', 'publication_year', 'read_count', 'rank', 'url'}
    if len(books) != 20_000 or len({b.get('id') for b in books}) != 20_000:
        errors.append('The public catalog must contain 20,000 unique works')
    for rank, book in enumerate(books, 1):
        if (set(book) != expected or not WORK_ID.fullmatch(book.get('id', '')) or
                book.get('rank') != rank or type(book.get('read_count')) is not int or book['read_count'] < 1 or
                book.get('url') != 'https://openlibrary.org/works/' + book['id']):
            errors.append(f'Unexpected public catalog fields at rank {rank}')
            break
    digest = hashlib.sha256(json.dumps(books, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    if catalog.get('catalog_revision') != digest:
        errors.append('Catalog revision does not match its public metadata')
    covers = payloads.get('data/cover_ids.json', {})
    public_ids = {book['id'] for book in books}
    if any(work_id not in public_ids or type(cover_id) is not int or cover_id <= 0
           for work_id, cover_id in covers.items()):
        errors.append('The cover index must contain public catalog IDs and positive numeric cover IDs only')
    if errors:
        raise ValueError('\n'.join(errors))
    return {'files': files, 'file_count': len(files), 'source_bytes': sum(f['bytes'] for f in files),
            'catalog_works': len(books), 'cover_ids': len(covers)}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--staged', action='store_true')
    group.add_argument('--revision', help='Review files from a local commit, for example HEAD')
    parser.add_argument('--manifest', type=Path, help='Write a local file/hash manifest (use an ignored folder)')
    args = parser.parse_args()
    try:
        result = audit(args.staged, args.revision)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'Repository review failed:\n{error}')
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(result, indent=2) + '\n')
    print(f"Reviewed {result['file_count']} files; {result['source_bytes'] / 1_000_000:.2f} MB; "
          f"{result['catalog_works']:,} public works; no unexpected publishable files found.")


if __name__ == '__main__':
    main()
