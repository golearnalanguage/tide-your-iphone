"""Canonical counts, CSV column mapping, and the legacy M0 text adapter."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re
from typing import Any

from .errors import TideError
from .registry import validate_registry
from .storage import parse_csv, parse_json, read_text


# Our local M0 probe produced these headings using an external
# aw-import-screentime decoder. This adapter reads its output, not SEGB files.
# Upstream project credits are recorded in CREDITS.md.
M0_SECTIONS = {
    "TOP FOREGROUND ENTRIES": "foreground_entries",
    "TOP HOME SCREEN LAUNCHES [EXPERIMENTAL]": "homescreen_launches_experimental",
}
JOIN_FIELDS = (
    "metric", "rank", "count", "bundle_id", "app_name", "base_display_name",
    "bundle_name", "application_type", "version", "installed", "resolution",
)


def count_value(value: Any) -> int:
    if isinstance(value, str) and re.fullmatch(r"\d+", value.strip(), flags=re.ASCII):
        value = int(value.strip())
    if type(value) is not int or value < 0:
        raise TideError("使用次数必须是大于等于零的整数")
    return value


def aggregate_rows(
    rows: Any, bundle_column: str = "bundle_id", count_column: str = "count",
    metric_column: str = "metric", default_metric: str = "foreground_entries",
) -> dict[str, list[tuple[int, str]]]:
    if not isinstance(default_metric, str) or not default_metric.strip():
        raise TideError("默认指标名必须为非空文本")
    if not isinstance(rows, list):
        raise TideError("统计数据必须是行对象数组")
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict) or bundle_column not in row or count_column not in row:
            raise TideError(f"统计数据第 {index} 行缺少 {bundle_column} / {count_column}")
        bundle = row[bundle_column]
        metric = row.get(metric_column) or default_metric
        if not isinstance(bundle, str) or not bundle.strip():
            raise TideError(f"统计数据第 {index} 行的 Bundle ID 无效")
        if not isinstance(metric, str) or not metric.strip():
            raise TideError(f"统计数据第 {index} 行的 metric 无效")
        counts[metric.strip()][bundle.strip()] += count_value(row[count_column])
    if not rows:
        counts[default_metric] = {}
    return {metric: [(count, bundle) for bundle, count in per_app.items()]
            for metric, per_app in counts.items()}


def select_usage_device(
    rows: list[dict[str, Any]], device_column: str, device: str | None,
) -> list[dict[str, Any]]:
    """Prevent different devices in a table from being silently merged."""
    if any(not isinstance(row, dict) for row in rows):
        raise TideError("统计行必须是对象")
    identifiers = {str(row[device_column]) for row in rows
                   if row.get(device_column) is not None and str(row[device_column]).strip()}
    if device:
        selected = [row for row in rows if str(row.get(device_column, "")) == device]
        if not selected:
            raise TideError(f"统计数据中没有 --usage-device 指定的设备；检查 {device_column} 列")
        return selected
    if len(identifiers) > 1:
        raise TideError("统计数据包含多个设备；使用 --usage-device 选择，--device-column 指定设备列")
    if identifiers and any(not row.get(device_column) for row in rows):
        raise TideError("统计数据的设备列有缺失值；请补齐或通过 --usage-device 选择完整记录")
    return rows


def parse_m0(text: str) -> dict[str, list[tuple[int, str]]]:
    rankings: dict[str, list[tuple[int, str]]] = {}
    active = None
    seen: dict[str, set[str]] = defaultdict(set)
    for number, line in enumerate(text.splitlines(), 1):
        header = re.fullmatch(r"\s*=====\s+(.+?)\s+=====\s*", line)
        if header:
            active = M0_SECTIONS.get(header.group(1))
            if active:
                if active in rankings:
                    raise TideError(f"M0 第 {number} 行出现重复统计段")
                rankings[active] = []
            continue
        if not active or not line.strip():
            continue
        match = re.fullmatch(r"\s*(\d+)\s+(\S+)\s*", line)
        if not match:
            raise TideError(f"M0 第 {number} 行的排名格式错误")
        bundle = match.group(2)
        if bundle in seen[active]:
            raise TideError(f"M0 排名包含重复 Bundle ID: {bundle}")
        seen[active].add(bundle)
        rankings[active].append((int(match.group(1)), bundle))
    if not rankings:
        raise TideError("没有发现支持的 M0 排名段；可改用 bundle_id/count/metric JSON 或 CSV")
    return rankings


def load_usage(
    path: Path, *, format: str = "auto", bundle_column: str = "bundle_id",
    count_column: str = "count", metric_column: str = "metric",
    default_metric: str = "foreground_entries",
    device_column: str = "device_id", usage_device: str | None = None,
) -> tuple[dict[str, list[tuple[int, str]]], str]:
    text = read_text(path)
    if format == "auto":
        if path.suffix.lower() == ".csv":
            format = "csv"
        elif text.lstrip().startswith(("[", "{")):
            format = "json"
        else:
            format = "m0"
    if format == "m0":
        if usage_device:
            identifiers = re.findall(r"^Device:\s*(\S+)\s*$", text, flags=re.MULTILINE)
            if identifiers != [usage_device]:
                raise TideError("M0 的 Device 字段与 --usage-device 不匹配")
        return parse_m0(text), "m0_printed_rankings"
    if format == "csv":
        fields, rows = parse_csv(text)
        if bundle_column not in fields or count_column not in fields:
            raise TideError(f"CSV 表头缺少 {bundle_column} / {count_column}")
    else:
        document = parse_json(text)
        if isinstance(document, dict) and "rankings" in document:
            document = document["rankings"]
        if isinstance(document, dict):
            rows = []
            empty_metrics = []
            for metric, ranked in document.items():
                if not isinstance(metric, str) or not metric.strip():
                    raise TideError("JSON 指标名必须为非空文本")
                if not isinstance(ranked, list):
                    raise TideError("JSON 统计对象必须将指标名映射到行数组")
                if not ranked:
                    empty_metrics.append(metric)
                for row in ranked:
                    if not isinstance(row, dict):
                        raise TideError("JSON 统计行必须是对象")
                    rows.append({**row, metric_column: metric})
            selected = select_usage_device(rows, device_column, usage_device)
            result = aggregate_rows(selected, bundle_column, count_column, metric_column, default_metric)
            if not rows:
                result = {}
            for metric in empty_metrics:
                result[metric] = []
            return result, "provided_counts"
        rows = document
    if not isinstance(rows, list):
        raise TideError("统计数据必须是行对象数组")
    rows = select_usage_device(rows, device_column, usage_device)
    return aggregate_rows(rows, bundle_column, count_column, metric_column, default_metric), "provided_counts"


def join_rankings(
    rankings: dict[str, list[tuple[int, str]]], registry: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    validate_registry(registry)
    apps = {row["bundle_id"]: row for row in registry}
    joined = {}
    for metric in sorted(rankings):
        ranked = sorted(rankings[metric], key=lambda pair: (-pair[0], pair[1].casefold(), pair[1]))
        rows = []
        for rank, (count, bundle) in enumerate(ranked, 1):
            app = apps.get(bundle)
            rows.append({
                "metric": metric, "rank": rank, "count": count_value(count), "bundle_id": bundle,
                "app_name": (app["base_display_name"] or app["bundle_name"] or bundle) if app else bundle,
                "base_display_name": app["base_display_name"] if app else "",
                "bundle_name": app["bundle_name"] if app else "",
                "application_type": app["application_type"] if app else "",
                "version": app["version"] if app else "",
                "installed": True if app else None,
                "resolution": "installed_device" if app else "unresolved",
            })
        joined[metric] = rows
    return joined


def coverage_for(rows: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [row for row in rows if row["installed"] is True]
    total = sum(row["count"] for row in rows)
    resolved = sum(row["count"] for row in matched)
    return {
        "ranked_apps": len(rows), "matched_installed_apps": len(matched),
        "unresolved_apps": len(rows) - len(matched), "ranked_events": total,
        "matched_installed_events": resolved,
        "event_coverage_percent": round(resolved / total * 100, 2) if total else None,
    }
