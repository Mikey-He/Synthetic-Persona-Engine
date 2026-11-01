"""Where a session's effort goes, part by part (2026-11-01).

What a team needs from a simulated study is where people spend their effort and where they struggle,
not the same clicks in the same order. So a session is cut into the parts of the task: before the
form, each section of the form (flow.json engine.compare.parts), and after the save. For each part:
how many moves, how long, and how many went back to something already done there.

The bounds are not chosen: they are what the people themselves allow (resampling the people, 90%),
widened by the 2 points one move is worth. Passing means the runs cannot be told from the people;
with six people it cannot mean more than that.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime
from math import sqrt
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

from .target import holds

BEFORE, AFTER = "Before the form", "After the save"
ONE_MOVE = 0.02  # a session is about 50 moves; the logs cannot see less
SAMPLES = 5000
# How long a step takes a person, from published values and not fitted to anyone: the keystroke-level
# model (Card, Moran and Newell, 1983) and silent reading speed (Brysbaert, 2019).
THINK_S, POINT_S, PRESS_S, KEY_S, WORDS_PER_S = 1.35, 1.1, 0.2, 0.28, 238 / 60


def names(parts: Iterable[str]) -> list[str]:
    return [BEFORE, *parts, AFTER]


def _when(event: dict[str, Any]) -> float:
    return datetime.fromisoformat(event["clientTs"].replace("Z", "+00:00")).timestamp()


def person_parts(events: Iterable[dict[str, Any]], parts: list[str]) -> dict[str, dict[str, float]]:
    """A participant file's moves, seconds and repeats by part. Typing on in one box is one move."""
    moves, repeats, seconds, seen = Counter(), Counter(), Counter(), Counter()
    rows = [e for e in events if e.get("clientTs")]
    start = next((_when(e) for e in rows if e["type"] == "control_clicked"), None)
    part, saved, last, previous = BEFORE, False, None, None
    for e in rows:
        now = _when(e)
        if last is not None and start is not None and last >= start:
            seconds[part] += now - last
        last = now
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        screen = payload.get("screen")
        if screen:
            part = next((p for p in parts if screen.endswith(p)), AFTER if saved else BEFORE)
        if e["type"] == "save_succeeded":
            saved = True
        if e["type"] in ("control_clicked", "field_changed"):
            key = (e["type"], str(e.get("target")))
            if e["type"] == "field_changed" and key == previous:
                continue
            previous = key
            moves[part] += 1
            repeats[part] += seen[(part, key[1])] > 0
            seen[(part, key[1])] += 1
    return _table(moves, seconds, repeats, parts)


def step_seconds(action: dict[str, Any], words_new: int) -> float:
    """Reads what is new here, decides, and acts."""
    kind = action.get("type")
    act = {"click": POINT_S + PRESS_S, "choose": POINT_S + PRESS_S, "open_help": POINT_S + PRESS_S, "scroll": POINT_S,
           "press": PRESS_S}.get(kind, 0.0)
    if kind == "type":
        act = POINT_S + PRESS_S + KEY_S * len(str(action.get("value") or ""))
    return words_new / WORDS_PER_S + THINK_S + act


def engine_parts(steps: Iterable[dict[str, Any]], parts: list[str], commit: Iterable[str] = ()) -> dict[str, dict[str, float]]:
    """A run's moves, estimated seconds and repeats by part. What the model took to answer is not a
    person's time, so time is estimated from what they read and did. Anything after the last final
    button counts as after the save."""
    rows = list(steps)
    final = {c.lower() for c in commit}
    last = max((i for i, r in enumerate(rows) if str((r.get("action") or {}).get("text") or "").strip().lower() in final), default=None)
    moves, repeats, seconds, seen = Counter(), Counter(), Counter(), Counter()
    read: set[str] = set()
    for i, r in enumerate(rows):
        action = r.get("action") or {}
        signature = (r.get("signature") or "").split("|")
        section = signature[1] if len(signature) > 1 else ""
        part = AFTER if last is not None and i > last else next((p for p in parts if p in section), BEFORE)
        where = "|".join(signature[:3])
        words = r.get("words_seen")
        if words is None:  # a run from before this was recorded: only the names of its controls are known
            words = sum(len(line.split("|")[2].split()) for line in (r.get("prompt") or "").splitlines()
                        if line.startswith("el_") and line.count("|") >= 2)
        # What is new to them takes reading; a run from before this was recorded knows only the page.
        seconds[part] += step_seconds(action, r["words_new"] if "words_new" in r else 0 if where in read else words)
        read.add(where)
        if action.get("type") in ("click", "choose", "type", "press", "open_help"):
            text = str(action.get("text"))
            moves[part] += 1
            repeats[part] += seen[(part, text)] > 0
            seen[(part, text)] += 1
    return _table(moves, seconds, repeats, parts)


def _table(moves: Counter, seconds: Counter, repeats: Counter, parts: list[str]) -> dict[str, dict[str, float]]:
    return {"moves": {p: moves[p] for p in names(parts)}, "seconds": {p: round(seconds[p], 1) for p in names(parts)},
            "repeats": {p: repeats[p] for p in names(parts)}}


