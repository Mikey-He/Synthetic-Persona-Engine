"""Several seeded runs of the same cards, and what they add up to (engine-design.md 4.9).

One run of a card is one possible session. With fatigue, distraction and the other slips
drawn from a seed, a card is run several times and the results are counted: how many runs
passed each of the platform's checks, which defaults were missed, how often each slip came
up and, given the person's own session, how close the runs came to it.

    python -m sue.batch --card studio-ab12 --runs 5
    python -m sue.batch --card aryan --card shared-l3 --runs 5 --like-session <person session id>

Seeds are 1 to --runs, so a batch can be repeated exactly. A v2 card has nothing to draw:
its runs differ only as much as the model's replies do.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from .compare import compare_sessions, save_compare, window
from .config import load_config, load_env, require_env
from .model import gemini_for
from .run import run
from .target import make_target

METRICS = ("content", "precision", "direction", "order", "settings")


def run_metrics(compared: dict[str, Any]) -> dict[str, float]:
    return {
        "content": compared["content"]["recall"],
        "precision": compared["content"]["precision"],
        "direction": compared["first_touch_order"]["share_of_person"],
        "order": compared["order"]["share_of_person"],
        "settings": compared["settings"]["share"],
    }


def aggregate(card: str, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """What the runs of one card add up to."""
    n = len(runs)
    criteria: Counter[str] = Counter()
    failed: Counter[str] = Counter()
    missed: Counter[str] = Counter()
    slips: Counter[str] = Counter()
    stops: Counter[str] = Counter()
    for r in runs:
        ev = r.get("evaluation") or {}
        for name, ok in (ev.get("criteria") or {}).items():
            criteria[name] += 1 if ok else 0
            if not ok:
                failed[name] += 1
        for m in r.get("missed_defaults") or []:
            missed[m.get("original") or m.get("text") or "?"] += 1
        slips.update(r.get("slips") or {})
        stops[r["stop"]["reason"]] += 1
    out: dict[str, Any] = {
        "card": card,
        "runs": n,
        "seeds": [r.get("seed") for r in runs],
        "passed": sum(1 for r in runs if (r.get("evaluation") or {}).get("overall")),
        "checks_passed": {k: criteria[k] for k in sorted(set(criteria) | set(failed))},
        "missed_defaults": dict(missed),
        "slips": dict(slips),
        "stops": dict(stops),
        "actions": round(mean(r["actions"] for r in runs), 1) if runs else 0,
        "run_dirs": [r["dir"] for r in runs],
    }
    with_person = [r["metrics"] for r in runs if r.get("metrics")]
    if with_person:
        out["metrics"] = {k: {"mean": round(mean(m[k] for m in with_person), 3),
                              "min": round(min(m[k] for m in with_person), 3),
                              "max": round(max(m[k] for m in with_person), 3)} for k in METRICS}
    return out


def report(agg: dict[str, Any], person: str | None) -> str:
    """The batch as a short Markdown note."""
    n = agg["runs"]
    lines = [f"## {agg['card']}: {n} runs (seeds {', '.join(map(str, agg['seeds']))})", "",
             f"- Passed the grading: **{agg['passed']} of {n}**"]
    for name, ok in agg["checks_passed"].items():
        lines.append(f"  - {name}: {ok} of {n}")
    if agg["missed_defaults"]:
        lines.append("- Missed defaults: " + "; ".join(f"{k} ({v} of {n})" for k, v in agg["missed_defaults"].items()))
    if agg["slips"]:
        lines.append("- Slips over all runs: " + ", ".join(f"{k} {v}" for k, v in agg["slips"].items()))
    lines.append("- How runs ended: " + ", ".join(f"{k} {v}" for k, v in agg["stops"].items()))
    if agg.get("metrics"):
        lines += ["", f"Against the person's session {person}:", "", "| Measure | Mean | Range |", "|---|---|---|"]
        for k, m in agg["metrics"].items():
            lines.append(f"| {k} | {m['mean']:.0%} | {m['min']:.0%} to {m['max']:.0%} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Several seeded runs of the same cards, counted together")
    parser.add_argument("--card", action="append", required=True, help="a card in data/personas; repeat for more cards")
    parser.add_argument("--runs", type=int, default=5, help="runs per card, seeds 1 to this number (default 5)")
    parser.add_argument("--like-session", help="the person's session id: their window size, and compare every run with it")
    parser.add_argument("--viewport", help="window size, e.g. 1920x955; default from config.toml")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--flow", help="the workflow's flow.json (default paths.flow in config.toml)")
    parser.add_argument("--live", action="store_true", help="write each run's screen and pointer as it goes (the platform's Watch live)")
    args = parser.parse_args(argv)

    config = load_config(flow=args.flow)
    load_env()
    target = make_target(config)
    size = args.viewport
    if args.like_session and target.kind != "uat":
        print("--like-session needs the person's session on the UAT platform", file=sys.stderr)
        return 1
    console = getattr(target, "console", None)
    if args.like_session:
        seen = window(console.events(args.like_session).get(args.like_session, []))
        if not seen or not seen.get("viewport"):
            print(f"Session {args.like_session} has no window size recorded", file=sys.stderr)
            return 1
        size = f"{seen['viewport']['width']}x{seen['viewport']['height']}"
    if size:
        w, h = (int(x) for x in size.lower().split("x"))
        config["platform"]["viewport_width"], config["platform"]["viewport_height"] = w, h
    model = gemini_for(config, require_env("GEMINI_API_KEY"))

    out_dir = Path(config["paths"]["runs"]) / f"batch-{datetime.now():%Y%m%d-%H%M%S}"
    out_dir.mkdir(parents=True, exist_ok=True)
    results, notes = [], []
    for card in args.card:
        runs = []
        for seed in range(1, args.runs + 1):
            print(f"\n##### {card}, run {seed} of {args.runs} (seed {seed})")
            summary = run(card, config, target, model, max_steps=args.max_steps, seed=seed, live=args.live)
            if args.like_session:
                found = compare_sessions(console, config, args.like_session, summary["session"])
                if found:
                    compared = save_compare(Path(summary["dir"]), args.like_session, *found)
                    summary["metrics"] = run_metrics(compared)
            runs.append(summary)
        agg = aggregate(card, runs)
        results.append(agg)
        notes.append(report(agg, args.like_session))
        (out_dir / "batch.json").write_text(json.dumps({"person": args.like_session, "workflow": config["workflow"]["name"],
                                                        "flow": config["workflow"]["file"], "target": target.kind,
                                                        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                                        "runsPerCard": args.runs, "cards": results},
                                                       ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "batch.md").write_text("\n".join(notes), encoding="utf-8")
    print("\n" + "\n".join(notes))
    print(f"Saved to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
