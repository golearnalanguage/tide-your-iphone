"""The exact six-field installed-app contract, independent of device discovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .errors import TideError
from .storage import parse_csv, read_json, read_text


REGISTRY_FIELDS = (
    "bundle_id", "base_display_name", "bundle_name", "application_type", "version", "installed",
)


def text_field(value: Any, name: str) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float)) and not isinstance(value, bool):
        return str(value).strip()
    raise TideError(f"应用字段 {name} 必须是文本或数字")


def normalize_apps(raw: Any) -> list[dict[str, Any]]:
    """Whitelist InstallationProxy attributes and reject identifier collisions."""
    if not isinstance(raw, (dict, list)):
        raise TideError("安装清单必须是以 Bundle ID 为键的对象或元数据数组")
    entries = raw.items() if isinstance(raw, dict) else ((None, value) for value in raw)
    rows = []
    for key, metadata in entries:
        if not isinstance(metadata, dict):
            raise TideError("安装清单中每个应用的元数据必须是对象")
        bundle_id = text_field(metadata.get("CFBundleIdentifier") or key, "CFBundleIdentifier")
        if key and metadata.get("CFBundleIdentifier") and str(key) != bundle_id:
            raise TideError(f"安装清单键与 CFBundleIdentifier 不一致: {key}")
        if not bundle_id:
            raise TideError("应用缺少 CFBundleIdentifier")
        rows.append({
            "bundle_id": bundle_id,
            "base_display_name": text_field(metadata.get("CFBundleDisplayName"), "CFBundleDisplayName"),
            "bundle_name": text_field(metadata.get("CFBundleName"), "CFBundleName"),
            "application_type": text_field(metadata.get("ApplicationType"), "ApplicationType"),
            "version": text_field(
                metadata.get("CFBundleShortVersionString") or metadata.get("Product Version")
                or metadata.get("CFBundleVersion"), "version",
            ),
            "installed": True,
        })
    validate_registry(rows)
    return sorted(rows, key=lambda row: (row["bundle_id"].casefold(), row["bundle_id"]))


def validate_registry(rows: Any) -> None:
    if not isinstance(rows, list):
        raise TideError("精简 App Registry 必须是数组")
    seen = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) != set(REGISTRY_FIELDS):
            raise TideError(f"Registry 第 {index} 行必须恰好包含六个字段")
        if any(not isinstance(row[field], str) for field in REGISTRY_FIELDS[:-1]):
            raise TideError(f"Registry 第 {index} 行的前五个字段必须是文本")
        if not row["bundle_id"] or row["bundle_id"] != row["bundle_id"].strip():
            raise TideError(f"Registry 第 {index} 行的 Bundle ID 为空或含首尾空格")
        if row["installed"] is not True:
            raise TideError(f"Registry 第 {index} 行必须包含布尔值 installed=true")
        if row["bundle_id"] in seen:
            raise TideError(f"Registry 包含重复 Bundle ID: {row['bundle_id']}")
        seen.add(row["bundle_id"])


def load_registry(path: Path, *, allow_raw: bool = False) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        fields, rows = parse_csv(read_text(path))
        if set(fields) != set(REGISTRY_FIELDS):
            raise TideError("App Registry CSV 必须恰好包含六个字段")
        for row in rows:
            if row["installed"].strip().lower() != "true":
                raise TideError("App Registry CSV 的 installed 列必须为 true")
            row["installed"] = True
    else:
        rows = read_json(path)
        is_registry = isinstance(rows, list) and all(
            isinstance(row, dict) and "bundle_id" in row for row in rows
        )
        if allow_raw and not is_registry:
            return normalize_apps(rows)
    validate_registry(rows)
    return sorted(rows, key=lambda row: (row["bundle_id"].casefold(), row["bundle_id"]))
