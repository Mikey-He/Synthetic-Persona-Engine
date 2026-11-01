"""Step 9: stop or not (engine-design.md 4.6).

Code never asks the model "are you done". It asks a question the person could answer
by looking, chosen by how this person confirms he is done, and checks the answer
against the screen. Three of the five ways are wired:

- list (checks the list or details page): the list shows the budget; the quote must be
  on screen and readable to him (a fake word means he cannot recognise it, as a person
  would not);
- action (done once the last button is clicked): he stops right after the final
  consequential action, unless the product visibly refused it (save_refused);
- toast (a success message, 2026-10-31): asked on the first look after the final action,
  since such a message goes away, and checked like the list's quote.

The others (email, trigger) go through the expectation-missed handling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence import VOID, _norm, check_word, quote_on_screen
from .persona import Persona

BY_LIST = "list"
BY_LAST_ACTION = "action"
BY_MESSAGE = "toast"

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


def asks_message(persona: Persona) -> bool:
    goal = persona.goal
    return BY_MESSAGE in (goal.get("confirmBy") or []) and bool((goal.get("productSignals") or {}).get(BY_MESSAGE))


def save_refused(still_there: bool, warnings: list[str]) -> bool:
    """The final button did not take: it is still on the page, in view or not, with a warning he can
    see. Some pages keep the button after a save and some show warnings that are not about it, so it
    takes both. A warning he did not notice does not count: he believes it went through."""
    return bool(still_there and warnings)


def missing_confirmation(persona: Persona) -> list[str]:
    """The ways he confirms he is done, when the product offers none of them (the
    expectation is missed, engine-design.md 4.6). Empty when at least one works: the
    last button always works, the others only when the product sends that signal."""
    ways = persona.goal.get("confirmBy") or []
    signals = persona.goal.get("productSignals") or {}
    if not ways or any(w == BY_LAST_ACTION or signals.get(w) for w in ways):
        return []
    return list(ways)


def lacking_confirmation(persona: Persona) -> list[str]:
    """The ways he confirms that the product does not offer, even when another way works: someone who
    wants to see it trigger too goes on looking after the success message (P003 did)."""
    goal = persona.goal
    signals = goal.get("productSignals") or {}
    return [w for w in goal.get("confirmBy") or [] if w != BY_LAST_ACTION and not signals.get(w)]


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


def check_found(observations: dict[str, Any], key: str, hits, visible_text: str, what: str) -> Check:
    """An answer found, or the page reached (flow.json engine.outcome, engine-design.md 6.3): the
    model says the screen shows it and quotes it; code checks the quote is on screen and readable
    to him. A fake word in it means he could not recognise it, as a person would not. what names
    it for the log (the answer, the page)."""
    seen = observations.get(key) or {}
    answer, quote = seen.get("answer"), str(seen.get("quote") or "").strip()
    if answer is not True or not quote:
        return Check(True, False, f"the model says this screen does not show {what}", answer, quote)
    if not quote_on_screen(quote, visible_text):
        return Check(True, False, "the quote is not on screen", answer, quote)
    if check_word(quote, hits, visible_text).level == VOID:
        return Check(True, False, "the quote has words they cannot read, so they cannot recognise it", answer, quote)
    return Check(True, True, f"they see {what}; the quote checks out", answer, quote)


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
