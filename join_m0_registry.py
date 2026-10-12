#!/usr/bin/env python3
"""Compatibility entry point; also accepts the generic --usage option."""
import sys

from tide_your_iphone.cli import main

if __name__ == "__main__":
    raise SystemExit(main(["join", *sys.argv[1:]]))
