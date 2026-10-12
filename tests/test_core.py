from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from tide_your_iphone.device import Device, select_device, usb_devices
from tide_your_iphone.errors import TideError
from tide_your_iphone.registry import REGISTRY_FIELDS, load_registry, normalize_apps, validate_registry
from tide_your_iphone.storage import csv_bytes, json_bytes, parse_csv, parse_json, verify_manifest, write_artifacts
from tide_your_iphone.usage import aggregate_rows, count_value, coverage_for, join_rankings, load_usage, parse_m0


ROOT = Path(__file__).resolve().parents[1]


class RegistryTests(unittest.TestCase):
    def test_unicode_fallbacks_and_private_key_whitelist(self):
        registry = normalize_apps({
            "org.example.z": {"CFBundleDisplayName": "笔记, Notes\n二", "ApplicationType": "User",
                              "CFBundleVersion": 13, "Container": "private", "Entitlements": {}},
            "org.example.a": {"CFBundleName": "Reader", "CFBundleShortVersionString": "2"},
        })
        self.assertEqual([row["bundle_id"] for row in registry], ["org.example.a", "org.example.z"])
        self.assertEqual(registry[1]["version"], "13")
        self.assertTrue(all(set(row) == set(REGISTRY_FIELDS) for row in registry))
        rows = list(csv.DictReader(io.StringIO(csv_bytes(REGISTRY_FIELDS, registry).decode())))
        self.assertEqual(rows[1]["base_display_name"], "笔记, Notes\n二")
        self.assertEqual(rows[1]["installed"], "true")

    def test_array_metadata_supported(self):
        self.assertEqual(normalize_apps([{"CFBundleIdentifier": "legacyID"}])[0]["bundle_id"], "legacyID")

    def test_duplicates_and_mismatched_ids_rejected(self):
        for raw in ([{"CFBundleIdentifier": "a"}, {"CFBundleIdentifier": "a"}],
                    {"a": {"CFBundleIdentifier": "b"}}):
            with self.subTest(raw=raw), self.assertRaises(TideError):
                normalize_apps(raw)

    def test_invalid_shapes_and_fields_rejected(self):
        for raw in (None, 1, "bad", {"a": None}, [{"CFBundleName": "noID"}], {"a": {"CFBundleName": []}}):
            with self.subTest(raw=raw), self.assertRaises(TideError):
                normalize_apps(raw)

    def test_registry_csv_json_parity_and_bom(self):
        registry = normalize_apps({"a": {"CFBundleName": "Alpha"}})
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            (directory / "registry.json").write_bytes(b"\xef\xbb\xbf" + json_bytes(registry))
            (directory / "registry.csv").write_bytes(b"\xef\xbb\xbf" + csv_bytes(REGISTRY_FIELDS, registry))
            self.assertEqual(load_registry(directory / "registry.json"), registry)
            self.assertEqual(load_registry(directory / "registry.csv"), registry)

    def test_six_fields_and_true_boolean_required(self):
        row = normalize_apps({"a": {}})[0]
        for changed in ({**row, "private_key": 1}, {**row, "installed": "true"},
                        {**row, "bundle_id": " "}, {**row, "version": 1}):
            with self.subTest(changed=changed), self.assertRaises(TideError):
                validate_registry([changed])


class DeviceTests(unittest.TestCase):
    def test_usb_filter_dedup_and_class_selection(self):
        raw = [
            {"ConnectionType": "USB", "DeviceClass": "iPhone", "Identifier": "phone"},
            {"ConnectionType": "Network", "DeviceClass": "iPhone", "Identifier": "network"},
            {"ConnectionType": "USB", "ProductType": "iPad16,1", "UniqueDeviceID": "ipad"},
            {"ConnectionType": "USB", "DeviceClass": "Watch", "Identifier": "watch"},
        ]
        raw.append(raw[0].copy())
        self.assertEqual(len(usb_devices(raw)), 2)
        self.assertEqual(usb_devices(raw, "iPad")[0].udid, "ipad")

    def test_multi_device_requires_selection(self):
        devices = [Device("one", "iPhone"), Device("two", "iPad")]
        self.assertEqual(select_device(devices, "two").device_class, "iPad")
        for candidates, udid in ((devices, None), ([], None), (devices, "missing")):
            with self.subTest(candidates=candidates, udid=udid), self.assertRaises(TideError):
                select_device(candidates, udid)

    def test_invalid_device_metadata_rejected(self):
        for raw in ({}, ["device"], [{"ConnectionType": "USB", "DeviceClass": "iPhone"}]):
            with self.subTest(raw=raw), self.assertRaises(TideError):
                usb_devices(raw)


