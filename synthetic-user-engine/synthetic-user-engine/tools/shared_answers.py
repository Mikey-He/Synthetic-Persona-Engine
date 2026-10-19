"""Writes questionnaire answer files for shared cards: one per user type, filled only from a
rough type label (sophistication level 1-5, after the GCBP persona presets), never from any
participant's answers. The files go through the same Persona Builder as personal answers:

    python tools/shared_answers.py
    node tools/build_cards.js data/answers/shared-l1.json data/answers/shared-l3.json

Experience strength uses the questionnaire's scale: 4 expert, 3 done it, 2 studied, 0 never.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOW = json.loads((ROOT / "data" / "version-a" / "flow.json").read_text(encoding="utf-8"))

LEVELS = {
    1: "Crawl",
    2: "Basic CSV",
    3: "Reports",
    4: "BigQuery",
    5: "Architect",
}

# The same at every level: everyday tools, never this platform, Google Cloud assumed (no AWS
# or other cloud), nothing the level does not imply (accounting courses, building admin panels).
COMMON = {"X01": 4, "X09": 3, "X15": 3}

# Per level, only what the level implies.
BY_LEVEL = {
    1: {},
    2: {"X02": 3, "X03": 2, "X04": 3, "X11": 2},
    3: {"X02": 4, "X03": 3, "X04": 3, "X05": 2, "X10": 2, "X11": 3},
    4: {"X02": 4, "X03": 4, "X04": 4, "X05": 3, "X10": 3, "X11": 3, "X12": 3, "X13": 3, "X20": 3},
    5: {"X02": 4, "X03": 4, "X04": 4, "X05": 4, "X10": 3, "X11": 4, "X12": 3, "X13": 3, "X16": 3, "X20": 4},
}

# A rough label says nothing about personality: every tendency question gets the middle
# answer, and the search habit is "it depends".
TEND = {"R1": 1, "R2": 1, "P1": 1, "P2": 1, "D1": 1, "D2": 1, "D3": 1, "H": 2}


def answers_for(level: int) -> dict:
    strengths = {**COMMON, **BY_LEVEL[level]}
    group_of = {e["id"]: e["group"] for e in FLOW["experiences"]}
    source_of = {g["id"]: g["source"] for g in FLOW["groups"]}
    screen = {s["id"]: [] for s in FLOW["sources"]}
    for eid in strengths:
        g = group_of[eid]
        if g not in screen[source_of[g]]:
            screen[source_of[g]].append(g)
    return {
        "kind": "sue-questionnaire",
        "version": 2,
        "flow": FLOW["name"],
        "filledAt": None,
        "pageLanguage": "en",
        "answers": {
            "name": f"Shared L{level} {LEVELS[level]}",
            "background": {},
            "screen": screen,
            "screenOther": {},
            "answers": {e["id"]: strengths[e["id"]] for e in FLOW["experiences"] if e["id"] in strengths},
            "expNotes": {},
            # Not taken: the engine uses the English level (fluent, 20,000 words).
            "lang": {"ui": "English", "english": "fluent"},
            "vocab": {},
            "tendStory": "",
            "tendFollow": "",
            "tend": TEND,
            "perc": {},
            "careText": "",
            # Not given: the builder's defaults (confirm by the list; if it never comes, go back and check).
            "done": [],
            "doneMiss": None,
            "doneMissOther": "",
        },
        "researcher": {"care": []},
        "note": f"Shared card for user type L{level} ({LEVELS[level]}), from tools/shared_answers.py. "
                "Built from the type label only; no participant's answers were used.",
    }


if __name__ == "__main__":
    for level in (1, 3):
        out = ROOT / "data" / "answers" / f"shared-l{level}.json"
        out.write_text(json.dumps(answers_for(level), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(out.relative_to(ROOT))
