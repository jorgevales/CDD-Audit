#!/usr/bin/env python3
"""User entry point for the portable CDD document-review workflow."""

from workflow.ui import run_app
from workflow.config import CONFIG_PATH
import argparse
from pathlib import Path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    run_app(parser.parse_args().config)
