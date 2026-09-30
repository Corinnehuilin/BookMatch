import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookmatch_app.storage import LibraryStore
from bookmatch_app.transfer import (export_library, import_goodreads, import_bookmatch_json,
                                    parse_goodreads_csv, parse_bookmatch_json)


class TransferReviewTests(unittest.TestCase):
    def test_goodreads_can_be_imported_again_after_clear_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / 'synthetic-goodreads.csv'
            with source.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['Book Id', 'Title', 'Author', 'My Rating',
                    'Exclusive Shelf', 'Private Notes', 'My Review', 'Date Read'])
                writer.writeheader()
                writer.writerow({'Book Id': '123456789', 'Title': 'A synthetic reading choice',
                    'Author': 'Example Author', 'My Rating': '4', 'Exclusive Shelf': 'read',
                    'Private Notes': 'Synthetic note', 'My Review': 'Synthetic review', 'Date Read': '2026/01/05'})
            store = LibraryStore(folder / 'library')
            preview = parse_goodreads_csv(source)
            self.assertEqual(import_goodreads(store, preview)['added'], 1)
            book_id = store.library_books()[0]['id']
            self.assertEqual(import_goodreads(store, preview)['skipped'], 1)
            store.clear_saved_books()
            self.assertIsNone(store.book(book_id)['rating'])
            self.assertEqual(import_goodreads(store, preview)['added'], 1)
            self.assertEqual(store.library_books()[0]['id'], book_id)
            self.assertEqual(store.book(book_id)['notes'], 'Synthetic note')
            self.assertEqual(store.connection.execute('SELECT COUNT(*) FROM goodreads_links').fetchone()[0], 1)
            store.close()

    def test_corrupt_optional_json_fields_are_reported_before_import(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            valid = {'id': 'manual-example', 'title': 'Synthetic title', 'author': 'Example author',
                     'status': 'Read', 'rating': 4.25, 'finished_on': '2026-01-05'}
            malformed = ({'notes': {}}, {'review': []}, {'publication_year': 1e100},
                         {'source_id': {}}, {'rating': True}, {'started_on': 'bad date'},
                         {'finished_on': 123}, {'started_on': '2026-02-01'})
            rows = [valid] + [{**valid, **fields, 'id': f'manual-bad-{index}'}
                              for index, fields in enumerate(malformed)]
            source = folder / 'backup.json'
            source.write_text(json.dumps({'format': 'bookmatch-library', 'version': 1, 'books': rows}))
            preview = parse_bookmatch_json(source)
            self.assertEqual(preview.valid_count, 1)
            self.assertEqual(len(preview.errors), len(malformed))
            store = LibraryStore(folder / 'library')
            result = import_bookmatch_json(store, preview)
            self.assertEqual(result['added'], 1)
            self.assertEqual(result['invalid'], len(malformed))
            self.assertEqual(store.library_books()[0]['finished_on'], '2026-01-05')
            store.close()

    def test_extreme_goodreads_year_is_reported_without_overflow(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'synthetic.csv'
            source.write_text('Book Id,Title,Author,Year Published\n1,Example,Example Author,inf\n2,Example two,Example Author,1e100\n')
            preview = parse_goodreads_csv(source)
            self.assertEqual(preview.valid_count, 0)
            self.assertEqual(len(preview.errors), 2)

    def test_failed_backup_replacement_keeps_existing_export_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            store = LibraryStore(folder / 'library')
            store.add_book('Synthetic title', 'Example Author')
            source = folder / 'backup.json'
            source.write_text('existing backup')
            with patch.object(Path, 'replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    export_library(store, source)
            self.assertEqual(source.read_text(), 'existing backup')
            self.assertEqual(list(folder.glob('.bookmatch-backup-*.tmp')), [])
            export_library(store, source)
            self.assertEqual(parse_bookmatch_json(source).valid_count, 1)
            store.close()
