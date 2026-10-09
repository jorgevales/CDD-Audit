from __future__ import annotations

import os
import sys


class ProgressDisplay:
    def __init__(self, total: int, stream=None) -> None:
        self.total = total
        self.stream = stream or sys.stdout
        self.completed = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.completed)

    def show(self, note: str = "") -> None:
        label = f"[ REMAINING: {self.remaining} ]  completed {self.completed}/{self.total}"
        if note:
            label += f"  {note}"
        color = bool(getattr(self.stream, "isatty", lambda: False)()) and os.environ.get("NO_COLOR") is None
        if color:
            label = f"\033[30;103;1m {label} \033[0m"
        print(label, file=self.stream, flush=True)

    def recorded(self, note: str = "") -> None:
        self.completed += 1
        self.show(note)
