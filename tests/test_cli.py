from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tide_your_iphone.cli import main
from tide_your_iphone.device import Pmd3Client
from tide_your_iphone.errors import TideError


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.pmd = self.directory / "provider with spaces"
        shutil.copyfile(ROOT / "tests/fake_pmd3.py", self.pmd)
        self.pmd.chmod(0o700)

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, args):
        output, error = io.StringIO(), io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            status = main(args)
        return status, output.getvalue(), error.getvalue()

    def test_device_adapter_with_nonstandard_provider_path(self):
        status, _, error = self.invoke(["probe", "--pmd3", str(self.pmd), "--output-dir", str(self.directory)])
        self.assertEqual(status, 0, error)
        registry = json.loads((self.directory / "app_registry.json").read_text())
        self.assertEqual(registry[0]["base_display_name"], "示例笔记")
        self.assertNotIn("Container", registry[0])

    def test_multi_device_probe_stops_then_explicit_udid_succeeds(self):
        with patch.dict(os.environ, {"TIDE_TEST_SCENARIO": "multiple"}):
            status, _, error = self.invoke(["probe", "--pmd3", str(self.pmd), "--output-dir", str(self.directory)])
            self.assertEqual(status, 1)
            self.assertIn("多台", error)
            self.assertFalse((self.directory / "app_registry.json").exists())
            status, _, error = self.invoke([
                "probe", "--pmd3", str(self.pmd), "--udid", "EXAMPLE-IPAD-0002",
                "--output-dir", str(self.directory),
            ])
            self.assertEqual(status, 0, error)

    def test_devices_json(self):
        with patch.dict(os.environ, {"TIDE_TEST_SCENARIO": "multiple"}):
            status, output, error = self.invoke(["devices", "--pmd3", str(self.pmd), "--json"])
        self.assertEqual(status, 0, error)
        self.assertEqual(len(json.loads(output)), 2)

    def test_environment_provider_and_path_lookup(self):
        for environment in ({"TIDE_PMD3": str(self.pmd)}, {"TIDE_PMD3": "", "PATH": str(self.directory)}):
            if "PATH" in environment:
                destination = self.directory / "pymobiledevice3"
                shutil.copyfile(self.pmd, destination)
                destination.chmod(0o700)
            with patch.dict(os.environ, environment):
                client = Pmd3Client()
                self.assertTrue(Path(client.command[0]).is_file())

    def test_nonzero_timeout_and_invalid_json_have_actionable_errors(self):
        client = Pmd3Client(str(self.pmd), timeout=1)
        with patch("tide_your_iphone.device.subprocess.run", side_effect=subprocess.TimeoutExpired("pmd", 1)):
            with self.assertRaisesRegex(TideError, "超过 1"):
                client.devices()
        with patch("tide_your_iphone.device.subprocess.run", return_value=subprocess.CompletedProcess([], 2, "", "locked")):
            with self.assertRaisesRegex(TideError, "locked"):
                client.devices()
        with patch("tide_your_iphone.device.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "not json", "")):
            with self.assertRaisesRegex(TideError, "JSON"):
                client.devices()

    def test_offline_probe_join_top_and_verification(self):
        status, _, error = self.invoke([
            "probe", "--input", str(ROOT / "examples/installation_proxy.json"),
            "--output-dir", str(self.directory),
        ])
        self.assertEqual(status, 0, error)
        status, _, error = self.invoke([
            "join", "--registry", str(self.directory / "app_registry.csv"),
            "--usage", str(ROOT / "examples/usage.json"), "--top", "1",
            "--output-dir", str(self.directory),
        ])
        self.assertEqual(status, 0, error)
        ranking = json.loads((self.directory / "app_ranking.json").read_text())
        self.assertEqual(len(ranking["rankings"]["foreground_entries"]), 1)
        self.assertEqual(ranking["coverage"]["foreground_entries"]["ranked_apps"], 3)
        self.assertEqual(ranking["coverage"]["foreground_entries"]["ranked_events"], 21)
        self.assertEqual(self.invoke(["verify", str(self.directory / "app_registry.sha256")])[0], 0)
        self.assertEqual(self.invoke(["verify", str(self.directory / "app_ranking.sha256")])[0], 0)

    def test_no_device_and_missing_input_are_clean_failures(self):
        with patch.dict(os.environ, {"TIDE_TEST_SCENARIO": "none"}):
            status, _, error = self.invoke(["probe", "--pmd3", str(self.pmd), "--output-dir", str(self.directory)])
        self.assertEqual(status, 1)
        self.assertIn("未发现", error)
        status, _, error = self.invoke(["probe", "--input", str(self.directory / "missing.json")])
        self.assertEqual(status, 1)
        self.assertNotIn("Traceback", error)

    def test_module_entrypoint_from_another_working_directory(self):
        result = subprocess.run(
            [sys.executable, "-m", "tide_your_iphone", "probe", "--input", str(ROOT / "examples/installation_proxy.json")],
            cwd=self.directory, env={**os.environ, "PYTHONPATH": str(ROOT)},
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.directory / "data/app_registry.json").is_file())


if __name__ == "__main__":
    unittest.main()
