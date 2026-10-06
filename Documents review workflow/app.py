#!/usr/bin/env python3
"""User entry point for the portable CDD document-review workflow."""

from workflow.web_server import run_app
from workflow.config import CONFIG_PATH
import argparse
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--no-browser", action="store_true", help="Print the local URL without opening it")
    parser.add_argument("--port", type=int, default=0, help="Local interface port (0 selects an available port)")
    args = parser.parse_args()
    run_app(args.config, port=args.port, open_browser=not args.no_browser)
