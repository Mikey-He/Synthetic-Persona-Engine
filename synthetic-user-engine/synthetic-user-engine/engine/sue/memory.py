"""Session memory (engine-design.md 4.5). Required: without it the engine circles
round the same wrong option."""

from __future__ import annotations

from dataclasses import dataclass, field


def action_key(context: str, element_label: str | None, action: str, value: str | None) -> tuple:
    """Identifies an action across steps by the screen context (route plus open
    sections) and the element's original text, not by its per-step id, so the same
    button is the same action after a re-render."""
    return (context, (element_label or "").strip().lower(), action, (value or "").strip().lower())


@dataclass
class SessionMemory:
    tried: dict[tuple, int] = field(default_factory=dict)  # action key -> step it was first tried
    learned: dict[str, int] = field(default_factory=dict)  # item id -> step it was learned
    dead_ends: dict[str, str] = field(default_factory=dict)  # link text -> the off-route page it led to
    touched: set[tuple] = field(default_factory=set)  # (route and open sections, element text) he clicked
    flips: dict[tuple, int] = field(default_factory=dict)  # (page, checkbox text) -> times he clicked it

    def was_tried(self, key: tuple) -> bool:
        return key in self.tried

    def record(self, key: tuple, step: int) -> None:
        self.tried.setdefault(key, step)

    def touch(self, place: str, label: str | None) -> None:
        """He clicked this element on this part of the page, whatever for."""
        self.touched.add((place, (label or "").strip().lower()))

    def has_touched(self, place: str, label: str | None) -> bool:
        return (place, (label or "").strip().lower()) in self.touched

    def flip(self, page: str, label: str | None) -> None:
        key = (page, (label or "").strip().lower())
        self.flips[key] = self.flips.get(key, 0) + 1

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
