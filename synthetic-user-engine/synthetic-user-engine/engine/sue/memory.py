"""Session memory (engine-design.md 4.5). Required: without it the engine circles
round the same wrong option."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


def action_key(context: str, element_label: str | None, action: str, value: str | None) -> tuple:
    """Identifies an action across steps by the screen context (route plus open
    sections) and the element's original text, not by its per-step id, so the same
    button is the same action after a re-render."""
    return (context, (element_label or "").strip().lower(), action, (value or "").strip().lower())


def typed_value(value: str | None) -> str:
    """A typed value, so that 800 and $800 are the same."""
    return re.sub(r"[\s$,]", "", str(value or "")).lower()


def _in_a_form(context: str) -> bool:
    parts = context.split("|")  # the route, the open sections, then the page and the digest
    return len(parts) >= 3 and parts[0].startswith("/") and bool(parts[1])


@dataclass
class SessionMemory:
    tried: dict[tuple, int] = field(default_factory=dict)  # action key -> step it was first tried
    learned: dict[str, int] = field(default_factory=dict)  # item id -> step it was learned
    dead_ends: dict[str, str] = field(default_factory=dict)  # link text -> the off-route page it led to
    touched: set[tuple] = field(default_factory=set)  # (route and open sections, element text) he clicked
    flips: dict[tuple, int] = field(default_factory=dict)  # (page, checkbox text) -> times he clicked it
    typed: set[tuple] = field(default_factory=set)  # (page, box name, value) he typed
    peeked: set[str] = field(default_factory=set)  # forms where a medium checker has taken his one look
    settled: dict[tuple, bool | None] = field(default_factory=dict)  # (page, checkbox text) he set on purpose in this form: how he left it

    def still_remembers(self, key: tuple, now: int, span: float | None, rng) -> bool:
        """Whether a move he tried is still in mind. People do go back to what they tried; a hard ban
        made that impossible. With no span, nothing fades. A move forgotten is new again."""
        if key not in self.tried:
            return False
        if not span or not rng:
            return True
        if rng.random() < math.exp(-(now - self.tried[key]) / span):
            return True
        del self.tried[key]
        return False

    def was_tried(self, key: tuple) -> bool:
        return key in self.tried

    def record(self, key: tuple, step: int) -> None:
        self.tried.setdefault(key, step)

    def forget(self, key: tuple) -> None:
        """Clicking it took him to another page: going there again later is a new move."""
        self.tried.pop(key, None)

    def new_form(self) -> None:
        """He left the form. A new one looks exactly like the last, and what he tried in that one is
        not tried in this one. Only moves made with a section open are forgotten."""
        self.tried = {k: v for k, v in self.tried.items() if not _in_a_form(k[0])}
        self.typed.clear()
        self.peeked.clear()
        self.settled.clear()
        self.flips.clear()

    def save_refused(self) -> None:
        """The product would not save and says what is wrong. What he tried in the form may need doing
        again, and the message is why: it is not the same move as before."""
        self.tried = {k: v for k, v in self.tried.items() if not _in_a_form(k[0])}
        self.typed.clear()

    def type_in(self, page: str, label: str | None, value: str | None) -> None:
        self.typed.add((page, (label or "").strip().lower(), typed_value(value)))

    def has_typed(self, page: str, label: str | None, value: str | None) -> bool:
        return (page, (label or "").strip().lower(), typed_value(value)) in self.typed

    def touch(self, place: str, label: str | None) -> None:
        """He clicked this element on this part of the page, whatever for."""
        self.touched.add((place, (label or "").strip().lower()))

    def has_touched(self, place: str, label: str | None) -> bool:
        return (place, (label or "").strip().lower()) in self.touched

    def flip(self, page: str, label: str | None) -> None:
        key = (page, (label or "").strip().lower())
        self.flips[key] = self.flips.get(key, 0) + 1

    def settle(self, page: str, label: str | None, ticked: bool | None = None) -> None:
        self.settled[(page, (label or "").strip().lower())] = ticked

    def is_settled(self, page: str, label: str | None, ticked: bool | None = None) -> bool:
        """Whether he set this box and it is still as he left it. A box the page put back is not settled:
        he can see it is not as he left it."""
        key = (page, (label or "").strip().lower())
        return key in self.settled and (self.settled[key] is None or ticked is None or self.settled[key] == bool(ticked))

    def flipped(self, page: str, label: str | None) -> int:
        return self.flips.get((page, (label or "").strip().lower()), 0)

    def dead_end(self, label: str | None, route: str) -> None:
        """A link that led him off the route. He remembers it on every page, so he does
        not go round the same menu items again."""
        if label and label.strip():
            self.dead_ends.setdefault(label.strip().lower(), route)

    def is_dead_end(self, label: str | None) -> bool:
        return bool(label) and label.strip().lower() in self.dead_ends

    def learn(self, item_id: str, step: int) -> bool:
        """Marks an item as understood from now on. Returns True the first time."""
        if item_id in self.learned:
            return False
        self.learned[item_id] = step
        return True

    def knows(self, item_id: str) -> bool:
        return item_id in self.learned
