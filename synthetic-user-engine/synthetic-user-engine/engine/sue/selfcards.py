"""The two self-test cards of a workflow, built from its flow.json (engine-design.md 6.3).

The full card understands every item and the blank card none, with every other setting in the
middle. The Persona Builder makes them for Version A (data/personas/full-card.json and
blank-card.json); a new workflow gets them from here, the same way, with no questionnaire: the
onboarding checks run them (sue/check.py), and --card full / --card blank run them on any
workflow. For Version A this builds the same cards the Persona Builder saved."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .words import fake

KINDS = ("full", "blank")


def confirm_by(signals: dict[str, Any]) -> list[str]:
    """How a self-test card makes sure it is done: by the list when the product has one, else by
    a success message, else once the last button is clicked."""
    if signals.get("list"):
        return ["list"]
    if signals.get("toast"):
        return ["toast"]
    return ["action"]


def build(flow: dict[str, Any], kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"a self-test card is full or blank, not {kind!r}")
    full = kind == "full"
    screens = {s["id"]: s for s in flow["screens"]}
    steps = flow["steps"]
    number = {s["id"]: n for n, s in enumerate(steps, 1)}
    screen_of = {s["id"]: screens[s["screen"]]["name"] for s in steps}
    primary = [i for i in flow["items"] if not i.get("altOf")]
    evidence = "Full card: understands everything, no misleading habits" if full else "Blank card: understands nothing"

    def result(item: dict[str, Any]) -> str:
        if item["kind"] == "habit":
            return "unaffected"
        return "understands" if full else "none"

    items = [{"id": i["id"], "step": number[i["step"]], "screen": screen_of[i["step"]], "needed": i.get("needed", True),
              "kind": i["kind"], "text": i["text"], "result": result(i), "evidence": evidence} for i in primary]
    card_screens = []
    for s in flow["screens"]:
        on = [i for i in primary if screens[next(st["screen"] for st in steps if st["id"] == i["step"])]["id"] == s["id"]]
        words = [{"id": i["id"], "original": i["text"], "shown": i["text"] if full else fake(i["text"]),
                  "level": "understands" if full else "none", "gloss": ""} for i in on if i["kind"] == "word"]
        knowledge = [{"id": i["id"], "kind": i["kind"], "text": i["text"], "level": "understands"}
                     for i in on if full and i["kind"] not in ("word", "habit")]
        card_screens.append({"screen": s["name"], "words": words, "knowledge": knowledge})
    card_steps = []
    for s in steps:
        def needed(way=None):
            return [i for i in primary if i["step"] == s["id"] and i.get("needed", True) and i["kind"] != "habit"
                    and (way is None or not i.get("way") or i["way"] == way)]

        def known(items):
            return "complete" if full or not items else "has unknown items"

        ways = [{"text": w["text"], "knowledge": known(needed(w["id"]))} for w in s.get("ways", [])]
        card_steps.append({"step": number[s["id"]], "screen": screen_of[s["id"]], "action": s["action"],
                           "risky": bool(s.get("risky")), "mustChangeDefaults": s.get("defaults", ""),
                           "ways": ways, "knowledge": known(needed()),
                           "misleadingHabit": False})
    signals = flow.get("signals") or {}
    medium = {"level": "medium", "usual": "medium", "source": "Self-test card: medium"}
    return {
        "format": "sue-persona", "version": 2, "flow": flow["name"],
        "builtAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z", "answersFilledAt": None,
        "persona": {"id": f"{kind}-card", "name": f"{kind.capitalize()} card", "cardType": kind,
                    "lang": {"ui": "", "english": "fluent", "vocabSize": None, "vocabSource": "Self-test card"},
                    "calibrated": False},
        "tendency": {"risk": dict(medium), "patience": dict(medium), "detail": dict(medium), "detailFind": dict(medium),
                     "detailCheck": dict(medium), "habit": "depends"},
        "perception": {"vision": {"level": "high", "source": "Self-test card"},
                       "motor": {"level": "high", "source": "Self-test card"},
                       "speed": {"level": "medium", "source": "Self-test card"}, "colorWeak": False,
                       "screen": flow.get("screenSize", "")},
        "goal": {"task": flow["task"], "successChecks": flow.get("checks", []), "careText": "", "care": [],
                 "confirmBy": confirm_by(signals), "productSignals": signals, "ifConfirmMissing": "check",
                 "ifConfirmMissingText": "", "situation": flow.get("situation") or {"urgency": "calm", "stakes": "low"},
                 "org": flow.get("org", "")},
        "screens": card_screens,
        "steps": card_steps,
        "items": items,
    }


def card_for(personas_dir: Path, name: str, flow_file: str | Path) -> dict[str, Any] | None:
    """The full or blank card for this workflow: the saved one when it was built for it, else
    one built now. None when name is not full or blank."""
    if name not in KINDS:
        return None
    flow = json.loads(Path(flow_file).read_text(encoding="utf-8"))
    saved = Path(personas_dir) / f"{name}-card.json"
    if saved.exists():
        card = json.loads(saved.read_text(encoding="utf-8"))
        if card.get("flow") == flow["name"]:
            return card
    return build(flow, name)
