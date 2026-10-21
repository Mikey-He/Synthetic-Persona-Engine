"""Where in the task each engine step happened, and what went wrong at each step of the task.

The engine records its own steps (steps.jsonl); a researcher thinks in the steps of the task
(flow.json steps). An engine step is placed on a task step by literal evidence only: the knowledge
items and words it relied on (each belongs to a task step), and the control's own text found in a
step's sentence. Progress moves forward; it goes back only when the control's text names an
earlier step. A step with no evidence stays where the person was.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

FINISHED = ("i'm finished", "i am finished")


def png_size(path: Path) -> tuple[int, int] | None:
    """Width and height from a PNG's header, so the page can show the part of a screen that matters."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
        return (int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")) if head[1:4] == b"PNG" else None
    except OSError:
        return None


def norm(text: Any) -> str:
    t = re.sub(r"[*•]+", " ", str(text or "")).lower()
    t = re.sub(r"\s+\d+\s*$", "", t)  # "Percent of budget 1" is the first of a list
    return re.sub(r"\s+", " ", t).strip(" .:")


def contains(sentence: str, phrase: str) -> bool:
    return len(phrase) >= 2 and re.search(r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])", sentence) is not None


class Placer:
    def __init__(self, flow: dict[str, Any]):
        self.steps = flow.get("steps") or []
        self.index = {s["id"]: i for i, s in enumerate(self.steps)}
        self.item_step = {i["id"]: self.index[i["step"]] for i in flow.get("items") or [] if i.get("step") in self.index}
        self.word_steps: dict[str, set[int]] = {}
        for i in flow.get("items") or []:
            if i.get("kind") == "word" and i.get("step") in self.index:
                self.word_steps.setdefault(norm(i["text"]), set()).add(self.index[i["step"]])
        self.sentences = [norm(f"{s.get('action', '')} {s.get('defaults', '')}") for s in self.steps]

    def named_by(self, text: Any) -> set[int]:
        """Task steps whose sentence names this control."""
        t = norm(text)
        if not t:
            return set()
        if t in FINISHED:
            return {len(self.steps) - 1}
        return {i for i, s in enumerate(self.sentences) if contains(s, t)}

    def place(self, rows: list[dict[str, Any]]) -> list[int]:
        cur, out = 0, []
        for row in rows:
            action = row.get("action") or {}
            chosen = [c for c in row.get("candidates") or [] if c.get("element") == action.get("element")]
            evidence: set[int] = set()
            for c in chosen:
                for e in c.get("evidence") or []:
                    ref = e.get("ref")
                    if e.get("type") == "item" and ref in self.item_step:
                        evidence.add(self.item_step[ref])
                    elif e.get("type") == "word":
                        evidence |= self.word_steps.get(norm(ref), set())
            named = self.named_by(action.get("original") or action.get("text"))
            if action.get("type") == "type":  # the value typed, when the step's sentence names it ("enter 1000")
                named |= self.named_by(action.get("value"))
            ahead = [i for i in evidence | named if i >= cur]
            if ahead:
                cur = min(ahead)
            elif named:  # the control names an earlier step: they went back to it
                cur = max(named)
            out.append(cur)
        return out

    def step_of_text(self, text: Any, fallback: int) -> int:
        named = self.named_by(text)
        return min(named, key=lambda i: abs(i - fallback)) if named else fallback


