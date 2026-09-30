import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookmatch_app.metadata import fetch_work_summary, genre_from_subjects


class MetadataTests(unittest.TestCase):
    def test_work_summary_fills_only_supported_public_fields(self):
        work = {
            "description": {"value": "A public summary."},
            "subjects": ["Habit breaking", "SELF-HELP / Personal Growth / General."],
            "first_publish_date": "2018",
        }
        with tempfile.TemporaryDirectory() as folder, patch(
            "bookmatch_app.metadata._read_json", return_value=work
        ) as reader:
            result = fetch_work_summary("OL17930368W", Path(folder))
            self.assertEqual(result["description"], "A public summary.")
            self.assertEqual(result["genre"], "Self-help")
            reader.assert_called_once_with("https://openlibrary.org/works/OL17930368W.json")
            reader.reset_mock()
            self.assertEqual(fetch_work_summary("OL17930368W", Path(folder)), result)
            reader.assert_not_called()
        self.assertEqual(genre_from_subjects("Habit, SELF-HELP / Personal Growth / General."), "Self-help")
        self.assertEqual(genre_from_subjects("Habit, Behavior modification"), "")

    def test_lookup_uses_only_public_work_id_and_caches_result(self):
        work = {"description": {"value": "A public summary."}, "first_publish_date": "2018"}
        with tempfile.TemporaryDirectory() as folder, patch(
            "bookmatch_app.metadata._read_json", return_value=work
        ) as reader:
            result = fetch_work_summary("OL17930368W", Path(folder))
            self.assertEqual(result["description"], "A public summary.")
            self.assertEqual([call.args[0] for call in reader.call_args_list], [
                "https://openlibrary.org/works/OL17930368W.json",
            ])
            reader.reset_mock()
            self.assertEqual(fetch_work_summary("OL17930368W", Path(folder)), result)
            reader.assert_not_called()
            with self.assertRaises(ValueError):
                fetch_work_summary("Atomic Habits?query=private", Path(folder))


if __name__ == "__main__":
    unittest.main()
