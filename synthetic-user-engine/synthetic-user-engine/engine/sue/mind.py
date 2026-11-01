"""How a person decides: one mechanism, for every step of every card (engine-design.md 4.10, 2026-11-01).

The person goes over what they can do in reading order, values each move, and takes the first that
looks good enough (satisficing, as in Simon, and SNIF-ACT's serial evaluation). Nothing looked good
enough once they have read everything: they take one of what they have in mind, likelier the better
it looks. There is nothing else: going down a form, the final button coming last, reading on and
coming back, wandering when unsure and going straight when sure are what this does, not rules.

    value  = hope x understanding x weight x freshness
    chance = logistic((value - aspiration) / noise)

hope         0 to 10, the model's reading of the screen, less the doubt of someone unsure of the way.
             For what they cannot read, code's own word overlap with the task instead, so the
             model's experience does not leak in.
understanding  1 if they understand the move; less if half or not at all, by daring (risk).
weight       what the move is for, by detail when checking, how unsure they are, and where they are.
freshness    0 just after doing it; recovers with time outside a form, and stays 0 inside one.
aspiration   how good is good enough: higher for careful finders, lower when tired or pressed, and
             low in a form, where they go over each field rather than look for the way.
noise        how far the choice strays: wide when unsure of the way, narrow in a form.
unsure       from the card, and it fades as they move around: they learn where things are.

Every trait acts only as a parameter of these terms. The numbers are in config.toml [mind]."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .evidence import HALF, SURE
from .prompt import CHECK, EXPLORE, FIX, RETREAT, TASK

CHANGES = ("type", "choose")


@dataclass
class Outlook:
    """The person now: scores after fatigue and pressure, and where they are in the task."""

    risk: float
    find: float
    check: float
    unsure: float  # 0 knows the way, 1 does not
    in_form: bool
    saved: bool  # the task is done; they only look around now
    params: dict[str, float]

    @property
    def aspiration(self) -> float:
        p = self.params
        return (p["aspiration_form"] if self.in_form else p["aspiration"]) + p["aspiration_find"] * (self.find - 5) / 5

    @property
    def noise(self) -> float:
        p = self.params
        return p["noise_sure"] if self.in_form else p["noise_sure"] + (p["noise_unsure"] - p["noise_sure"]) * self.unsure


@dataclass
class Move:
    candidate: dict[str, Any]
    element: dict[str, Any] | None
    level: str
    key: tuple
    verdicts: list[Any]
    final: bool = False  # Finish, Cancel: a button that settles the form
    alike: int = 0  # words in common with the task, computed by code
    dropped: str | None = None
    terms: dict[str, float] | None = None
    value: float = 0.0
    chance: float = 0.0

    @property
    def purpose(self) -> str:
        return self.candidate.get("purpose") or TASK

    @property
    def action(self) -> str:
        return self.candidate.get("action") or "click"


def hope_of(move: Move, o: Outlook) -> float:
    if move.level not in (SURE, HALF):  # they cannot read it, so what the model says of it is the model's
        return 1.0 + min(3, move.alike)
    hope = move.candidate.get("hope")
    hope = max(0.0, min(10.0, float(hope))) if isinstance(hope, (int, float)) else 5.0
    return hope if o.in_form else hope * (1 - o.params["doubt"] * o.unsure)


def elsewhere(move: Move, o: Outlook) -> bool:
    """Leaves what they are working on: a look around, or folding this section for another."""
    e = move.element or {}
    return move.purpose == EXPLORE or (o.in_form and e.get("expanded") is not None and not e.get("dropdown"))


def changes_value(move: Move) -> bool:
    e = move.element or {}
    return move.action in CHANGES or e.get("type") in ("checkbox", "radio") or e.get("role") in ("checkbox", "radio", "switch")


def understanding(move: Move, o: Outlook) -> float:
    p, daring = o.params, o.risk / 10
    if move.level == SURE:
        return 1.0
    low, high = (p["half_low"], 1.0) if move.level == HALF else (p["void_low"], p["void_high"])
    share = low + (high - low) * daring
    return share * share if move.final else share  # a button that settles things takes more daring


def weight(move: Move, o: Outlook) -> float:
    p, careful = o.params, o.check / 10
    if o.saved and (move.action in CHANGES or move.final or move.purpose in (TASK, FIX)):
        return 0.0  # it is done; they change nothing now
    if elsewhere(move, o):
        return p["explore_in_form"] if o.in_form else 1.0
    if move.purpose == FIX:
        return p["fix_floor"] + (1 - p["fix_floor"]) * careful
    if move.purpose == CHECK:  # a look costs nothing; a look that changes a value is not just a look
        return (p["check_floor"] + (1 - p["check_floor"]) * careful) * (p["look_changes"] if changes_value(move) else 1.0)
    if move.purpose == RETREAT:
        return p["retreat"]
    return 1.0


def freshness(last: int | None, now: int, o: Outlook) -> float:
    if last is None:
        return 1.0
    return 0.0 if o.in_form else 1 - math.exp(-(now - last) / o.params["memory_span"])


def appraise(move: Move, o: Outlook, last: int | None, now: int) -> float:
    hope, under, weigh, fresh = hope_of(move, o), understanding(move, o), weight(move, o), freshness(last, now, o)
    # Looking around is not filling things in: less hope than this changes no value outside a form.
    if not o.in_form and move.action in CHANGES and hope < o.params["change_floor"]:
        weigh = 0.0
    move.value = hope * under * weigh * fresh
    move.chance = 1 / (1 + math.exp(-(move.value - o.aspiration) / o.noise))
    move.terms = {"hope": hope, "understanding": round(under, 3), "weight": round(weigh, 3), "freshness": round(fresh, 3)}
    return move.value


def reading_order(moves: list[Move]) -> list[Move]:
    """Down the piece; what has no place on it (scrolling on, going back) after what has."""
    def place(m: Move) -> tuple[float, float]:
        box = (m.element or {}).get("box")
        return (box["y"], box["x"]) if box else (math.inf, math.inf)
    return sorted(moves, key=place)


def scan(moves: list[Move], rng) -> Move | None:
    """The first in reading order that looks good enough; None if none does."""
    for m in reading_order(moves):
        if m.value > 0 and rng.random() < m.chance:
            return m
    return None


def settle(moves: list[Move], o: Outlook, rng) -> Move | None:
    """They have read everything and nothing was good enough: one of what they have in mind, likelier
    the better it looks. Below the floor it is not a move at all."""
    pool = [m for m in moves if m.value >= o.params["floor"]]
    if not pool:
        return None
    top = max(m.value for m in pool)
    return rng.choices(pool, weights=[math.exp((m.value - top) / o.noise) for m in pool])[0]
