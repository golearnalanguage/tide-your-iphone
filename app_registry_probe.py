#!/usr/bin/env python3
"""Compatibility entry point for the original probe command."""
import sys

from tide_your_iphone.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["probe", *sys.argv[1:]]))
