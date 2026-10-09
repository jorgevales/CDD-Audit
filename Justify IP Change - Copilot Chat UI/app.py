#!/usr/bin/env python3
"""Supported terminal entry point for Justify IP Change - Copilot Chat UI."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from justify_ip_change_copilot_chat_ui.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
