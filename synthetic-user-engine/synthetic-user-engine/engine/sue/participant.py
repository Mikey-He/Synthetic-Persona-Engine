"""A person's session from the study page's participant file, against the engine's runs.

The participant file (testing-platform/billing-config-study) holds the person's events and what
the product saved; an engine run on a web product holds its steps and, in the summary, what the
product saved. Both become the same moves, so sue.compare's measures apply: content, order,
direction and saved settings. A move is a thing done, named as it reads on screen; clicking,
typing and choosing are one kind, because the person's log records a ticked box as a field change
where the engine records a click on its label. Pages are not moves: in this product a page changes
only by a click, already counted, and the engine's route leaves out a fragment like #budgets.

    python -m sue.participant --person data/participants/billing-config/participant-001.json --engine runs/<run folder>
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from .compare import compare, flatten, side_by_side
from .screen import Strip
from .target import same

NAMED = "(the name they typed)"
NOT_SETTINGS = ("id", "name")  # every budget gets its own id, and each side names it differently


def load(path: Path | str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("kind") != "uat-participant-file":
        raise ValueError(f"{path} is not a participant file")
    return data


def engine_window(person: dict[str, Any]) -> str:
    """The window that gives the engine the person's page: the size of the page they saw, plus the
    task bar the engine draws below it."""
    seen = longest_window(person.get("events") or []) or person["session"]["viewport"]
    return f"{seen['width']}x{seen['height'] + Strip.HEIGHT}"


def longest_window(events: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """The window size that was on screen longest: some resize just after they start."""
    rows = [e for e in events if e.get("clientTs")]
    held: dict[tuple[int, int], float] = {}
    size, since = None, None
    for e in rows:
        at = datetime.fromisoformat(e["clientTs"].replace("Z", "+00:00"))
        payload = e.get("payload") or {}
        new = payload.get("viewport") if e.get("type") == "session_started" else payload if e.get("type") == "viewport_changed" else None
        if size and (new or e is rows[-1]):
            held[size] = held.get(size, 0.0) + (at - since).total_seconds()
        if new:
            size, since = (new["width"], new["height"]), at
    if not held:
        return None
    width, height = max(held, key=held.get)
    return {"width": width, "height": height}


def thing(label: Any) -> str:
    """A control or field as it reads, without the menu dots that follow some names."""
    return re.sub(r"^[▾▸]\s*|\s*⌄$", "", re.sub(r"\s+", " ", str(label or "").replace("⋮", "")).strip()).lower()


def named_as(label: str, fields: Iterable[str]) -> str:
    """A section header or field whose label goes on with its current value, by its name alone."""
    return next((f.lower() for f in fields if label.startswith(f.lower())), label)


def _add(out: list[str], move: str) -> None:
    if not out or out[-1] != move:  # typing 1, 10, 100, 1000 is one change
        out.append(move)


def person_moves(events: Iterable[dict[str, Any]], fields: Iterable[str] = ()) -> list[str]:
    out: list[str] = []
    named = ""
    for e in events:
        kind, payload = e.get("type"), e.get("payload") or {}
        if kind == "field_changed":
            field = thing(payload.get("field"))
            if field.startswith("name"):
                named = thing(payload.get("value"))
            _add(out, "do " + field)
        elif kind == "control_clicked":
            label = named_as(thing(payload.get("label")), fields)
            _add(out, "do " + (NAMED if named and label == named else label))
    return out


def engine_moves(steps: Iterable[dict[str, Any]], fields: Iterable[str] = ()) -> list[str]:
    out: list[str] = []
    named = ""
    steps = list(steps)
    for n, s in enumerate(steps):
        a = s.get("action") or {}
        if a.get("type") not in ("click", "type", "choose", "open_help"):
            continue
        # What the person's log could never hold: the task bar, a click that missed, a click into a
        # field that changed nothing (their log records a field only when it changes).
        if str(a.get("note") or "").endswith("the test's own bar)") or a.get("misclick"):
            continue
        after = steps[n + 1].get("signature") if n + 1 < len(steps) else None
        if a["type"] == "click" and a.get("tag") in ("input", "textarea", "select") and after == s.get("signature"):
            continue
        # By the name the person's log uses: the aria-label first, as the study page's harness does.
        label = named_as(thing(a.get("aria") or a.get("original") or a.get("text")), fields)
        if a["type"] == "type" and label.startswith("name"):
            named = thing(a.get("value"))
        _add(out, "do " + (NAMED if named and label == named else label))
    return out


def read_run(run_dir: Path | str) -> dict[str, Any]:
    folder = Path(run_dir)
    return {"summary": json.loads((folder / "summary.json").read_text(encoding="utf-8")),
            "steps": [json.loads(line) for line in (folder / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]}


def _saved(stored: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    rows = (stored or {}).get(key)
    return rows[-1] if isinstance(rows, list) and rows else None


def settings(person: dict[str, Any] | None, engine: dict[str, Any] | None) -> dict[str, Any]:
    """Of the values in what the person finally saved, how many the engine's saved item has too."""
    p = {k: v for k, v in flatten(person or {}).items() if k not in NOT_SETTINGS}
    e = flatten(engine or {})
    alike = [k for k, v in p.items() if k in e and same(e[k], v)]
    return {"fields": len(p), "same": len(alike), "share": round(len(alike) / len(p), 3) if p else 0.0,
            "different": {k: {"person": p[k], "engine": e.get(k)} for k in p if k not in alike}}


def compare_run(person: dict[str, Any], run: dict[str, Any], key: str | None = None, fields: Iterable[str] = ()) -> dict[str, Any]:
    """key: where the product keeps what was saved; by default the first thing either side stored."""
    human, engine = person_moves(person["events"], fields), engine_moves(run["steps"], fields)
    result = compare(human, engine)
    key = key or next(iter(run["summary"].get("stored") or person.get("product") or {}), None)
    last = (run["summary"].get("last_saved") or {}).get(key)
    result["settings"] = settings(_saved(person.get("product"), key), last or _saved(run["summary"].get("stored"), key))
    result["person_moves"], result["engine_moves"] = human, engine
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare an engine run with the person's participant file")
    parser.add_argument("--person", required=True, help="the participant file")
    parser.add_argument("--engine", required=True, help="the run's folder")
    args = parser.parse_args(argv)
    person, run = load(args.person), read_run(args.engine)
    r = compare_run(person, run)
    c, o, f, st = r["content"], r["order"], r["first_touch_order"], r["settings"]
    print(f"Content: {c['recall']:.0%} of what the person touched; precision {c['precision']:.0%}")
    print(f"Order: {o['share_of_person']:.0%}; direction: {f['share_of_person']:.0%}; saved settings: {st['same']} of {st['fields']}")
    print("\n".join(side_by_side(r["person_moves"], r["engine_moves"], r["pairs"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