def read_steps(run_dir: str | Path) -> list[dict[str, Any]]:
    with open(Path(run_dir) / "steps.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def share(row: dict[str, float]) -> dict[str, float]:
    total = sum(row.values()) or 1
    return {p: v / total for p, v in row.items()}


def group_share(rows: list[dict[str, float]]) -> dict[str, float]:
    """Each session counting the same, however long."""
    return {p: mean(share(r)[p] for r in rows) for p in rows[0]}


def wrong_parts(stored: dict[str, Any] | None, success: list[dict[str, Any]], field_parts: dict[str, str], last: Any = None) -> set[str]:
    """The parts whose saved values are not what the checks ask, so a failed check is narrowed to the
    field that failed it. Of a check's alternatives, the one that comes closest says what was wrong.
    Nothing saved is no wrong value: a run that never saved shows in how often runs pass."""
    out: set[str] = set()
    for check in success:
        rows = (stored or {}).get(check.get("key"))
        if check.get("type") != "storage" or not isinstance(rows, list) or not rows:
            continue
        row = last if last in rows else rows[-1]
        wrong = dict(holds(row, check))
        if check.get("anyOf"):
            misses = [holds(row, alt) for alt in check["anyOf"]]
            wrong.update(min(misses, key=len))
        out |= {field_parts[k] for k in wrong if k in field_parts}
    return out


def trouble(session: dict[str, Any]) -> dict[str, float]:
    """Whether each part went wrong, as sue.events reads it from what happened."""
    went = {t[0] for t in session.get("troubles") or []}
    return {p: float(p in went) for p in session["repeats"]}


def pairs_agree(a: dict[str, float], b: dict[str, float]) -> float:
    """Of every two parts, the share in which both sides say the same one is larger: the question a team
    asks of a simulated study. A tie against a difference counts half."""
    keys = list(a)
    pairs = [(x, y) for i, x in enumerate(keys) for y in keys[i + 1:]]
    sign = lambda v: (v > 0) - (v < 0)  # noqa: E731
    score = lambda s, t: 1.0 if s == t else 0.5 if 0 in (s, t) else 0.0  # noqa: E731
    return mean(score(sign(a[x] - a[y]), sign(b[x] - b[y])) for x, y in pairs) if pairs else 0.0


MEASURES = (("seconds", "Time", share), ("moves", "Moves", share), ("trouble", "Chance of going wrong", lambda row: row))


def _profile(session: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {key: of(trouble(session) if key == "trouble" else session[key]) for key, _, of in MEASURES}


def _mean_rows(rows: list[dict[str, float]]) -> dict[str, float]:
    return {p: mean(r[p] for r in rows) for p in rows[0]}


def scorecard(humans: list[dict[str, Any]], per_person_runs: list[list[dict[str, Any]]]) -> dict[str, Any]:
    """The measure of success (Mikey, 2026-11-01): part by part, how the runs differ from the people, and
    how far they agree on which part takes longest and which goes wrong. Each person's runs count as one
    synthetic person. Each person is also set against their own runs and against other real people."""
    people = [_profile(h) for h in humans]
    runs = [{key: _mean_rows([_profile(r)[key] for r in got]) for key, _, _ in MEASURES} for got in per_person_runs]
    whole_people = {key: _mean_rows([p[key] for p in people]) for key, _, _ in MEASURES}
    whole_runs = {key: _mean_rows([r[key] for r in runs]) for key, _, _ in MEASURES}
    group = {key: pairs_agree(whole_people[key], whole_runs[key]) for key, _, _ in MEASURES}
    each = []
    for i, p in enumerate(people):
        own = mean(pairs_agree(p[key], runs[i][key]) for key, _, _ in MEASURES)
        others = [o for j, o in enumerate(people) if j != i]
        each.append({"own": own, "stranger": mean(pairs_agree(p[key], o[key]) for o in others for key, _, _ in MEASURES) if others else None})
    return {"people": whole_people, "runs": whole_runs, "group": group, "overall": mean(group.values()), "each": each}


def top_two(row: dict[str, float]) -> set[str]:
    return set(sorted(row, key=lambda p: -row[p])[:2])


def people_bounds(rows: list[dict[str, float]], seed: int = 1) -> dict[str, Any]:
    """What these people allow: for each part, the range of the group's share over resampled groups,
    and how often each pair of parts came out on top."""
    rng = random.Random(seed)
    samples = [group_share(rng.choices(rows, k=len(rows))) for _ in range(SAMPLES)]
    bounds = {}
    for p in rows[0]:
        values = sorted(s[p] for s in samples)
        bounds[p] = (max(0.0, values[int(SAMPLES * 0.05)] - ONE_MOVE), min(1.0, values[int(SAMPLES * 0.95)] + ONE_MOVE))
    tops = Counter(frozenset(top_two(s)) for s in samples)
    in_top = Counter(p for s in samples for p in top_two(s))
    return {"bounds": bounds, "top": tops.most_common(1)[0], "in_top": {p: n / SAMPLES for p, n in in_top.items()}}


def pass_bounds(passed: int, people: int, z: float = 1.645) -> tuple[float, float]:
    """What the people's pass rate allows, 90% (Wilson)."""
    p, n = passed / people, people
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def verdict(humans: list[dict[str, float]], per_person_runs: list[list[dict[str, float]]]) -> dict[str, Any]:
    """The people's and the runs' shares of one measure, and whether each part falls within the bounds.
    Each person's runs count together as one synthetic person."""
    known = people_bounds(humans)
    engine = group_share([group_share(runs) for runs in per_person_runs if runs])
    rows = {p: {"people": mean(share(h)[p] for h in humans), "low": known["bounds"][p][0], "high": known["bounds"][p][1],
                "runs": engine[p], "inside": known["bounds"][p][0] <= engine[p] <= known["bounds"][p][1]} for p in engine}
    pair, count = known["top"]
    return {"rows": rows, "top_people": sorted(pair), "top_stable": count / SAMPLES, "top_runs": sorted(top_two(engine)), "in_top": known["in_top"]}
