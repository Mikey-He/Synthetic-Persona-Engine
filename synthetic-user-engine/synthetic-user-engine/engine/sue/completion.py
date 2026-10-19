"""Step 9: stop or not (engine-design.md 4.6).

Code never asks the model "are you done". It asks a question the person could answer
by looking, chosen by how this person confirms he is done, and checks the answer
against the screen. Phase 1 wires two of the five ways:

- list (checks the list or details page): the list shows the budget; the quote must be
  on screen and readable to him (a fake word means he cannot recognise it, as a person
  would not);
- action (done once the last button is clicked): he stops right after the final
  consequential action.

The others (success message, email, trigger) and the expectation-missed handling come
in phase 2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import VOID, _norm, check_word, quote_on_screen
from .persona import Persona

BY_LIST = "list"
BY_LAST_ACTION = "action"

# The ways a person makes sure a setup worked, as the questionnaire asks (card goal.confirmBy).
WAY_TEXT = {
    "action": "once they click the last button",
    "toast": "a success message",
    "list": "checking the list or details page",
    "external": "an email or phone notification",
    "test": "making it actually trigger once",
}


def ways_text(ways: list[str]) -> str:
    return "; ".join(WAY_TEXT.get(w, w) for w in ways)


@dataclass(frozen=True)
class Check:
    asked: bool
    done: bool
    why: str
    answer: Any = None
    quote: str = ""


def asks_list(persona: Persona) -> bool:
    goal = persona.goal
    return BY_LIST in (goal.get("confirmBy") or []) and bool((goal.get("productSignals") or {}).get("list"))


def missing_confirmation(persona: Persona) -> list[str]:
    """The ways he confirms he is done, when the product offers none of them (the
    expectation is missed, engine-design.md 4.6). Empty when at least one works: the
    last button always works, the others only when the product sends that signal."""
    ways = persona.goal.get("confirmBy") or []
    signals = persona.goal.get("productSignals") or {}
    if not ways or any(w == BY_LAST_ACTION or signals.get(w) for w in ways):
        return []
    return list(ways)


def stops_after_last_action(persona: Persona) -> bool:
    return BY_LAST_ACTION in (persona.goal.get("confirmBy") or [])


def check_list(persona: Persona, observations: dict[str, Any], route: str, hits, visible_text: str,
               list_routes: list[str], key: str) -> Check:
    """key: the observation the model answered in (prompt.list_key of what the workflow makes)."""
    if not asks_list(persona):
        return Check(False, False, "they do not confirm by the list")
    seen = observations.get(key) or {}
    answer, quote = seen.get("answer"), str(seen.get("quote") or "").strip()
    if route not in list_routes:
        return Check(True, False, "not on the list page", answer, quote)
    if answer is not True or not quote:
        return Check(True, False, "the model says the list does not have it", answer, quote)
    if not quote_on_screen(quote, visible_text):
        return Check(True, False, "the quote is not on screen", answer, quote)
    if check_word(quote, hits, visible_text).level == VOID:
        return Check(True, False, "the quote has words they cannot read, so they cannot recognise it", answer, quote)
    return Check(True, True, "the list shows the one just made; the quote checks out", answer, quote)


def review_link(check: Check, elements: list[dict[str, Any]], review_items: list[str], knows) -> dict[str, Any] | None:
    """A careful checker (detail when checking: high) who confirms by the list or the
    detail page opens the one he just saved and checks it once before he is done, if he
    knows how to open it (review_items, the name link). knows(item_id) says whether he
    does. Returns the link, or None."""
    if not check.done:
        return None
    quote = _norm(check.quote)
    for e in elements:
        if e.get("kl") in review_items and knows(e["kl"]) and e.get("text") and _norm(e["text"]) in quote:
            return e
    return None
