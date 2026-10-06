"""One line per step (engine-design.md 5): the processed screenshot, the candidates and
their evidence, what was dropped or void, what was done, and which rule decided it."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class RunLog:
    def __init__(self, runs_dir: Path, name: str):
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.dir = runs_dir / f"{stamp}-{name}"
        self.dir.mkdir(parents=True, exist_ok=True)
        self._steps = (self.dir / "steps.jsonl").open("a", encoding="utf-8")

    def screenshot(self, step: int, png: bytes, suffix: str = "") -> str:
        path = self.dir / f"step_{step:03d}{suffix}.png"
        path.write_bytes(png)
        return path.name

    def write_json(self, name: str, data: Any) -> Path:
        path = self.dir / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return path

    def step(self, record: dict[str, Any]) -> None:
        self._steps.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        self._steps.flush()

    def close(self) -> None:
        self._steps.close()
