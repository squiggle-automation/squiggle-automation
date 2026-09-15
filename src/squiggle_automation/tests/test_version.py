from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from squiggle_automation.version import get_version


class GetVersionTests(SimpleTestCase):
    def test_reads_version_file(self):
        version_file = Path(__file__).resolve().parent.parent / "VERSION"
        self.assertEqual(get_version(), version_file.read_text().strip())

    def test_missing_version_file_returns_unknown(self):
        with mock.patch.object(Path, "read_text", side_effect=FileNotFoundError):
            self.assertEqual(get_version(), "unknown")
