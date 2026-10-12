"""Strict local input and deterministic, atomically written output files."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable

from .errors import TideError


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise TideError(f"无法读取 UTF-8 文件 {path.name}: {exc}") from exc


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TideError(f"JSON 包含重复键: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> Any:
    raise TideError(f"JSON 包含非法数值: {value}")


def parse_json(text: str) -> Any:
    try:
        return json.loads(text, object_pairs_hook=_unique_keys, parse_constant=_invalid_constant)
    except json.JSONDecodeError as exc:
        raise TideError(f"JSON 格式错误（第 {exc.lineno} 行）: {exc.msg}") from exc


def read_json(path: Path) -> Any:
    return parse_json(read_text(path))


def parse_csv(text: str) -> tuple[list[str], list[dict[str, str]]]:
    try:
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        fields = reader.fieldnames
        if not fields or len(set(fields)) != len(fields) or any(not field for field in fields):
            raise TideError("CSV 必须有非空且唯一的列名")
        rows = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise TideError(f"CSV 第 {reader.line_num} 行列数与表头不一致")
            rows.append(row)
        return fields, rows
    except csv.Error as exc:
        raise TideError(f"CSV 格式错误: {exc}") from exc


def json_bytes(document: Any) -> bytes:
    return (json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def csv_bytes(fields: Iterable[str], rows: Iterable[dict[str, Any]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(fields), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        converted = {
            key: ("true" if value is True else "false" if value is False else "" if value is None else value)
            for key, value in row.items()
        }
        writer.writerow(converted)
    return buffer.getvalue().encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise TideError(f"无法计算文件校验值 {path.name}: {exc}") from exc
    return digest.hexdigest()


def write_artifacts(
    directory: Path,
    files: dict[str, bytes],
    checksum_name: str,
    *,
    overwrite: bool = False,
    inputs: Iterable[Path] = (),
) -> list[Path]:
    """Write files with their checksum manifest, leaving inputs protected."""
    directory = directory.expanduser().absolute()
    names = list(files) + [checksum_name]
    protected = {path.resolve() for path in inputs}
    targets = [directory / name for name in names]
    for target in targets:
        if target.resolve() in protected:
            raise TideError(f"输出 {target.name} 与输入文件重合，请选择其他输出目录")
        if target.exists() and (target.is_dir() or not overwrite):
            raise TideError(f"输出已存在: {target}；更换目录或使用 --overwrite")

    manifest = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in files.items())
    payloads = {**files, checksum_name: manifest.encode("utf-8")}
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".tide-", dir=directory) as staging:
            staged_files = []
            for name, data in payloads.items():
                staged = Path(staging) / name
                with staged.open("wb") as handle:
                    handle.write(data)
                    handle.flush()
                    os.fsync(handle.fileno())
                staged_files.append(staged)
            for staged, target in zip(staged_files, targets):
                if overwrite:
                    os.replace(staged, target)
                else:
                    # link is atomic and fails if another run creates the same file.
                    os.link(staged, target)
    except OSError as exc:
        raise TideError(f"无法写入输出目录 {directory}: {exc}") from exc
    return targets


def verify_manifest(path: Path) -> list[str]:
    lines = read_text(path).splitlines()
    if not lines:
        raise TideError("SHA-256 清单为空")
    verified = []
    for line in lines:
        digest, separator, name = line.partition("  ")
        if (not separator or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)
                or not name or Path(name).name != name or "/" in name or "\\" in name):
            raise TideError("SHA-256 清单行格式错误或文件名越出了当前目录")
        if sha256_file(path.parent / name) != digest:
            raise TideError(f"SHA-256 不匹配: {name}")
        verified.append(name)
    return verified
