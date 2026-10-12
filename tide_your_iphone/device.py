"""A subprocess adapter for the installed pymobiledevice3 CLI.

CLI contract: doronz88/pymobiledevice3 (see CREDITS.md and THIRD_PARTY_NOTICES.md).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

from .errors import TideError
from .storage import parse_json


SUPPORTED_CLASSES = ("iPhone", "iPad", "iPod")


@dataclass(frozen=True)
class Device:
    udid: str
    device_class: str
    product_type: str = ""
    product_version: str = ""
    name: str = ""

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def usb_devices(raw: Any, device_class: str = "Any") -> list[Device]:
    if not isinstance(raw, list):
        raise TideError("设备发现返回格式错误：预期 JSON 数组")
    found: dict[str, Device] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise TideError("设备发现数组包含非对象元素")
        if item.get("ConnectionType") != "USB":
            continue
        product = str(item.get("ProductType") or "")
        kind = str(item.get("DeviceClass") or "")
        if not kind:
            kind = next((name for name in SUPPORTED_CLASSES if product.startswith(name)), "")
        if kind not in SUPPORTED_CLASSES or (device_class != "Any" and kind != device_class):
            continue
        udid = str(item.get("UniqueDeviceID") or item.get("Identifier") or "")
        if not udid:
            raise TideError("设备元数据缺少 UDID")
        device = Device(udid, kind, product, str(item.get("ProductVersion") or ""),
                        str(item.get("DeviceName") or ""))
        if udid in found and found[udid] != device:
            raise TideError("设备发现返回了冲突的重复 UDID")
        found[udid] = device
    return sorted(found.values(), key=lambda device: device.udid)


def select_device(devices: list[Device], udid: str | None = None) -> Device:
    if udid:
        matches = [device for device in devices if device.udid == udid]
        if not matches:
            raise TideError("指定 UDID 的 USB 设备未发现，请检查连接、解锁状态和设备类型筛选")
        return matches[0]
    if not devices:
        raise TideError("未发现 USB Apple 移动设备，请连接并解锁设备，检查电脑信任状态")
    if len(devices) > 1:
        raise TideError("连接了多台设备；先运行 devices，再通过 --udid 明确选择")
    return devices[0]


def abbreviated_udid(udid: str) -> str:
    return udid if len(udid) <= 12 else f"{udid[:8]}…{udid[-4:]}"


class Pmd3Client:
    def __init__(self, executable: str | None = None, timeout: int = 120) -> None:
        executable = executable or os.environ.get("TIDE_PMD3")
        if executable:
            location = shutil.which(os.path.expanduser(executable))
            if not location:
                raise TideError("找不到指定的 pymobiledevice3；--pmd3 接受可执行文件路径或命令名")
            self.command = [location]
        elif shutil.which("pymobiledevice3"):
            self.command = [shutil.which("pymobiledevice3")]
        elif importlib.util.find_spec("pymobiledevice3") is not None:
            self.command = [sys.executable, "-m", "pymobiledevice3"]
        else:
            raise TideError("未找到 pymobiledevice3。激活其环境，或设置 --pmd3 / TIDE_PMD3")
        self.timeout = timeout
        self.environment = os.environ.copy()
        # An existing tunnel setting must not redirect an explicitly selected USB device.
        self.environment.pop("PYMOBILEDEVICE3_TUNNEL", None)
        self.environment.pop("PYMOBILEDEVICE3_UDID", None)

    def run(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                self.command + args, capture_output=True, text=True, encoding="utf-8",
                timeout=self.timeout, check=False, stdin=subprocess.DEVNULL, env=self.environment,
            )
        except subprocess.TimeoutExpired as exc:
            raise TideError(f"设备命令超过 {self.timeout} 秒，请检查设备是否解锁") from exc
        except (OSError, UnicodeError) as exc:
            raise TideError(f"pymobiledevice3 无法运行: {exc}") from exc
        if result.returncode:
            detail = result.stderr.strip()[-800:] or f"退出码 {result.returncode}"
            raise TideError(f"pymobiledevice3 命令失败: {detail}")
        return result.stdout

    def version(self) -> str:
        if len(self.command) > 1:
            python = Path(self.command[0])
        else:
            directory = Path(self.command[0]).resolve().parent
            python = next((directory / name for name in ("python", "python3", "python.exe")
                           if (directory / name).is_file()), None)
        if python is None:
            return "unknown"
        try:
            result = subprocess.run(
                [str(python), "-c", "from importlib.metadata import version; print(version('pymobiledevice3'))"],
                capture_output=True, text=True, timeout=min(self.timeout, 10),
                check=False, stdin=subprocess.DEVNULL,
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            return "unknown"

    def devices(self, device_class: str = "Any") -> list[Device]:
        return usb_devices(parse_json(self.run(["usbmux", "list", "--usb"])), device_class)

    def apps(self, udid: str) -> Any:
        # Fail early for incompatible CLI contracts rather than pinning one package version.
        help_text = self.run(["apps", "list", "--help"])
        if "--udid" not in help_text or "--type" not in help_text:
            raise TideError("当前 pymobiledevice3 缺少 apps list 的 --udid / --type 参数")
        return parse_json(self.run([
            "apps", "list", "--udid", udid, "--type", "Any", "--no-mobdev2",
            "--no-calculate-sizes", "--no-show-placeholders",
        ]))
