"""A persona card built by the Persona Builder (tools/persona-builder.html) from one
participant's questionnaire answers (engine-design.md 3, 6). The builder has already
computed every result; the engine only reads them."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Knowledge results as the card writes them.
KNOW = "understands"
VAGUE = "vague"
EVERYDAY = "everyday"  # knows only the everyday meaning
OTHER = "other"  # reads it as something else
NONE = "none"
MISLED = "misleads"
MISLED_MAYBE = "may_mislead"
UNAFFECTED = "unaffected"

# Item kinds.
WORD = "word"
ICON = "icon"
HABIT = "habit"

CARD_FORMAT, CARD_VERSION = "sue-persona", 2
# v3 (Persona Studio, 2026-10-19) adds a 0-10 score to each tendency, the states (fatigue,
# distraction, time pressure, attention to warnings) and perception the engine uses
# (sue/variability.py). v2 cards from the questionnaire still run exactly as before.
CARD_VERSIONS = (2, 3)


@dataclass(frozen=True)
class Word:
    """One word item: the original on screen, what this person sees, and what they take it to mean."""

    id: str
    original: str
    shown: str
    level: str
    gloss: str


@dataclass(frozen=True)
class Item:
    id: str
    kind: str
    text: str
    result: str
    step: int
    needed: bool


@dataclass(frozen=True)
class Persona:
    id: str
    name: str
    card_type: str  # normal / blank / full
    english: str  # fluent / intermediate / beginner
    vocab_size: int | None  # from the vocabulary test; None when it was not taken
    task: str
    words: tuple[Word, ...]
    items: dict[str, Item]
    tendency: dict[str, Any]
    perception: dict[str, Any]
    goal: dict[str, Any]
    steps: tuple[dict[str, Any], ...]
    source: Path
    version: int = CARD_VERSION
    state: dict[str, Any] | None = None  # v3 only
    flow: str = ""  # the name of the workflow the card was built for (the flow's name)

    def item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def knowledge_lines(self) -> tuple[list[str], list[str]]:
        """What goes into the prompt (engine-design.md 4.1, 4.2): non-word items they know,
        and the ones they only vaguely remember. Words are not listed here; they reach the
        model through the screen itself."""
        known, vague = [], []
        for it in self.items.values():
            if it.kind in (WORD, HABIT):
                continue
            if it.result == KNOW:
                known.append(f"[{it.id}] {it.text}")
            elif it.result == VAGUE:
                vague.append(f"[{it.id}] {it.text} (vaguely remembered, not sure)")
        return known, vague


class CardError(ValueError):
    """The file is not a persona card this engine reads."""


def load_persona(path: Path) -> Persona:
    return persona_from_card(json.loads(path.read_text(encoding="utf-8")), path)


def persona_from_card(card: dict[str, Any], path: Path) -> Persona:
    """A card already read, e.g. one Persona Studio has not saved yet; path is for messages."""
    if card.get("format") != CARD_FORMAT or card.get("version") not in CARD_VERSIONS:
        raise CardError(f"{path.name} is not a {CARD_FORMAT} card of version "
                        + " or ".join(f"v{v}" for v in CARD_VERSIONS)
                        + "; build it again in tools/persona-builder.html or Persona Studio")
    words: dict[str, Word] = {}
    for screen in card["screens"]:
        for w in screen["words"]:
            words.setdefault(w["id"], Word(w["id"], w["original"], w["shown"], w["level"], w.get("gloss", "")))
    items = {
        it["id"]: Item(it["id"], it["kind"], it["text"], it["result"], it["step"], it["needed"])
        for it in card["items"]
    }
    p = card["persona"]
    lang = p.get("lang") or {}
    return Persona(
        id=p["id"],
        name=p["name"],
        card_type=p["cardType"],
        english=lang.get("english") or "fluent",
        vocab_size=lang.get("vocabSize"),
        task=card["goal"]["task"],
        words=tuple(words.values()),
        items=items,
        tendency=card["tendency"],
        perception=card["perception"],
        goal=card["goal"],
        steps=tuple(card["steps"]),
        source=path,
        version=card["version"],
        state=card.get("state") if card["version"] >= 3 else None,
        flow=card.get("flow") or "",
    )


CARD_FILES = {"blank": "blank-card.json", "full": "full-card.json"}


def load_card(personas_dir: Path, name: str) -> Persona:
    """name is blank / full, or a card file name in the personas folder (the .json may be
    left off, so a new person's card p4.json runs as --card p4)."""
    file = CARD_FILES.get(name, name)
    if not (Path(personas_dir) / file).exists() and not file.endswith(".json"):
        file += ".json"
    return load_persona(Path(personas_dir) / file)
