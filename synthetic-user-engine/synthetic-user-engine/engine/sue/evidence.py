"""The model's word does not count, evidence does (engine-design.md 4.3).

Each piece of evidence a candidate cites is checked against the persona card and the
screen as this person sees it, and turns into sure / half / void. A candidate's confidence
is its best piece of evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .memory import SessionMemory
from .persona import EVERYDAY, HABIT, KNOW, OTHER, VAGUE, Persona
from .words import Hit

SURE = "sure"
HALF = "half"
VOID = "void"
RANK = {SURE: 2, HALF: 1, VOID: 0}

_HALF_RESULTS = {VAGUE, EVERYDAY, OTHER}


@dataclass(frozen=True)
class Verdict:
    type: str
    ref: str
    level: str
    reason: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def check_item(ref: str, persona: Persona, memory: SessionMemory) -> Verdict:
    if memory.knows(ref):
        return Verdict("item", ref, SURE, "learned during the test")
    it = persona.item(ref)
    if it is None:
        return Verdict("item", ref, VOID, "no such item")
    if it.kind == HABIT:
        return Verdict("item", ref, VOID, "a habit is not evidence")
    if it.result == KNOW:
        return Verdict("item", ref, SURE, f"card: {it.result}")
    if it.result in _HALF_RESULTS:
        return Verdict("item", ref, HALF, f"card: {it.result}")
    return Verdict("item", ref, VOID, f"card: {it.result}")


def _hit_level(hit: Hit) -> str:
    if hit.level == KNOW:
        return SURE
    if hit.level in _HALF_RESULTS:
        return HALF
    return VOID


_TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")


def check_word(ref: str, screen_hits: list[Hit], visible_text: str = "", on_element: str | None = None) -> Verdict:
    """ref is text as he sees it on screen, often a whole element label. Every English
    word in it must be on screen, alone or inside a phrase (Target amount); the ref then
    counts at the level of its weakest word. A fake word, or a word that is not on
    screen, makes it void. Numbers and amounts are data: they count if they are on screen.

    on_element is the text he sees on the element the action targets. When given, the
    ref must be on that element itself (2026-10-04): "Atlas" elsewhere on screen is no
    reason to press a button whose label he cannot read."""
    if on_element is not None:
        own = {t.lower() for t in _TOKEN.findall(on_element)}
        tokens = [t.lower() for t in _TOKEN.findall(ref)]
        if (tokens and not set(tokens) <= own) or (not tokens and _norm(ref) not in _norm(on_element)):
            return Verdict("word", ref, VOID, "not on the element acted on")
    by_shown: dict[str, Hit] = {}
    for h in screen_hits:
        by_shown.setdefault(_norm(h.shown), h)
    key = _norm(ref)
    if key in by_shown:
        h = by_shown[key]
        return Verdict("word", ref, _hit_level(h), f"{h.source}, {h.level}")
    token_level: dict[str, str] = {}
    for h in screen_hits:
        for t in _TOKEN.findall(h.shown):
            t = t.lower()
            if t not in token_level or RANK[_hit_level(h)] > RANK[token_level[t]]:
                token_level[t] = _hit_level(h)
    tokens = [t.lower() for t in _TOKEN.findall(ref)]
    if not tokens:
        if key and visible_text and key in _norm(visible_text):
            return Verdict("word", ref, SURE, "a number or amount on screen")
        return Verdict("word", ref, VOID, "not on screen")
    missing = [t for t in tokens if t not in token_level]
    if missing:
        return Verdict("word", ref, VOID, f"not on screen: {' '.join(missing[:3])}")
    level = min((token_level[t] for t in tokens), key=lambda lv: RANK[lv])
    return Verdict("word", ref, level, "counted at its weakest word")


def own_words(element_text: str, screen_hits: list[Hit], visible_text: str = "") -> Verdict | None:
    """The words on the element itself always count as evidence (2026-10-04): whether he
    can read the button he is about to press is something code can look up, whatever
    the model wrote. The model sometimes leaves the evidence out, or cites words from
    elsewhere, for a move it plainly means (deleting an extra threshold row)."""
    if not element_text or not element_text.strip():
        return None
    # The main name decides (2026-10-04): when the label holds an item word, the first
    # one in it (the longest on a tie) is what he reads the button as. A qualifier in
    # brackets, "Alerts only (available to all services)", does not pull it down.
    text = _norm(element_text)
    named = [(text.find(_norm(h.shown)), -len(h.shown), h) for h in screen_hits
             if h.item_id and h.shown.strip() and _norm(h.shown) in text]
    if named:
        main = min(named, key=lambda x: (x[0], x[1]))[2]
        level = _hit_level(main)
        return Verdict("word", main.shown, level, "the element's main name is an item word (added by code)") if level != VOID else None
    v = check_word(element_text, screen_hits, visible_text, element_text)
    if v.level == VOID:
        return None
    return Verdict("word", element_text, v.level, "the element's own words (added by code)")


def check_evidence(evidence: list[dict], persona: Persona, memory: SessionMemory, screen_hits: list[Hit],
                   visible_text: str = "", element_text: str | None = None) -> list[Verdict]:
    """element_text: what he sees on the target element, for actions on an element.
    None for scroll and back, whose word evidence may come from anywhere on screen."""
    out = []
    for e in evidence or []:
        kind, ref = str(e.get("type", "")), str(e.get("ref", ""))
        if kind == "item":
            out.append(check_item(ref, persona, memory))
        elif kind == "word":
            out.append(check_word(ref, screen_hits, visible_text, element_text))
        else:
            out.append(Verdict(kind, ref, VOID, "unknown evidence type"))
    return out


def best_level(verdicts: list[Verdict]) -> str:
    return max((v.level for v in verdicts), key=lambda lv: RANK[lv], default=VOID)


def quote_on_screen(quote: str, visible_text: str) -> bool:
    """A quote counts only if it really is on screen, as he sees it."""
    q = _norm(quote)
    return bool(q) and q in _norm(visible_text)
