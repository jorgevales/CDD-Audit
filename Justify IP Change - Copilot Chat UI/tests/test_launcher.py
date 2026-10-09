from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_BOOTSTRAP_SHA256 = "9096efa6e3a8457cc3ec56e749a2d1e17505b756ee3cb2b7e889526367efc187"


class SharedLauncherContractTests(unittest.TestCase):
    def test_bundled_bootstrap_has_approved_hash(self):
        digest = hashlib.sha256((ROOT / "bootstrap" / "virtualenv.pyz").read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_BOOTSTRAP_SHA256)

    def test_dependency_lock_is_exact_and_complete(self):
        lines = [line.strip() for line in (ROOT / "requirements.lock.txt").read_text(encoding="utf-8").splitlines()]
        pins = {line.split("==", 1)[0]: line.split("==", 1)[1] for line in lines if line and not line.startswith("#")}
        self.assertEqual(
            pins,
            {
                "et_xmlfile": "2.0.0",
                "greenlet": "3.5.6",
                "openpyxl": "3.1.5",
                "playwright": "1.55.0",
                "pyee": "13.0.1",
                "typing_extensions": "4.16.0",
            },
        )

    def test_launcher_keeps_shared_setup_safety_contract(self):
        source = (ROOT / "Launcher.ps1").read_text(encoding="utf-8-sig")
        for required in (
            ".venv-setup.lock",
            "SETUP LOCKED:",
            "--no-download",
            "--no-periodic-update",
            "'--seeder','pip'",
            "PIP_TARGET",
            "requirements.lock.txt",
            "Remove-IncompleteEnvironments",
            "Remove-EnvironmentDirectory",
            "mapped_shared_root",
            "normalized_final_path",
            "$WindowsAccount",
            ".setup-logs",
            "[System.IO.Path]::GetTempPath()",
            "distribution(pip.__name__)",
            "[System.Management.Automation.ErrorRecord]",
        ):
            self.assertIn(required, source)
        self.assertNotIn("LOCALAPPDATA", source)
        self.assertNotIn("Preserve-Environment", source)
        self.assertLess(source.index("$LogPath = $null"), source.index("function Find-Python"))

    def test_all_cmd_entrypoints_use_policy_tolerant_launcher(self):
        for name in ("Setup.cmd", "Start Justify IP Change.cmd", "Run Tests.cmd"):
            source = (ROOT / name).read_text(encoding="utf-8-sig")
            self.assertIn("-ExecutionPolicy Bypass", source)
            self.assertIn("Launcher.ps1", source)


if __name__ == "__main__":
    unittest.main()
