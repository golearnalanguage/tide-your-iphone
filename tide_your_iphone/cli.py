"""The reusable command line entry point."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

from . import __version__
from .device import Pmd3Client, SUPPORTED_CLASSES, abbreviated_udid, select_device
from .errors import TideError
from .registry import REGISTRY_FIELDS, load_registry, normalize_apps
from .storage import csv_bytes, json_bytes, sha256_file, verify_manifest, write_artifacts
from .usage import JOIN_FIELDS, coverage_for, join_rankings, load_usage


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("必须输入正整数") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("必须输入正整数")
    return number


def add_device_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--pmd3", help="pymobiledevice3 可执行文件；默认 TIDE_PMD3 / PATH / 当前 Python 环境")
    parser.add_argument("--device-class", choices=("Any",) + SUPPORTED_CLASSES, default="Any")
    parser.add_argument("--timeout", type=positive_integer, default=120, help="每条设备命令超时秒数")


def add_output_options(parser: argparse.ArgumentParser, default: str) -> None:
    parser.add_argument("--output-dir", type=Path, default=Path(default))
    parser.add_argument("--overwrite", action="store_true", help="替换本命令已生成的输出文件")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tide-your-iphone", description="tide your iPhone — 通用只读应用清单与使用排名")
    parser.add_argument("--version", action="version", version=f"tide your iPhone {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    devices = commands.add_parser("devices", help="列出 USB iPhone / iPad / iPod")
    add_device_options(devices)
    devices.add_argument("--json", action="store_true", help="以 JSON 输出设备选择信息")

    probe = commands.add_parser("probe", help="读取当前设备清单，或离线精简清单文件")
    add_device_options(probe)
    probe.add_argument("--udid", help="多设备时明确选择 UDID")
    probe.add_argument("--input", type=Path, help="离线导入 InstallationProxy JSON 或六字段 Registry JSON/CSV")
    probe.add_argument("--expect-pmd3-version", help="可选：检查指定 pymobiledevice3 版本")
    add_output_options(probe, "data")

    join = commands.add_parser("join", help="将任意设备的 JSON / CSV / M0 统计关联到应用名称")
    join.add_argument("--registry", type=Path, required=True)
    join.add_argument("--usage", "--m0-output", dest="usage", type=Path, required=True)
    join.add_argument("--format", choices=("auto", "json", "csv", "m0"), default="auto")
    join.add_argument("--bundle-column", default="bundle_id")
    join.add_argument("--count-column", default="count")
    join.add_argument("--metric-column", default="metric")
    join.add_argument("--metric", default="foreground_entries", help="输入未提供指标名时的默认指标")
    join.add_argument("--device-column", default="device_id", help="统计数据的设备标识列")
    join.add_argument("--usage-device", help="按统计数据中的设备标识筛选；Biome UUID 与 USB UDID 使用不同命名空间")
    join.add_argument("--top", type=positive_integer, help="每个指标导出的前 N 项；省略则导出全部")
    add_output_options(join, "reports")

    verify = commands.add_parser("verify", help="验证输出文件的 SHA-256")
    verify.add_argument("manifest", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "devices":
            devices = Pmd3Client(args.pmd3, args.timeout).devices(args.device_class)
            if args.json:
                print(json_bytes([device.as_dict() for device in devices]).decode("utf-8"), end="")
            else:
                for device in devices:
                    print(f"{device.udid}  {device.device_class}  {device.product_type}  {device.name}")
                if not devices:
                    print("没有发现 USB Apple 移动设备")
            return 0

        if args.command == "probe":
            if args.input:
                if args.udid or args.pmd3 or args.expect_pmd3_version:
                    raise TideError("--input 为离线模式；移除 --udid / --pmd3 / --expect-pmd3-version")
                registry = load_registry(args.input.expanduser(), allow_raw=True)
                inputs = [args.input.expanduser()]
                description = f"离线导入: {args.input.name}"
            else:
                client = Pmd3Client(args.pmd3, args.timeout)
                version = client.version()
                if args.expect_pmd3_version and version != args.expect_pmd3_version:
                    raise TideError(f"pymobiledevice3 版本不匹配: 预期 {args.expect_pmd3_version}, 实际 {version}")
                device = select_device(client.devices(args.device_class), args.udid)
                registry = normalize_apps(client.apps(device.udid))
                inputs = []
                description = f"{device.device_class} {abbreviated_udid(device.udid)} / pymobiledevice3 {version}"
            paths = write_artifacts(args.output_dir, {
                "app_registry.json": json_bytes(registry),
                "app_registry.csv": csv_bytes(REGISTRY_FIELDS, registry),
            }, "app_registry.sha256", overwrite=args.overwrite, inputs=inputs)
            counts = Counter(row["application_type"] or "Unknown" for row in registry)
            print(description)
            print(f"应用 {len(registry)} 个: " + ", ".join(f"{kind}={count}" for kind, count in sorted(counts.items())))

        elif args.command == "join":
            registry_path = args.registry.expanduser()
            usage_path = args.usage.expanduser()
            registry = load_registry(registry_path)
            rankings, scope = load_usage(
                usage_path, format=args.format, bundle_column=args.bundle_column,
                count_column=args.count_column, metric_column=args.metric_column, default_metric=args.metric,
                device_column=args.device_column, usage_device=args.usage_device,
            )
            full = join_rankings(rankings, registry)
            coverage = {metric: coverage_for(rows) for metric, rows in full.items()}
            exported = {metric: rows[:args.top] if args.top else rows for metric, rows in full.items()}
            document = {
                "schema_version": 1,
                "source": {
                    "registry_file": registry_path.name, "registry_sha256": sha256_file(registry_path),
                    "usage_file": usage_path.name, "usage_sha256": sha256_file(usage_path),
                    "scope": scope,
                },
                "coverage_scope": "all_input_rows_before_top_filter",
                "coverage": coverage, "top": args.top, "rankings": exported,
            }
            paths = write_artifacts(args.output_dir, {
                "app_ranking.json": json_bytes(document),
                "app_ranking.csv": csv_bytes(JOIN_FIELDS, (row for rows in exported.values() for row in rows)),
            }, "app_ranking.sha256", overwrite=args.overwrite, inputs=[registry_path, usage_path])
            for metric, summary in coverage.items():
                percent = summary["event_coverage_percent"]
                shown = f"{percent}%" if percent is not None else "无事件"
                print(f"{metric}: 匹配 {summary['matched_installed_apps']}/{summary['ranked_apps']} 个应用，覆盖 {shown}")

        else:
            for name in verify_manifest(args.manifest.expanduser()):
                print(f"{name}: OK")
            return 0

        for path in paths:
            print(path)
        return 0
    except (TideError, OSError) as exc:
        print(f"错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已取消", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