def read_rows(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "steps.jsonl"
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def why_of(row: dict[str, Any]) -> str:
    a = row.get("action") or {}
    return next((c.get("why") or "" for c in row.get("candidates") or [] if c.get("element") == a.get("element")), "")


def did_of(row: dict[str, Any]) -> str:
    a = row.get("action") or {}
    kind, text, value = a.get("type") or "", a.get("original") or a.get("text") or "", a.get("value")
    if kind == "type":
        return f"Typed “{value}” into {text}" if value not in (None, "") else f"Typed into {text}"
    if kind == "scroll":
        return "Scrolled to look further"
    if kind == "back":
        return "Went back"
    return f"{kind.capitalize()} {text}".strip() if kind else "Looked at the page"


def journey(flow: dict[str, Any], run_dir: Path, url: str, baseline: list[int] | None = None) -> dict[str, Any]:
    """One run, step by step of the task: what the person did there and what went wrong.
    baseline: how many actions the full card took at each step; clearly more counts as hesitating."""
    placer = Placer(flow)
    n = len(placer.steps)
    rows = read_rows(run_dir)
    s = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")) if (run_dir / "summary.json").exists() else {}
    where = placer.place(rows)
    per = [{"moves": [], "wrong": 0, "backs": 0, "slips": 0, "looks": 0, "missed": [], "failed": [], "stopped": False} for _ in range(n)]
    prev = {"wrong": 0, "backs": 0}
    for row, at in zip(rows, where):
        st = row.get("state") or {}
        a = row.get("action") or {}
        p = per[at]
        p["wrong"] += max(0, (st.get("wrong") or 0) - prev["wrong"])
        p["backs"] += max(0, (st.get("backs") or 0) - prev["backs"])
        prev = {"wrong": st.get("wrong") or 0, "backs": st.get("backs") or 0}
        p["slips"] += 1 if a.get("misclick") else 0
        p["looks"] += len(row.get("looks") or []) + (1 if a.get("type") == "scroll" else 0)
        p["moves"].append({"n": row.get("step"), "did": did_of(row), "why": why_of(row), "rule": row.get("rule") or "",
                           "shot": f"{url}/{row['screenshot']}" if row.get("screenshot") else None,
                           "size": png_size(run_dir / row["screenshot"]) if row.get("screenshot") else None,
                           "box": a.get("box"), "misclick": bool(a.get("misclick")), "route": row.get("route")})
    for m in s.get("missed_defaults") or []:
        at = where[m["step"] - 1] if m.get("step") and m["step"] - 1 < len(where) else n - 1
        per[placer.step_of_text(m.get("original") or m.get("text"), at)]["missed"].append(
            {"text": m.get("original") or m.get("text"), "why": m.get("why") or ""})
    ev = s.get("evaluation") or {}
    labels = ((flow.get("engine") or {}).get("grading")) or {}
    steps_of = ((flow.get("engine") or {}).get("gradingSteps")) or {}
    ignored = set(ev.get("ignored") or ((flow.get("engine") or {}).get("gradingIgnored")) or [])
    for k, ok in (ev.get("criteria") or {}).items():
        if not ok and k not in ignored:
            at = placer.index.get(steps_of.get(k), n - 1)
            per[at]["failed"].append({"key": k, "text": labels.get(k, k), "detail": ((ev.get("details") or {}).get(k)) or ""})
    stop = s.get("stop") or {}
    reached = max(where) if where else -1
    if stop.get("reason") and stop["reason"] != "completion_declared" and n:
        per[where[-1] if where else 0]["stopped"] = True
    out = []
    for i, p in enumerate(per):
        base = baseline[i] if baseline and i < len(baseline) else None
        long = base is not None and len(p["moves"]) >= max(2 * base, base + 3)
        status = ("stopped" if p["stopped"] else "wrong" if p["missed"] or p["failed"]
                  else "hesitated" if p["wrong"] or p["backs"] or p["slips"] or long else "ok" if i <= reached else "skipped")
        out.append({**p, "status": status})
    return {"steps": out, "passed": bool(ev.get("overall")), "stop": stop, "seconds": s.get("seconds"),
            "actions": s.get("actions"), "report": f"{url}/report.html" if (run_dir / "report.html").exists() else None}


def full_run(flow: dict[str, Any], runs: Path) -> Path | None:
    """The latest run of the full card on this task."""
    for d in sorted((p for p in runs.iterdir() if p.is_dir() and p.name.endswith("-full")), reverse=True):
        try:
            run = (d / "run.json").read_text(encoding="utf-8")
        except OSError:
            continue
        if flow.get("name") and flow["name"] in run and read_rows(d):
            return d
    return None


def baseline(flow: dict[str, Any], runs: Path) -> list[int] | None:
    """How many actions the full card took at each step of the task."""
    d = full_run(flow, runs)
    if not d:
        return None
    where = Placer(flow).place(read_rows(d))
    return [where.count(i) for i in range(len(flow.get("steps") or []))]


def storyboard(flow: dict[str, Any], runs: Path) -> list[dict[str, Any] | None]:
    """A screenshot for each task step, from the latest run of the full card on this task, with
    where on it the step's control is."""
    name = flow.get("name")
    for d in sorted((p for p in runs.iterdir() if p.is_dir() and p.name.endswith("-full")), reverse=True):
        run = {}
        try:
            run = json.loads((d / "run.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if name not in json.dumps(run, ensure_ascii=False):
            continue
        rows = read_rows(d)
        if not rows:
            continue
        where = Placer(flow).place(rows)
        shots: list[dict[str, Any] | None] = [None] * len(flow.get("steps") or [])
        for row, at in zip(rows, where):
            if shots[at] is None and row.get("screenshot"):
                shots[at] = {"url": f"/runs/{d.name}/{row['screenshot']}", "size": png_size(d / row["screenshot"]),
                             "box": (row.get("action") or {}).get("box") or row.get("focus_rect")}
        if sum(1 for x in shots if x) >= len(shots) // 2:
            return shots
    return [None] * len(flow.get("steps") or [])
