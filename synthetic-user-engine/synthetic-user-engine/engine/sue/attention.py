"""Where he is looking (engine-design.md 4.8).

A person does not take in a whole screen at once. He reads it piece by piece in an
order: whatever just opened first, then the middle of the page, then the navigation
menu from the top down. The model sees only the piece he is looking at; the rest of
the screenshot is covered. When nothing in that piece is worth doing, he looks at the
next piece. Having looked at every piece once, he takes in the whole screen.

A piece is what a glance takes in (2026-10-04): a whole opened part (an open form
section, an open dropdown, a dialog); otherwise a list, table or group within a region,
such as one group of the menu. Someone who reads the whole screen before acting
(detail when finding things: high) takes each region as one piece."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

KIND_NAMES = {
    "popup": "the part just opened", "main": "the middle of the page", "nav": "the navigation menu",
    "aside": "the side panel", "header": "the top bar", "footer": "the bottom", "other": "the page",
}


@dataclass
class Chunk:
    kind: str
    rect: dict[str, float]
    elements: list[dict[str, Any]]
    index: int = 0
    total: int = 1

    def describe(self) -> str:
        return f"{KIND_NAMES.get(self.kind, self.kind)} (piece {self.index + 1} of {self.total})"


def chunks(elements: list[dict[str, Any]], order: list[str], viewport: tuple[int, int], by_group: bool = True,
           pad: int = 12) -> list[Chunk]:
    """Splits the visible elements into the pieces he reads, in reading order."""
    pieces: dict[tuple, dict[str, Any]] = {}
    for e in elements:
        r = e.get("region")
        if e.get("harness") or not r:
            continue
        g = r.get("group") if by_group and r["kind"] != "popup" else None
        key = (r["id"], g["id"] if g else None)
        pieces.setdefault(key, {"region": r, "group": g, "elements": []})["elements"].append(e)

    def rank(item: dict[str, Any]) -> tuple:
        r, g = item["region"], item["group"] or item["region"]
        kind = order.index(r["kind"]) if r["kind"] in order else len(order)
        area = r["w"] * r["h"] if r["kind"] == "popup" else 0  # the innermost thing that opened comes first
        return (kind, area, r["y"], r["x"], g["y"], g["x"])

    out: list[Chunk] = []
    for item in sorted(pieces.values(), key=rank):
        r, els = item["region"], sorted(item["elements"], key=lambda e: (e["box"]["y"], e["box"]["x"]))
        top = max(0, min(e["box"]["y"] for e in els) - pad)
        bottom = min(viewport[1], max(e["box"]["y"] + e["box"]["h"] for e in els) + pad)
        if r["kind"] == "popup":  # an opened part is read as a whole, including its text
            top, bottom = max(0, r["y"] - pad // 2), min(viewport[1], r["y"] + r["h"] + pad // 2)
        out.append(Chunk(r["kind"], {"x": r["x"], "y": top, "w": r["w"], "h": max(1, bottom - top)}, els))
    for i, c in enumerate(out):
        c.index, c.total = i, len(out)
    return out


@dataclass
class Attention:
    order: list[str]
    viewport: tuple[int, int]
    by_group: bool = True
    pos: dict[str, int] = field(default_factory=dict)  # screen context -> piece he is on
    whole: set[str] = field(default_factory=set)  # contexts where he has looked at every piece

    def _parts(self, elements):
        return chunks(elements, self.order, self.viewport, self.by_group)

    def focus(self, context: str, elements: list[dict[str, Any]]) -> Chunk | None:
        """The piece he is looking at, or None when he takes in the whole screen."""
        if context in self.whole:
            return None
        parts = self._parts(elements)
        if not parts:
            return None
        return parts[min(self.pos.get(context, 0), len(parts) - 1)]

    def advance(self, context: str, elements: list[dict[str, Any]], can_scroll: bool = False) -> tuple[str, str] | None:
        """Moves on. Returns (what, note): "look" at the next piece, or "scroll" when he
        has read to the bottom of the page's main part or of what opened and the page
        goes on below; he scrolls and keeps reading there instead of turning to the
        menu. None when he has already taken in the whole screen."""
        if context in self.whole:
            return None
        parts = self._parts(elements)
        cur = min(self.pos.get(context, 0), max(len(parts) - 1, 0))
        nxt = cur + 1
        reading_page = bool(parts) and parts[cur].kind in ("popup", "main")
        leaves_page = nxt >= len(parts) or parts[nxt].kind not in ("popup", "main")
        if can_scroll and reading_page and leaves_page:
            self.pos[context] = 0  # after scrolling he reads from the top of what he sees
            return ("scroll", "done with this piece; there is more below, so they scroll on")
        if nxt < len(parts):
            self.pos[context] = nxt
            return ("look", f"nothing to do in this piece; next: {parts[nxt].describe()}")
        self.whole.add(context)
        return ("look", "every piece looked at; now takes in the whole screen")
