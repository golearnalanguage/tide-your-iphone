#!/usr/bin/env python3
"""Synthetic CLI used only by integration tests; never touches a device."""
import json
import os
import sys

args = sys.argv[1:]
scenario = os.environ.get("TIDE_TEST_SCENARIO", "single")
devices = [
    {"ConnectionType": "USB", "DeviceClass": "iPhone", "Identifier": "EXAMPLE-PHONE-0001"},
    {"ConnectionType": "USB", "DeviceClass": "iPad", "Identifier": "EXAMPLE-IPAD-0002"},
]

if args == ["usbmux", "list", "--usb"]:
    print(json.dumps(devices if scenario == "multiple" else [] if scenario == "none" else devices[:1]))
elif args == ["apps", "list", "--help"]:
    print("--udid --type --no-mobdev2 --no-calculate-sizes --no-show-placeholders")
elif args[:2] == ["apps", "list"]:
    if "--udid" not in args or args[args.index("--udid") + 1] not in {row["Identifier"] for row in devices}:
        sys.exit(2)
    if any(flag not in args for flag in ("--no-mobdev2", "--no-calculate-sizes", "--no-show-placeholders")):
        sys.exit(2)
    print(json.dumps({
        "org.example.notes": {
            "CFBundleIdentifier": "org.example.notes", "CFBundleDisplayName": "示例笔记",
            "CFBundleName": "ExampleNotes", "ApplicationType": "User",
            "CFBundleShortVersionString": "2.0", "Container": "/private/example-only",
        }
    }))
else:
    sys.exit(2)
