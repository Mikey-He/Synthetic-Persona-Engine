"""Runs every participant's card and compares at two levels (2026-10-31).

Each person: the engine's runs at that person's window, against that person's file. The group:
how often each thing was done, how often each check passed, among the people and among the runs.
The group level is what a team without participants would rely on, so it is reported on its own.

    python -m sue.study --flow <flow.json> --participants <folder> --runs 5 --watch
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import Counter
from math import log2, sqrt
from statistics import mean, median
from typing import Any, Iterable

from .batch import METRICS
from .compare import compare
from .config import load_config, load_env, require_env
from .model import gemini_for
from .participant import compare_run, engine_window, load, person_moves, read_run, thing
from .events import person_trouble, run_trouble
from .parts import MEASURES, engine_parts, pass_bounds, person_parts, read_steps, scorecard, verdict
from .run import run
from .target import json_check, make_target


def card_of(personas: Path, name: str, flow: str) -> str | None:
    """The card made from this person's file: Persona Studio saves it under the code name."""
    for path in sorted(personas.glob("studio-*.json")):
        card = json.loads(path.read_text(encoding="utf-8"))
        if card.get("persona", {}).get("name") == name and card.get("flow") == flow:
            return path.stem
    return None


def person_checks(person: dict[str, Any], success: list[dict[str, Any]]) -> dict[str, bool]:
    """The person graded by the checks that grade the engine."""
    out = {}
    for check in success:
        if check.get("type") == "storage":
            out[check["name"]] = json_check((person.get("product") or {}).get(check["key"]), check)[0]
    return out


def metrics(compared: dict[str, Any]) -> dict[str, float]:
    return {"content": compared["content"]["recall"], "precision": compared["content"]["precision"],
            "direction": compared["first_touch_order"]["share_of_person"],
            "order": compared["order"]["share_of_person"], "settings": compared["settings"]["share"]}


def shares(sets: list[set[str]]) -> dict[str, float]:
    """The share of these sessions in which each thing was done."""
    return {t: sum(t in s for s in sets) / len(sets) for t in set().union(*sets)} if sets else {}


