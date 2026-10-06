"""How close a run came to what the real person did (engine-design.md 5, 8 phase 4).

Both sides come from the platform's own event log, so the person's session and the
engine's session are measured with the same ruler. Each event becomes a move: a page
he opened, a section he entered, a control he clicked or a field he changed. The
current value shown on a dropdown is cut off its label ([compare].field_labels), so
"Projects All projects (2)" and "Projects Atlas" are the same control.

A click on the name he gave the budget (the list row) is the same move whatever the
name: each side names it differently.

The numbers that come out:
- content: of the distinct things the person touched, how many the engine touched
  too (recall), and how many of the engine's were also the person's (precision);
- order: the longest run of moves both did in the same order, as a share of the
  person's moves (repeats count, so a person who opens one dropdown three times
  pulls it down);
- first-touch order: the same over the order in which each distinct thing was first
  touched, which is the direction he took, without the repeats;
- settings: of the values in the budget the person finally saved, how many the
  engine's saved budget has too (every field, not only the six the platform grades;
  the name is left out).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from .config import load_config, load_env, platform_url, require_env
from .platform import ResearchConsole

ENGINE = Path(__file__).resolve().parent.parent


def moves(events: Iterable[dict[str, Any]], field_labels: list[str], ignore: list[str]) -> list[str]:
    out: list[str] = []
    named = ""  # the name he typed for the budget
    for e in events:
        kind, target, payload = e.get("type"), e.get("target") or "", e.get("payload") or {}
        if kind == "field_changed" and payload.get("field") == "name":
            named = str(payload.get("newValue") or "").strip()
        if kind == "page_viewed":
            move = "page " + (payload.get("route") or target).split("?")[0]
        elif kind == "step_entered":
            move = "section " + str(payload.get("section") or target)
        elif kind == "control_clicked":
            label = (payload.get("label") or target).strip()
            for name in field_labels:
                if label == name or label.startswith(name + " "):
                    label = name
                    break
            if named and label == named:
                label = "(the budget name they typed)"
            move = "click " + label
        elif kind == "field_changed":
            move = "change " + re.sub(r"\.\d+(?=\.|$)", "", payload.get("field") or target)
        elif kind == "save_succeeded":
            move = "saved"
        elif kind == "completion_declared":
            move = "finished"
        else:
            continue
        if any(re.fullmatch(p, move) for p in ignore):
            continue
        if not out or out[-1] != move:  # typing 1, 10, 100, 1000 is one change
            out.append(move)
    return out


def flatten(value: Any, path: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            out |= flatten(v, f"{path}.{k}" if path else k)
        return out
    if isinstance(value, list):
        return {path: json.dumps(sorted(value, key=lambda x: json.dumps(x, sort_keys=True)), sort_keys=True)}
    return {path: value}


def last_saved(result: dict[str, Any]) -> dict[str, Any] | None:
    budgets = result.get("budgets") or []
    scored = (result.get("scored") or {}).get("budgetId")
    pick = next((b for b in budgets if b.get("id") == scored), budgets[-1] if budgets else None)
    return (pick or {}).get("config")


def settings(person: dict[str, Any] | None, engine: dict[str, Any] | None) -> dict[str, Any]:
    p = {k: v for k, v in flatten(person or {}).items() if k != "name"}
    e = flatten(engine or {})
    same = [k for k in p if k in e and e[k] == p[k]]
    return {"same": len(same), "fields": len(p), "share": round(len(same) / len(p), 3) if p else 0.0,
            "different": {k: {"person": p[k], "engine": e.get(k)} for k in p if k not in same}}


def window(events: Iterable[dict[str, Any]]) -> dict[str, Any] | None:
    """The window size and zoom a session ran in. People resize the window at the start
    (Joy's began at 668 x 932 and was enlarged three times before she started), so this
    is the size that was on screen the longest, from session_started and the
    viewport_changed events that follow it; changes lists every size seen."""
    from datetime import datetime

    def ts(e: dict[str, Any]) -> float:
        return datetime.fromisoformat(str(e.get("client_ts", "")).replace("Z", "+00:00")).timestamp()

    events = [e for e in events if e.get("client_ts")]
    zoom, spans, current, since = None, {}, None, None
    for e in events:
        p = e.get("payload") or {}
        size = None
        if e.get("type") == "session_started":
            zoom, size = p.get("zoom"), p.get("viewport")
        elif e.get("type") == "viewport_changed" and p.get("width"):
            size = {"width": p.get("width"), "height": p.get("height")}
        if size:
            if current:
                key = (current["width"], current["height"])
                spans[key] = spans.get(key, 0.0) + ts(e) - since
            current, since = size, ts(e)
    if not current:
        return None
    key = (current["width"], current["height"])
    spans[key] = spans.get(key, 0.0) + ts(events[-1]) - since
    w, h = max(spans, key=spans.get)
    return {"viewport": {"width": w, "height": h}, "zoom": zoom,
            "changes": [{"width": k[0], "height": k[1], "seconds": round(v, 1)} for k, v in spans.items()]}


def lcs(a: list[str], b: list[str]) -> list[tuple[int, int]]:
    n, m = len(a), len(b)
    t = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            t[i][j] = t[i + 1][j + 1] + 1 if a[i] == b[j] else max(t[i + 1][j], t[i][j + 1])
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        if a[i] == b[j]:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif t[i + 1][j] >= t[i][j + 1]:
            i += 1
        else:
            j += 1
    return pairs


def compare(human: list[str], engine: list[str]) -> dict[str, Any]:
    h, e = set(human), set(engine)
    both = h & e
    recall = len(both) / len(h) if h else 0.0
    precision = len(both) / len(e) if e else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    pairs = lcs(human, engine)
    first_h, first_e = list(dict.fromkeys(human)), list(dict.fromkeys(engine))
    first = lcs(first_h, first_e)
    return {
        "content": {"recall": round(recall, 3), "precision": round(precision, 3), "f1": round(f1, 3),
                    "person_only": sorted(h - e), "engine_only": sorted(e - h)},
        "order": {"in_order": len(pairs), "person_moves": len(human), "engine_moves": len(engine),
                  "share_of_person": round(len(pairs) / len(human), 3) if human else 0.0},
        "first_touch_order": {"in_order": len(first), "person_things": len(first_h),
                              "share_of_person": round(len(first) / len(first_h), 3) if first_h else 0.0},
        "pairs": pairs,
    }


def side_by_side(human: list[str], engine: list[str], pairs: list[tuple[int, int]]) -> list[str]:
    rows, i, j = [], 0, 0
    for pi, pj in pairs + [(len(human), len(engine))]:
        while i < pi or j < pj:
            rows.append(f"  {human[i] if i < pi else '':<44} | {engine[j] if j < pj else ''}")
            i, j = min(i + 1, pi), min(j + 1, pj)
        if pi < len(human):
            rows.append(f"= {human[pi]:<44} | {engine[pj]}")
            i, j = pi + 1, pj + 1
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare an engine run with the person's own session, from the platform logs")
    parser.add_argument("--person", required=True, help="the person's session id")
    parser.add_argument("--engine", required=True, help="the engine's session id, or a run folder under runs/")
    parser.add_argument("--quiet", action="store_true", help="do not print the side-by-side moves")
    args = parser.parse_args(argv)

    config = load_config()
    load_env()
    engine_id, run_dir = args.engine, None
    if (Path(args.engine) / "summary.json").exists() or (ENGINE / "runs" / args.engine / "summary.json").exists():
        run_dir = Path(args.engine) if (Path(args.engine) / "summary.json").exists() else ENGINE / "runs" / args.engine
        engine_id = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["session"]
    console = ResearchConsole(platform_url(config), require_env("ADMIN_PASSWORD"))
    logs = console.events(args.person, engine_id)
    for sid in (args.person, engine_id):
        if sid not in logs:
            print(f"No session {sid} on the platform", file=sys.stderr)
            return 1
    c = config["compare"]
    human = moves(logs[args.person], c["field_labels"], c["ignore"])
    engine = moves(logs[engine_id], c["field_labels"], c["ignore"])
    result = compare(human, engine)
    result["settings"] = settings(last_saved(console.result(args.person)), last_saved(console.result(engine_id)))
    result["windows"] = {"person": window(logs[args.person]), "engine": window(logs[engine_id])}
    if not args.quiet:
        print(f"{'Person':<46} | Engine")
        print("\n".join(side_by_side(human, engine, result["pairs"])))
    content, order = result["content"], result["order"]
    pw, ew = result["windows"]["person"] or {}, result["windows"]["engine"] or {}
    if pw.get("viewport") != ew.get("viewport"):  # zoom is pixel density only; the page lays out by viewport
        v = pw.get("viewport") or {}
        print(f"Note: the two windows differ. Person {v.get('width')}x{v.get('height')} (zoom {pw.get('zoom')}), "
              f"engine {(ew.get('viewport') or {}).get('width')}x{(ew.get('viewport') or {}).get('height')}. "
              f"Run sue.run --like-session {args.person} so the engine uses their window; only then is it a fair comparison.")
    print(f"\nContent: of the {len(set(human))} things the person touched, the engine touched {content['recall']:.0%}; "
          f"of the engine's, the person touched {content['precision']:.0%} (F1 {content['f1']:.0%})")
    print(f"Order: {order['in_order']} of the person's {order['person_moves']} moves done by the engine in the same order "
          f"({order['share_of_person']:.0%}); the engine made {order['engine_moves']} moves")
    first = result["first_touch_order"]
    print(f"Direction (order of first touches): {first['in_order']} of the person's {first['person_things']} things "
          f"in the same order ({first['share_of_person']:.0%})")
    st = result["settings"]
    print(f"Saved settings: {st['same']} of the {st['fields']} values in the person's budget are the same ({st['share']:.0%})"
          + ("; different: " + "; ".join(f"{k} person {v['person']} / engine {v['engine']}" for k, v in st["different"].items())
             if st["different"] else ""))
    print("Only the person: " + "; ".join(content["person_only"]))
    print("Only the engine: " + "; ".join(content["engine_only"]))
    if run_dir:
        out = {k: v for k, v in result.items() if k != "pairs"} | {"person_session": args.person, "person_moves": human, "engine_moves": engine}
        (run_dir / "compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Saved to {run_dir / 'compare.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
