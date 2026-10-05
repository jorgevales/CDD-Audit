"""Atomic configuration/checkpoint writes with transient Windows lock recovery."""
import os
import time
from pathlib import Path


def replace_with_retry(source: Path, destination: Path) -> None:
    for attempt in range(12):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(min(0.1 * (attempt + 1), 0.5))