def usable(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A run the tooling broke says nothing about the person. Kept in study.json, left out of the rates."""
    return [r for r in runs if r.get("stop") != "technical_error"]


def passed(evaluation: dict[str, Any], stop: str) -> bool:
    """Right, and they said they were done, as the person did. A run that never finished has not passed."""
    return bool(evaluation.get("overall")) and stop == "completion_declared"


def group(people: list[dict[str, Any]]) -> dict[str, Any]:
    """The people against the runs. Each person's runs count together as one synthetic person, so a
    person with more runs does not weigh more."""
    # Only people with a run behind them, so that the two sides of every rate are the same people.
    people = [{**p, "runs": usable(p["runs"])} for p in people if usable(p["runs"])] or people
    human = shares([set(p["moves"]) for p in people])
    per_person = [shares([set(r["moves"]) for r in p["runs"]]) for p in people if p["runs"]]
    things = set(human).union(*per_person) if per_person else set(human)
    engine = {t: mean(s.get(t, 0.0) for s in per_person) for t in things} if per_person else {}
    rows = [{"thing": t, "people": round(human.get(t, 0.0), 3), "runs": round(engine.get(t, 0.0), 3)} for t in things]
    rows.sort(key=lambda r: (-abs(r["people"] - r["runs"]), r["thing"]))
    checks = sorted({c for p in people for c in p["checks"]})
    return {
        "people": len(people),
        "runs": sum(len(p["runs"]) for p in people),
        "passed": {"people": round(mean(all(p["checks"].values()) for p in people), 3),
                   "runs": round(mean(mean(bool(r["passed"]) for r in p["runs"]) for p in people if p["runs"]), 3) if per_person else None},
        "checks": [{"check": c, "people": round(mean(bool(p["checks"].get(c)) for p in people), 3),
                    "runs": round(mean(mean(bool(r["checks"].get(c)) for r in p["runs"]) for p in people if p["runs"]), 3) if per_person else None}
                   for c in checks],
        "things": rows,
        "mean_gap": round(mean(abs(r["people"] - r["runs"]) for r in rows), 3) if rows else None,
    }


def draws_note(runs: list[dict[str, Any]]) -> str:
    """With no random draws the seeds did nothing: the repeats differ only by the model."""
    if not runs:
        return "n/a"
    draws = [r.get("draws") or 0 for r in runs]
    return "none: repeats differ only by the model" if not any(draws) else f"{min(draws)} to {max(draws)}"


def shape(moves: list[str], entry: Iterable[str] = ()) -> dict[str, int]:
    """The shape of a session, whatever the path: how long, how long before starting the task itself,
    and how much of it went back to something already done."""
    starts = {"do " + thing(x) for x in entry}
    before = next((i for i, m in enumerate(moves) if m in starts), len(moves))
    return {"moves": len(moves), "before the task": before, "repeats": len(moves) - len(set(moves))}


def _steps(sessions: list[list[str]]) -> Counter:
    """Each step from one thing to the next, each session counting the same however long."""
    out: Counter = Counter()
    for moves in sessions:
        pairs = list(zip(moves, moves[1:]))
        for pair in pairs:
            out[pair] += 1 / len(pairs)
    return out


def step_distance(a: list[list[str]], b: list[list[str]]) -> float:
    """How far apart two groups' steps from one thing to the next are: 0 the same, 1 nothing in common
    (Jensen-Shannon distance, base 2)."""
    p, q = _steps(a), _steps(b)
    tp, tq = sum(p.values()) or 1, sum(q.values()) or 1
    total = 0.0
    for k in set(p) | set(q):
        x, y = p[k] / tp, q[k] / tq
        m = (x + y) / 2
        total += (x * log2(x / m) if x else 0) + (y * log2(y / m) if y else 0)
    return round(sqrt(total / 2), 3)


def strangers(people: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """How like each person another real person is: what a card made for this person has to beat. Two
    real people differ a lot, so a path score has no meaning without this."""
    out: dict[str, dict[str, float]] = {}
    for p in people:
        rows = [compare(p["moves"], o["moves"]) for o in people if o is not p]
        if rows:
            out[p["name"]] = {"content": mean(r["content"]["recall"] for r in rows), "direction": mean(r["first_touch_order"]["share_of_person"] for r in rows),
                              "order": mean(r["order"]["share_of_person"] for r in rows)}
    return out


def shapes_note(people: list[dict[str, Any]], entry: list[str]) -> list[str]:
    """The group's distribution: the people against the runs, then each person against their own runs
    and against other people."""
    ran = [p for p in people if usable(p["runs"])]
    if not ran:
        return []
    humans = [shape(p["moves"], entry) for p in ran]
    runs = [shape(r["moves"], entry) for p in ran for r in usable(p["runs"])]
    spread = lambda rows, k: f"{median(r[k] for r in rows):.0f} ({min(r[k] for r in rows)} to {max(r[k] for r in rows)})"  # noqa: E731
    lines = ["", "## How sessions looked", "", "Median (lowest to highest).", "", "| | People | Runs |", "|---|---|---|"]
    lines += [f"| {k} | {spread(humans, k)} | {spread(runs, k)} |" for k in humans[0]]
    entries = Counter(p["moves"][0] for p in ran if p["moves"])
    entered = Counter(r["moves"][0] for p in ran for r in usable(p["runs"]) if r["moves"])
    lines += ["", f"First move. People: {dict(entries)}. Runs: {dict(entered)}.",
              f"Steps from one thing to the next, distance between the people and the runs (0 the same, 1 nothing in common): "
              f"{step_distance([p['moves'] for p in ran], [r['moves'] for p in ran for r in usable(p['runs'])])}."]
    known = strangers(ran)
    lines += ["", "## Each person: their runs, another real person", "",
              "| Person | content | direction | order | Their moves within their runs? | Before the task within their runs? |", "|---|---|---|---|---|---|"]
    for p in ran:
        got, other = usable(p["runs"]), known.get(p["name"])
        cell = lambda k: f"{mean(r['metrics'][k] for r in got):.0%} / {other[k]:.0%}" if other else "n/a"  # noqa: E731
        mine, theirs = shape(p["moves"], entry), [shape(r["moves"], entry) for r in got]
        inside = lambda k: "yes" if min(t[k] for t in theirs) <= mine[k] <= max(t[k] for t in theirs) else "no"  # noqa: E731
        lines.append(f"| {p['name']} | {cell('content')} | {cell('direction')} | {cell('order')} | {inside('moves')} | {inside('before the task')} |")
    return lines


def scorecard_note(people: list[dict[str, Any]]) -> list[str]:
    """The answer to the study's question, first: part by part, how the runs differ from the people."""
    ran = [p for p in people if p.get("parts") and [r for r in usable(p["runs"]) if r.get("parts")]]
    if len(ran) < 2:
        return []
    card = scorecard([p["parts"] for p in ran], [[r["parts"] for r in usable(p["runs"]) if r.get("parts")] for p in ran])
    pct = lambda x: f"{x:.0%}"  # noqa: E731
    most = lambda row: max(row, key=row.get)  # noqa: E731
    lines = ["## Scorecard: where the runs differ from the people, part by part", "",
             f"Agreement on which part is larger, over every two parts: **{pct(card['overall'])}** (standard: about 70%).", "",
             "| Measure | Agreement | People: largest part | Runs: largest part |", "|---|---|---|---|"]
    lines += [f"| {title} | {pct(card['group'][key])} | {most(card['people'][key])} | {most(card['runs'][key])} |" for key, title, _ in MEASURES]
    lines += ["", "| Part | Time: people / runs | Moves: people / runs | Chance of going wrong: people / runs |", "|---|---|---|---|"]
    for part in card["people"]["seconds"]:
        lines.append("| " + part + " | " + " | ".join(f"{pct(card['people'][key][part])} / {pct(card['runs'][key][part])}" for key, _, _ in MEASURES) + " |")
    lines += ["", "| Person | Agreement with their own runs | With another real person |", "|---|---|---|"]
    lines += [f"| {p['name']} | {pct(e['own'])} | {pct(e['stranger'])} |" for p, e in zip(ran, card["each"])]
    return lines + [""]


def parts_note(people: list[dict[str, Any]]) -> list[str]:
    """The measure of success: the people against the runs, part by part (sue.parts). A study made
    before this was recorded has none until it is reported with --participants."""
    ran = [p for p in people if p.get("parts") and [r for r in usable(p["runs"]) if r.get("parts")]]
    if len(ran) < 2:
        return []
    pct = lambda x: f"{x:.0%}"  # noqa: E731
    low, high = pass_bounds(sum(all(p["checks"].values()) for p in ran), len(ran))
    rate = mean(mean(bool(r["passed"]) for r in usable(p["runs"])) for p in ran)
    totals = [sum(p["parts"]["moves"].values()) for p in ran]
    runs_total = median(sum(r["parts"]["moves"].values()) for p in ran for r in usable(p["runs"]))
    lines = ["", "## Where the effort goes: the measure of success", "",
             "Bounds are what these people allow (resampled, 90%, widened by one move). Within them, the runs cannot be told from the people; with this few people it means no more than that.", "",
             f"- Passed: runs {pct(rate)}, allowed {pct(low)} to {pct(high)}: {'yes' if low <= rate <= high else 'NO'}",
             f"- Moves in a session: runs {runs_total:.0f} (median), people {min(totals)} to {max(totals)}: {'yes' if min(totals) <= runs_total <= max(totals) else 'NO'}"]
    for key, title in (("moves", "Moves"), ("seconds", "Time (runs estimated from what they read and did)"), ("repeats", "Going back to what they had done")):
        got = verdict([p["parts"][key] for p in ran], [[r["parts"][key] for r in usable(p["runs"]) if r.get("parts")] for p in ran])
        lines += ["", f"### {title}", "", "| Part | People | Allowed | Runs | Within? |", "|---|---|---|---|---|"]
        lines += [f"| {part} | {pct(v['people'])} | {pct(v['low'])} to {pct(v['high'])} | {pct(v['runs'])} | {'yes' if v['inside'] else 'NO'} |" for part, v in got["rows"].items()]
        lines += ["", f"Largest two. People: {', '.join(got['top_people'])} (in {pct(got['top_stable'])} of resampled groups). Runs: {', '.join(got['top_runs'])}."]
    return lines


def add_parts(people: list[dict[str, Any]], participants: str, config: dict[str, Any]) -> None:
    """The parts of a study made before they were recorded, from its files."""
    parts, commit = config["compare"].get("parts") or [], config["run"].get("commit_labels") or []
    files = {}
    for f in sorted(Path(participants).glob("participant-*.json")):
        person = load(f)
        files[person["questionnaire"]["answers"]["name"]] = person
    for p in people:
        if p["name"] in files:
            p["parts"] = person_parts(files[p["name"]]["events"], parts)
            p["parts"]["troubles"] = person_trouble(files[p["name"]], config)
        for r in p["runs"]:
            if Path(r["dir"], "steps.jsonl").exists():
                r["parts"] = engine_parts(read_steps(r["dir"]), parts, commit)
                summary = json.loads(Path(r["dir"], "summary.json").read_text(encoding="utf-8")) if Path(r["dir"], "summary.json").exists() else {}
                r["parts"]["troubles"] = run_trouble(r["dir"], summary, config)


def report(folders: list[str], out: Path, entry: list[str], participants: str | None = None, config: dict[str, Any] | None = None) -> Path:
    """One report from several study folders (each person run in their own process)."""
    people: list[dict[str, Any]] = []
    for folder in folders:
        people += json.loads((Path(folder) / "study.json").read_text(encoding="utf-8"))["people"]
    by_name: dict[str, dict[str, Any]] = {}
    for p in people:  # a person run in parts keeps every run; a seed run again counts its last run
        kept = by_name.setdefault(p["name"], {**p, "runs": []})
        kept["runs"] = [r for r in kept["runs"] if r["seed"] not in {x["seed"] for x in p["runs"]}] + p["runs"]
    people = sorted(by_name.values(), key=lambda p: p["name"])
    if participants and config:
        add_parts(people, participants, config)
    g = group(people)
    out.mkdir(parents=True, exist_ok=True)
    (out / "study.json").write_text(json.dumps({"people": people, "group": g}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "study.md").write_text(note(people, g, entry), encoding="utf-8")
    return out


def note(people: list[dict[str, Any]], g: dict[str, Any], entry: list[str] = ()) -> str:
    pct = lambda x: "n/a" if x is None else f"{x:.0%}"  # noqa: E731
    lines = ["# Participants against the engine", "", *scorecard_note(people), "## Each person", "",
             "| Person | Person passed | Runs passed | How runs ended | Said done, not right | Random draws | " + " | ".join(METRICS) + " |",
             "|---|---|---|---|---|---|" + "---|" * len(METRICS)]
    for p in people:
        runs = usable(p["runs"])
        got = [r["metrics"] for r in runs]
        cells = [pct(mean(m[k] for m in got)) if got else "n/a" for k in METRICS]
        ended = ", ".join(f"{n} {k}" for k, n in sorted(Counter(r.get("stop") for r in p["runs"]).items()))
        false_done = sum(r.get("stop") == "completion_declared" and not r["passed"] for r in runs)
        lines.append(f"| {p['name']} | {'yes' if all(p['checks'].values()) else 'no'} | "
                     f"{sum(bool(r['passed']) for r in runs)} of {len(runs)} | {ended} | {false_done} | {draws_note(runs)} | " + " | ".join(cells) + " |")
    lines += ["", "## The group", "", f"{g['people']} people, {g['runs']} runs. Passed: people {pct(g['passed']['people'])}, runs {pct(g['passed']['runs'])}.", "",
              "| Check | People | Runs |", "|---|---|---|"]
    lines += [f"| {c['check']} | {pct(c['people'])} | {pct(c['runs'])} |" for c in g["checks"]]
    lines += ["", f"How often each thing was done, widest gaps first (mean gap {pct(g['mean_gap'])}):", "",
              "| Thing | People | Runs |", "|---|---|---|"]
    lines += [f"| {r['thing']} | {pct(r['people'])} | {pct(r['runs'])} |" for r in g["things"]]
    lines += parts_note(people)
    lines += shapes_note(people, list(entry))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Every participant's card, run and compared, one by one and as a group")
    parser.add_argument("--flow", required=True, help="the workflow's flow.json")
    parser.add_argument("--participants", help="the folder of participant files")
    parser.add_argument("--report", nargs="+", help="make one report from these study folders instead of running")
    parser.add_argument("--runs", type=int, default=5, help="runs per person, seeds 1 to this number (default 5)")
    parser.add_argument("--only", action="append", help="a participant id, such as 001; repeat for more (default all)")
    parser.add_argument("--watch", action="store_true", help="show every run in a window, live")
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--seeds", help="which seeds, such as 3 or 1,2,3, instead of 1 to --runs")
    args = parser.parse_args(argv)

    config = load_config(flow=args.flow)
    entry = config["compare"].get("entry") or []
    if args.report:
        print(report(args.report, Path(config["paths"]["runs"]) / f"study-report-{datetime.now():%Y%m%d-%H%M%S}", entry, args.participants, config))
        return 0
    if not args.participants:
        parser.error("--participants is needed to run")
    load_env()
    target = make_target(config)
    model = gemini_for(config, require_env("GEMINI_API_KEY"))
    success = config["workflow"]["target"]["success"]
    personas = Path(config["paths"]["personas"])
    # With the process id: people run side by side start in the same second.
    out_dir = Path(config["paths"]["runs"]) / f"study-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}"
    out_dir.mkdir(parents=True, exist_ok=True)

    people = []
    for path in sorted(Path(args.participants).glob("participant-*.json")):
        person = load(path)
        pid = person["session"]["participantId"]
        if args.only and pid not in args.only:
            continue
        name = person["questionnaire"]["answers"]["name"]
        card = card_of(personas, name, config["workflow"]["name"])
        if not card:
            print(f"{name}: no card yet; import {path.name} in Persona Studio first", file=sys.stderr)
            return 1
        w, h = (int(x) for x in engine_window(person).split("x"))
        config["platform"]["viewport_width"], config["platform"]["viewport_height"] = w, h
        row: dict[str, Any] = {"name": name, "card": card, "window": f"{w}x{h}", "moves": person_moves(person["events"], config["compare"]["field_labels"]),
                                 "parts": person_parts(person["events"], config["compare"].get("parts") or []),
                                 "checks": person_checks(person, success), "runs": []}
        for seed in [int(x) for x in args.seeds.split(",")] if args.seeds else range(1, args.runs + 1):
            print(f"\n##### {name}, seed {seed} (window {w}x{h})")
            summary = run(card, config, target, model, max_steps=args.max_steps, seed=seed, watch=args.watch)
            if "no_credits" in (summary["stop"].get("why") or ""):
                print(f"Stopped: the model's credits ran out ({summary['stop']['why']})", file=sys.stderr)
                return 3
            compared = compare_run(person, read_run(summary["dir"]), fields=config["compare"]["field_labels"])
            (Path(summary["dir"]) / "compare.json").write_text(json.dumps(compared, ensure_ascii=False, indent=2), encoding="utf-8")
            ev = summary.get("evaluation") or {}
            row["runs"].append({"seed": seed, "dir": summary["dir"], "passed": passed(ev, summary["stop"]["reason"]), "checks": ev.get("criteria") or {},
                                  "stop": summary["stop"]["reason"], "draws": summary.get("draws"), "metrics": metrics(compared), "moves": compared["engine_moves"],
                                  "parts": engine_parts(read_steps(summary["dir"]), config["compare"].get("parts") or [], config["run"].get("commit_labels") or [])})
        people.append(row)
        # after each person, so an interrupted study keeps what it has
        g = group(people)
        (out_dir / "study.json").write_text(json.dumps({"people": people, "group": g}, ensure_ascii=False, indent=2), encoding="utf-8")
        (out_dir / "study.md").write_text(note(people, g, entry), encoding="utf-8")
    print(f"\nSaved to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