class UsageTests(unittest.TestCase):
    def test_csv_json_m0_have_equivalent_rankings(self):
        registry = load_registry(ROOT / "examples/installation_proxy.json", allow_raw=True)
        actual = []
        for name in ("usage.csv", "usage.json", "m0_output.txt"):
            rankings, scope = load_usage(ROOT / "examples" / name)
            actual.append(join_rankings(rankings, registry))
        self.assertEqual(actual[0], actual[1])
        self.assertEqual(actual[0], actual[2])

    def test_custom_columns_duplicates_and_deterministic_ties(self):
        rankings = aggregate_rows([
            {"app": "b", "entries": "2"}, {"app": "a", "entries": "1"},
            {"app": "a", "entries": "1"},
        ], bundle_column="app", count_column="entries")
        rows = join_rankings(rankings, normalize_apps({"a": {}, "b": {}}))["foreground_entries"]
        self.assertEqual([(row["bundle_id"], row["count"]) for row in rows], [("a", 2), ("b", 2)])

    def test_unresolved_installed_state_is_unknown(self):
        rankings = {"test": [(3, "missing"), (2, "installed")]}
        rows = join_rankings(rankings, normalize_apps({"installed": {}}))["test"]
        self.assertIsNone(rows[0]["installed"])
        self.assertEqual(rows[0]["resolution"], "unresolved")
        self.assertEqual(rows[0]["app_name"], "missing")
        self.assertEqual(coverage_for(rows)["event_coverage_percent"], 40.0)

    def test_zero_counts_coverage_is_null(self):
        self.assertIsNone(coverage_for([])["event_coverage_percent"])
        rows = join_rankings({"test": [(0, "a")]}, [])["test"]
        self.assertIsNone(coverage_for(rows)["event_coverage_percent"])

    def test_invalid_counts_rejected(self):
        for value in (-1, "-1", 1.0, True, "1.5", "NaN", None):
            with self.subTest(value=value), self.assertRaises(TideError):
                count_value(value)

    def test_single_m0_section_is_supported(self):
        self.assertEqual(parse_m0("===== TOP FOREGROUND ENTRIES =====\n 5 a\n"),
                         {"foreground_entries": [(5, "a")]})

    def test_bad_m0_rows_and_duplicates_fail(self):
        for text in ("nothing", "===== TOP FOREGROUND ENTRIES =====\nbad row\n",
                     "===== TOP FOREGROUND ENTRIES =====\n1 a\n2 a\n"):
            with self.subTest(text=text), self.assertRaises(TideError):
                parse_m0(text)

    def test_multiple_usage_devices_require_explicit_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.csv"
            path.write_text("device_id,bundle_id,count\nphone,a,3\nipad,a,9\n", encoding="utf-8")
            with self.assertRaises(TideError):
                load_usage(path)
            rankings, _ = load_usage(path, usage_device="phone")
            self.assertEqual(rankings, {"foreground_entries": [(3, "a")]})


class StorageTests(unittest.TestCase):
    def test_duplicate_json_keys_and_nonfinite_values_rejected(self):
        for text in ('{"a": 1, "a": 2}', '[NaN]', '[Infinity]'):
            with self.subTest(text=text), self.assertRaises(TideError):
                parse_json(text)

    def test_bad_csv_headers_and_width_rejected(self):
        for text in ("a,a\n1,2\n", "a,b\n1\n", "a,b\n1,2,3\n"):
            with self.subTest(text=text), self.assertRaises(TideError):
                parse_csv(text)

    def test_manifest_tampering_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            write_artifacts(directory, {"a.json": b"[]\n"}, "sums.sha256")
            self.assertEqual(verify_manifest(directory / "sums.sha256"), ["a.json"])
            with self.assertRaises(TideError):
                write_artifacts(directory, {"a.json": b"new"}, "sums.sha256")
            self.assertEqual((directory / "a.json").read_bytes(), b"[]\n")
            (directory / "a.json").write_bytes(b"changed")
            with self.assertRaises(TideError):
                verify_manifest(directory / "sums.sha256")

    def test_input_files_are_protected_even_with_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            path = directory / "input.json"
            path.write_bytes(b"original")
            with self.assertRaises(TideError):
                write_artifacts(directory, {"input.json": b"new"}, "sums.sha256",
                                overwrite=True, inputs=[path])
            self.assertEqual(path.read_bytes(), b"original")

    def test_explicit_overwrite_updates_all_checksums(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            write_artifacts(directory, {"a.json": b"[]\n"}, "sums.sha256")
            write_artifacts(directory, {"a.json": b"[1]\n"}, "sums.sha256", overwrite=True)
            self.assertEqual(verify_manifest(directory / "sums.sha256"), ["a.json"])


if __name__ == "__main__":
    unittest.main()
