"""Watches runs as they go, and reads finished ones, for a run that has gone wrong (2026-11-01).

A step-by-step record says early what a final score says late: the same moves going round, a save
refused again and again, a rule refusing what the model most wants to do. Costs no model calls.

    python -m sue.watch --since 20261101-120000 --follow      one line per new problem, as they appear
    python -m sue.watch --folders runs/study-core             what is wrong in runs already made
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROUND_MOVES = (2, 3, 4, 5, 6)  # lengths of a round of moves worth looking for
ROUNDS = 3  # the same round this many times running is going round, not trying again
REFUSED = 3  # final button pressed this many times
BLOCKED_HOPE = 7  # what the model much wants
BLOCKED_TIMES = 3  # refused by the same rule this many times
LONG_RUN = 100  # steps; the longest person made 68 moves
FINAL = {"finish", "save", "submit", "create", "done"}


def moves_of(steps: Iterable[dict[str, Any]]) -> list[str]:
    return [f"{(s.get('action') or {}).get('type')}:{(s.get('action') or {}).get('text') or (s.get('action') or {}).get('value')}"
            for s in steps if s.get("action")]


def going_round(moves: list[str]) -> tuple[int, list[str]] | None:
    """The same round of moves, several times running, at the end of what has been done so far."""
    for size in ROUND_MOVES:
        if len(moves) < size * ROUNDS:
            continue
        tail = moves[-size:]
        if len(set(tail)) > 1 and all(moves[-size * (i + 1):len(moves) - size * i] == tail for i in range(ROUNDS)):
            return size, tail
    return None


def problems(steps: list[dict[str, Any]], summary: dict[str, Any] | None = None) -> list[tuple[str, str]]:
    """(kind, what happened). kind is unique per run, so a problem is told once."""
    out: list[tuple[str, str]] = []
    if not steps:
        return out
    # Over every point of the run, not only its end: a round it later left still happened.
    moves = moves_of(steps)
    for end in range(len(moves), 0, -1):
        found = going_round(moves[:end])
        if found:
            out.append(("going_round", f"the same {found[0]} moves {ROUNDS} times running, up to move {end}: {' > '.join(found[1])}"))
            break
    pressed = [s["step"] for s in steps if str((s.get("action") or {}).get("text") or "").strip().lower() in FINAL]
    if len(pressed) >= REFUSED:
        out.append(("final_again", f"the final button pressed {len(pressed)} times, at steps {pressed}"))
    blocked: Counter = Counter()
    for s in steps:
        for c in s.get("candidates") or []:
            hope = c.get("hope")
            if c.get("dropped") and isinstance(hope, (int, float)) and hope >= BLOCKED_HOPE and c.get("purpose") in ("advance", "fix"):
                blocked[c["dropped"]] += 1
    for rule, n in blocked.items():
        if n >= BLOCKED_TIMES:
            out.append((f"blocked:{rule}", f"a rule refused what the model most wanted {n} times: {rule}"))
    if len(steps) > LONG_RUN:
        out.append(("long", f"more than {LONG_RUN} steps"))
    errors = sum(bool((s.get("model") or {}).get("error")) for s in steps)
    if errors >= 3:
        out.append(("model_errors", f"{errors} steps with a model error"))
    if summary:
        reason = summary["stop"]["reason"]
        if reason != "completion_declared":
            out.append(("ended", f"ended by {reason}: {str(summary['stop'].get('why'))[:160]}"))
        elif not (summary.get("evaluation") or {}).get("overall"):
            out.append(("wrong", f"said done, not right: {(summary.get('evaluation') or {}).get('criteria')}"))
    return out


def read(run: Path) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    steps = []
    file = run / "steps.jsonl"
    if file.exists():
        for line in file.read_text(encoding="utf-8").splitlines():
            try:
                steps.append(json.loads(line))
            except ValueError:  # the line being written
                break
    done = run / "summary.json"
    return steps, json.loads(done.read_text(encoding="utf-8")) if done.exists() else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Problems in runs, as they go or after")
    parser.add_argument("--runs", default="runs", help="the folder of runs")
    parser.add_argument("--since", help="only runs named from this time on, such as 20261101-120000")
    parser.add_argument("--folders", nargs="+", help="study folders to read once; their runs are listed in study.json")
    parser.add_argument("--follow", action="store_true", help="keep watching until --expect runs have ended")
    parser.add_argument("--expect", type=int, default=0, help="how many runs make up what is being watched")
    args = parser.parse_args(argv)
    if args.folders:
        counts: Counter = Counter()
        for folder in args.folders:
            for path in sorted(Path(folder).rglob("study.json")):
                for p in json.loads(path.read_text(encoding="utf-8"))["people"]:
                    for r in p["runs"]:
                        if Path(r["dir"]).exists():
                            for kind, text in problems(*read(Path(r["dir"]))):
                                counts[kind.split(":")[0]] += 1
                                print(f"{p['name']} seed {r['seed']}: {text}", flush=True)
        print(dict(counts))
        return 0
    told: set[tuple[str, str]] = set()
    finished: set[str] = set()
    while True:
        runs = [d for d in Path(args.runs).glob("2*-*") if d.is_dir() and (not args.since or d.name >= args.since)]
        for run in sorted(runs):
            steps, summary = read(run)
            for kind, text in problems(steps, summary):
                if (run.name, kind) not in told:
                    told.add((run.name, kind))
                    print(f"ALERT {run.name} step {len(steps)}: {text}", flush=True)
            if summary and run.name not in finished:
                finished.add(run.name)
                ev = (summary.get("evaluation") or {}).get("overall")
                print(f"ENDED {run.name} after {len(steps)} steps: {summary['stop']['reason']}, right: {ev} ({len(finished)} ended)", flush=True)
        if not args.follow or (args.expect and len(finished) >= args.expect):
            return 0
        time.sleep(20)


if __name__ == "__main__":
    sys.exit(main())
