"""Item locators, built and checked away from the page (engine-design.md 6.3).

On the page, page_script.js mark() finds an item's control from its locator. Here the same
rules run on a recorded screen's list of controls (sue/record.py), so a draft flow gets the
simplest locator that finds exactly that control and nothing else, and the review page can
show which control each item is on before anything is run."""

from __future__ import annotations

import re
from typing import Any


def norm(text: str | None) -> str:
    """As page_script.js norm(): lower case, single spaces, no punctuation at either end."""
    t = re.sub(r"\s+", " ", text or "").strip().lower()
    return re.sub(r"^[\W_]+|[\W_]+$", "", t)


def same(have: str | None, want: str | None, how: str = "exact") -> bool:
    h, w = norm(have), norm(want)
    if not w:
        return False
    if how == "contains":
        return w in h
    if how == "starts":
        return h.startswith(w)
    return h == w


def fits(control: dict[str, Any], loc: dict[str, Any], how: str | None = None) -> bool:
    how = how or loc.get("match", "exact")
    if loc.get("role") and control.get("role") != loc["role"]:
        return False
    if loc.get("text") and not same(control.get("text"), loc["text"], how):
        return False
    if loc.get("label") and not same(control.get("label"), loc["label"], how):
        return False
    if loc.get("region") and control.get("region") != loc["region"]:
        return False
    if loc.get("group") and not same(control.get("group"), loc["group"]):
        return False
    return True


def find(controls: list[dict[str, Any]], loc: dict[str, Any]) -> list[int]:
    """The controls a locator finds, by index; a looser match when nothing matches word for word."""
    if loc.get("selector"):
        return []  # a CSS selector can only be checked on the live page
    found = [i for i, c in enumerate(controls) if fits(c, loc)]
    if not found and loc.get("match", "exact") == "exact" and (loc.get("text") or loc.get("label")):
        loose = [i for i, c in enumerate(controls) if fits(c, loc, "contains")]
        found = loose if len(loose) == 1 or "nth" in loc else []
    if "nth" in loc:
        found = found[loc["nth"]:loc["nth"] + 1]
    return found


def build(controls: list[dict[str, Any]], index: int) -> dict[str, Any]:
    """The simplest locator that finds control index alone on this screen. Text first (what a
    person reads), then its role, the part of the page and its group heading; an icon by its
    label; nth only when nothing else tells it apart."""
    c = controls[index]
    text, label = (c.get("text") or "").strip(), (c.get("label") or "").strip()
    name = {"text": text} if text else {"label": label} if label else {}
    if not name:
        return {"role": c.get("role") or "button", "nth": [i for i, o in enumerate(controls) if o.get("role") == c.get("role")].index(index)}
    tries = [dict(name)]
    if c.get("role"):
        tries.append({**name, "role": c["role"]})
    if c.get("region") and c["region"] != "other":
        tries.append({**name, "region": c["region"]})
    if c.get("group"):
        tries.append({**name, "group": c["group"]})
    full = {**name, **({"role": c["role"]} if c.get("role") else {}),
            **({"region": c["region"]} if c.get("region") and c["region"] != "other" else {}),
            **({"group": c["group"]} if c.get("group") else {})}
    tries.append(full)
    for loc in tries:
        if find(controls, loc) == [index]:
            return loc
    matches = [i for i, o in enumerate(controls) if fits(o, full)]
    return {**full, "nth": matches.index(index)} if index in matches else full
