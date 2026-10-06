import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from workflow import fonts


class PrivateFontTests(unittest.TestCase):
    def test_cache_is_user_specific_and_independent_of_project_folder(self):
        with patch.dict(fonts.os.environ, {"LOCALAPPDATA": "session-local"}):
            self.assertEqual(fonts.font_directory(), Path("session-local/CDDAuditRemediation/fonts/Aptos-4.40"))
        with patch.dict(fonts.os.environ, {}, clear=True):
            self.assertIsNone(fonts.font_directory())

    def test_missing_or_corrupt_font_does_not_load_unverified_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = SimpleNamespace()
            for name in fonts.FONT_HASHES:
                (Path(directory) / name).write_bytes(b"not a font")
            with patch.object(fonts, "font_directory", return_value=Path(directory)), \
                 patch.object(fonts.tkfont, "families", return_value=["Segoe UI"]), \
                 patch.object(fonts, "private_font_api") as api:
                family, warning = fonts.load_ui_font(root)
                api.assert_not_called()
                self.assertEqual(family, "Segoe UI")
                self.assertIn("Install Aptos.cmd", warning)

    def test_failed_second_face_releases_only_this_process_resources(self):
        if fonts.os.name != "nt":
            self.skipTest("Private font loading is Windows-only")
        with tempfile.TemporaryDirectory() as directory:
            root = SimpleNamespace()
            digest = hashlib.sha256(b"test face").hexdigest()
            hashes = {name: digest for name in fonts.FONT_HASHES}
            for name in hashes:
                (Path(directory) / name).write_bytes(b"test face")
            api = Mock()
            api.AddFontResourceExW.side_effect = [1, 0]
            with patch.object(fonts, "FONT_HASHES", hashes), \
                 patch.object(fonts, "font_directory", return_value=Path(directory)), \
                 patch.object(fonts.tkfont, "families", return_value=["Segoe UI"]), \
                 patch.object(fonts, "private_font_api", return_value=api):
                _, warning = fonts.load_ui_font(root)
                self.assertTrue(warning)
                api.RemoveFontResourceExW.assert_called_once_with(str(Path(directory) / "Aptos.ttf"), 0x10, None)
                self.assertEqual(root.private_fonts, [])
