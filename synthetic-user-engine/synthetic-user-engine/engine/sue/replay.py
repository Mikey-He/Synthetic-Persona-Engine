"""A real person's session walked again through the engine's eyes, with no model (2026-10-31).

For each participant file: that person's card and vocabulary, their window, the same Screen the
engine uses, and the moves they really made, in order. At each move: what this person is shown as
that control's name, how they understand it, the own-words verdict on it, whether the engine lists
it at all, and whether the choosing rules would let the card do it. Then the move is performed, so
the page really advances. A person did every one of these moves, so a move the card cannot read,
or the rules refuse, is a defect in the card or the rule, not in the person.

A move that is not found is not always a defect. "not_in_dom" means the control is nowhere on the
page: the replay has lost the person's state (a limitation of the replay) unless the rows before
it are in step. "not_clickable" and "covered" mean it is there and the engine's list leaves it out:
those are real.

    python -m sue.replay --flow <flow.json> --participants <folder> --out <file outside the repo> [--only 001]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from playwright.sync_api import sync_playwright

from .choose import ACT, Policy, decide, score
from .config import load_config
from .evidence import VOID, check_evidence, own_words
from .memory import SessionMemory
from .participant import engine_window, load, thing
from .persona import ICON, NONE, Persona, load_card
from .prompt import CHECK, EXPLORE, FIX, RETREAT, TASK
from .screen import RewriteError, Screen, Strip, open_browser
from .similarity import similarity, task_values, task_words
from .study import card_of
from .target import make_target
from .variability import LEVELS, make, traits_of
from .words import build_vocabulary

MAX_SCROLLS = 6
PURPOSES = (TASK, FIX, EXPLORE, CHECK, RETREAT)
REAL = ("not_clickable", "covered", "not_listed")  # found on the page, left out of the engine's list
LOST = ("not_in_dom", "offscreen")  # the replay may have lost the person's state or place
INTERNAL_KEYS = ("uat:",)  # the study harness's own keys, not the product's

# What the page holds, named the way the study harness named it (harness.js labelOf, fieldName), so a
# recorded name finds its control whatever the engine calls it. Text comes from the originals the
# engine keeps on each text node, since the page itself now shows this person's words.
SNAPSHOT = r"""
(kind) => {
  const CLICKABLE = "a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=link], " +
    "[role=checkbox], [role=radio], [role=option], [role=menuitem], [role=tab], [role=switch]";
  const CONTROL = "a[href], button, summary, [role=button], [role=link], [role=option], [role=menuitem], [role=tab], " +
    "[data-page], [data-action], [data-step]";
  const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
  function orig(el) {
    const out = [];
    const walk = (n) => {
      if (n.nodeType === 3) {
        if (!n.nodeValue.trim()) return;
        const p = n.parentElement;
        if (p && p.tagName !== "OPTION" && p.checkVisibility && !p.checkVisibility()) return;
        out.push(n.__sueOrig !== undefined ? n.__sueOrig : n.nodeValue);
        return;
      }
      for (let c = n.firstChild; c; c = c.nextSibling) walk(c);
    };
    walk(el);
    return clean(out.join(" "));
  }
  function labelOf(el) {
    const label = el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    return label || el.closest("label");
  }
  function fieldName(el) {
    const label = labelOf(el);
    const own = label ? orig(label) : "";
    return own || el.getAttribute("placeholder") || el.getAttribute("aria-label") || el.name || el.type || "field";
  }
  // Some browsers leave a dropdown's options out of its label's text, so a file can name the field either way.
  function plainName(el) {
    const label = labelOf(el);
    if (!label) return "";
    const out = [];
    const walk = (n) => {
      if (n.nodeType === 3) { if (n.nodeValue.trim()) out.push(n.__sueOrig !== undefined ? n.__sueOrig : n.nodeValue); return; }
      if (n.tagName === "SELECT") return;
      for (let c = n.firstChild; c; c = c.nextSibling) walk(c);
    };
    walk(label);
    return clean(out.join(" "));
  }
  const hiddenUntilHover = (el) => {
    for (let n = el, i = 0; n && i < 3; n = n.parentElement, i++) if (getComputedStyle(n).opacity === "0") return true;
    return false;
  };
  const describeHit = (h) => h ? (h.tagName.toLowerCase() + (h.id ? "#" + h.id : "") + (h.className && h.className.baseVal === undefined ? "." + String(h.className).trim().replace(/\s+/g, ".") : "")) : null;
  const pool = kind === "field" ? [...document.querySelectorAll("input, select, textarea")] : [...document.querySelectorAll(CONTROL)];
  const rows = pool.map((el) => {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    const off = r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth;
    const cx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1), cy = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
    const hit = document.elementFromPoint(cx, cy);
    const clear = !!hit && (hit === el || el.contains(hit) || hit.contains(el));
    // The engine counts a hit on an ancestor as seeing the control, but then a click there goes to the ancestor:
    // what happens when a panel's own scrolling has cut the control off.
    const missed = !off && !!hit && hit !== el && !el.contains(hit) && hit.contains(el);
    let scroller = null;
    for (let n = el.parentElement; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const oy = getComputedStyle(n).overflowY;
      if ((oy === "auto" || oy === "scroll") && n.scrollHeight > n.clientHeight + 1) {
        const q = n.getBoundingClientRect();
        scroller = { cx: Math.round(q.left + q.width / 2), cy: Math.round(Math.max(q.top, 0) + (Math.min(q.bottom, innerHeight) - Math.max(q.top, 0)) / 2) };
        break;
      }
    }
    return {
      n: pool.indexOf(el),
      name: kind === "field" ? fieldName(el) : (el.getAttribute("aria-label") || orig(el) || el.getAttribute("title") || ""),
      plain: kind === "field" ? plainName(el) : "",
      aria: el.getAttribute("aria-label") || "",
      i: el.getAttribute("data-sue-i"),
      tag: el.tagName.toLowerCase(), type: el.type || "", role: el.getAttribute("role") || "",
      clickable: el.matches(CLICKABLE),
      shown: r.width >= 1 && r.height >= 1 && style.visibility !== "hidden" && style.display !== "none",
      offscreen: off, above: r.bottom <= 0,
      x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height),
      covered: off || clear ? null : describeHit(hit),
      missed, scroller,
      opacity0: hiddenUntilHover(el),
      disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
      value: el.tagName === "SELECT" ? (el.options[el.selectedIndex] ? orig(el.options[el.selectedIndex]) : el.value) : el.value,
      checked: el.type === "checkbox" || el.type === "radio" ? el.checked : null,
      options: el.tagName === "SELECT" ? [...el.options].map(orig) : null,
    };
  });
  return rows;
}
"""

WHERE = r"""
() => {
  const clean = (t) => (t || "").replace(/\s+/g, " ").trim();
  const orig = (el) => {
    if (!el) return "";
    const out = [];
    const walk = (n) => {
      if (n.nodeType === 3) { if (n.nodeValue.trim()) out.push(n.__sueOrig !== undefined ? n.__sueOrig : n.nodeValue); return; }
      for (let c = n.firstChild; c; c = c.nextSibling) walk(c);
    };
    walk(el);
    return clean(out.join(" "));
  };
  const title = orig(document.getElementById("pageTitle")), open = orig(document.querySelector(".step.open .stepname"));
  return { route: location.hash || "#", screen: open ? title + " / " + open : title };
}
"""

STORED = r"""
() => Object.fromEntries(Object.keys(localStorage).map((k) => {
  const v = localStorage.getItem(k);
  try { return [k, JSON.parse(v)]; } catch (e) { return [k, v]; }
}))
"""

QUIET_SPOT = r"""
([x, y]) => {
  const el = document.elementFromPoint(x, y);
  const INTERACTIVE = "a[href], button, input, select, textarea, label, summary, [role=button], [role=link], [role=option], " +
    "[role=checkbox], [role=radio], [role=menuitem], [role=tab], [contenteditable=true], [data-page], [data-action], [data-step]";
  return !!el && !el.closest(INTERACTIVE);
}
"""


# ---- the moves, from the participant's file ------------------------------------------------------

def _number(x: float) -> str:
    return str(int(x)) if float(x).is_integer() else str(round(x, 2))


def row_values(draft: dict[str, Any] | None) -> dict[str, list[str]]:
    """What each row of the threshold table held when this person next pressed FINISH. The file names
    a change only by the field's name ("Trigger on"), and there are several rows of that name."""
    rules = (draft or {}).get("rules") or []
    try:
        amount = float(str((draft or {}).get("amount") or 0).replace("$", "").replace(",", ""))
    except ValueError:
        amount = 0.0
    return {
        "percent of budget": [f"{_number(float(r.get('percent') or 0))}%" for r in rules],
        "trigger on": [str(r.get("trigger")) for r in rules],
        "amount": [f"${_number(amount * float(r.get('percent') or 0) / 100)}" for r in rules],
    }


def replay_moves(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """The moves to make again, in order. participant.person_moves names moves the same way, but it
    joins repeats, which is right for comparing and wrong here: "Specified amount" twice is opening
    the list and then picking from it. Only what changes nothing is left out: a field's second log
    line when it loses focus. A click on nothing stays, since it can close an open list."""
    events = list(events)
    out: list[dict[str, Any]] = []
    last_act = None
    for n, e in enumerate(events):
        kind, p = e.get("type"), e.get("payload") or {}
        base = {"seq": e.get("seq"), "route": p.get("route"), "screen": p.get("screen")}
        if kind == "page_viewed" and last_act is not None and last_act not in ("control_clicked", "key_pressed", "form_submitted", "save_clicked"):
            out.append({**base, "kind": "back", "label": ""})  # the page changed with no click: the browser's own Back
        if kind in ("control_clicked", "key_pressed", "form_submitted", "save_clicked", "page_viewed", "field_changed", "click_no_effect"):
            last_act = kind
        if kind == "control_clicked":
            out.append({**base, "kind": "control", "label": p.get("label") or "", "x": p.get("x"), "y": p.get("y")})
        elif kind == "click_no_effect":
            out.append({**base, "kind": "nothing", "label": "", "x": p.get("x"), "y": p.get("y")})
        elif kind == "field_changed":
            if p.get("from") == p.get("value"):
                continue
            field = thing(p.get("field"))
            later = next((x["payload"].get("draft") for x in events[n:] if x.get("type") == "save_clicked"), None)
            out.append({**base, "kind": "field", "label": p.get("field") or "", "from": p.get("from"), "value": p.get("value"),
                        "rows": row_values(later).get(field)})
        elif kind == "key_pressed" and p.get("key") == "Enter" and p.get("field"):
            out.append({**base, "kind": "enter", "label": p.get("field") or "", "value": p.get("value")})
    return out


def is_real_move(move: dict[str, Any]) -> bool:
    """A click on nothing and the browser's Back are replayed to keep the page in step, but they are not moves on a control."""
    return move["kind"] not in ("nothing", "back")


def names_match(recorded: str, name: str) -> bool:
    """The harness cut names at 80 characters."""
    want, have = thing(recorded), thing(name)
    if not want:
        return False
    return want == have or (len(recorded) >= 80 and have.startswith(want))


def _same_value(a: Any, b: Any) -> bool:
    return thing(a) == thing(b)


def pick_target(found: list[dict[str, Any]], move: dict[str, Any]) -> dict[str, Any]:
    """Which of the controls of that name the person meant. A field: one holding the old value, among
    them the row that ends up with the new value, the last of them when that does not say. A control:
    the one nearest the person's click, among those on screen first."""
    for row, c in enumerate(found):
        c["row"] = row
    if move["kind"] == "field":
        value = move.get("value")
        if isinstance(value, bool):
            holding = [c for c in found if c.get("checked") is not None and c["checked"] != value]
        else:
            holding = [c for c in found if _same_value(c.get("value"), move.get("from"))]
        pool = holding or found
        hints = move.get("rows")
        if hints:
            pool = [c for c in pool if c["row"] < len(hints) and _same_value(hints[c["row"]], value)] or pool
        return pool[-1]
    pool = [c for c in found if not c["offscreen"]] or found
    x, y = move.get("x"), move.get("y")
    if x is None or y is None:
        return pool[0]
    return min(pool, key=lambda c: abs(c["x"] + c["w"] / 2 - x) + abs(c["y"] + c["h"] / 2 - y))


def why_left_out(target: dict[str, Any]) -> str:
    """Why the engine's list does not have a control that is on the page."""
    if target["offscreen"]:
        return "offscreen"
    if not target["clickable"]:
        return "not_clickable"
    if target["covered"]:
        return "covered"
    if not target["shown"]:
        return "not_shown"
    return "not_listed"


# ---- the result ----------------------------------------------------------------------------------

def _without_ids(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list):
        return [_without_ids(v) for v in value]
    return value


def saved_difference(person: dict[str, Any] | None, replayed: dict[str, Any] | None) -> dict[str, Any]:
    """The product's saved keys that differ, ignoring ids, which are new every time, and the harness's own keys."""
    keep = lambda d: {k: _without_ids(v) for k, v in (d or {}).items() if not k.startswith(INTERNAL_KEYS)}  # noqa: E731
    p, r = keep(person), keep(replayed)
    return {k: {"person": p.get(k), "replay": r.get(k)} for k in sorted(set(p) | set(r)) if p.get(k) != r.get(k)}


def summarise(rows: list[dict[str, Any]], difference: dict[str, Any]) -> dict[str, Any]:
    moves = [r for r in rows if r["kind"] not in ("nothing", "back")]
    missing = [r for r in moves if not r["found"]]
    reasons: dict[str, int] = {}
    for r in missing:
        reasons[r["status"]] = reasons.get(r["status"], 0) + 1
    found = [r for r in moves if r["found"]]
    return {
        "moves": len(moves),
        "found": len(found),
        "not_found": len(missing),
        "not_found_by_reason": reasons,
        "not_found_real": sum(r["status"] in REAL for r in missing),
        "not_found_lost": sum(r["status"] in LOST for r in missing),
        "unreadable": sum(bool(r.get("unknown_words")) for r in found),
        "void": sum(r.get("own_words") is None for r in found),
        "blocked": sum(bool(r.get("rules", {}).get("blocked")) for r in found),
        "blocked_as_task": sum(bool(r.get("rules", {}).get("blocked_as_task")) for r in found),
        "hidden_until_hover": sum(bool(r.get("hidden_until_hover")) for r in found),
        "cut_off_on_the_way": sum("cut_off_by_the_window" in (r.get("seen") or []) for r in moves),
        "listed_but_click_misses": sum("listed_but_a_click_misses_it" in (r.get("seen") or []) for r in moves),
        "engine_scroll_cannot_reach": sum("engine_scroll_does_not_move_it" in (r.get("seen") or []) for r in moves),
        "named_differently": sum(r.get("names_same") is False for r in found),
        "out_of_step": sum(r.get("in_step") is False for r in moves),
        "perform_failed": sum(bool(r.get("perform_error")) for r in moves),
        "no_effect": sum(r.get("took") is False for r in moves),
        "saved_equal": not difference,
    }


# ---- the rules, asked about one move -------------------------------------------------------------

def reachable(score_now: float) -> list[str]:
    """The levels a trait's score can pick (variability.level_from)."""
    s = max(0.0, min(10.0, score_now))
    if s in (0.0, 5.0, 10.0):
        return [LEVELS[int(s // 5)]]
    lower = 0 if s < 5 else 1
    return [LEVELS[lower], LEVELS[lower + 1]]


def rule_check(element: dict[str, Any], action: str, value: Any, obs, persona: Persona, vocab, config: dict[str, Any],
               risks: list[str], checks: list[str]) -> dict[str, Any]:
    """Would the choosing rules let him do this, when this is the one thing the model offers? He gets
    every chance: any purpose the model might give it, his own words on the element and the item
    it is marked with as evidence, a fresh memory, and the whole screen read."""
    goal, rules = config["goal"], config["run"]
    task_set, task_nums = task_words(persona.task), task_values(persona.task)
    evidence = [{"type": "word", "ref": element["text"]}] if (element.get("text") or "").strip() else []
    if element.get("kl"):
        evidence.append({"type": "item", "ref": element["kl"]})
    out: dict[str, Any] = {"risks": risks, "checks": checks, "allowed": {}, "as_task": {}, "refused": {}}

    def lets(risk: str, purposes: tuple[str, ...]) -> bool:
        for check in checks:
            policy = Policy(risk=risk, check=check, consequential=rules["consequential_labels"], advancing=goal["advancing_labels"],
                            weights=config["prominence"], viewport=(config["platform"]["viewport_width"], config["platform"]["viewport_height"]))
            for purpose in purposes:
                memory = SessionMemory()
                said = None if action == "click" else value  # a tick is a click: the model names no value for it
                candidate = {"action": action, "element": element["id"], "value": said, "purpose": purpose, "evidence": evidence}
                on = element.get("text")
                verdicts = check_evidence(evidence, persona, memory, obs.hits, obs.visible_text, on)
                own = own_words(on, obs.hits, obs.visible_text) if on else None
                if own:
                    verdicts.append(own)
                s = score(candidate, element, verdicts, obs.signature, place=obs.context)
                d = decide([s], memory, policy, context=obs.signature, whole_screen=True, piece=[element],
                           sim=lambda e: similarity(e, vocab, task_set), task_values=task_nums, place=obs.context,
                           page=obs.route.split("?")[0])
                if d.kind == ACT and d.chosen is s:
                    out["rule"] = f"at {risk} risk: {d.rule}"
                    return True
                out["refused"].setdefault(risk, s.dropped or d.rule)
        return False

    for risk in LEVELS:
        out["as_task"][risk] = lets(risk, (TASK, FIX))
        out["allowed"][risk] = out["as_task"][risk] or lets(risk, PURPOSES)
        if out["allowed"][risk]:
            out["refused"].pop(risk, None)
    out["blocked"] = not any(out["allowed"][r] for r in risks)
    out["blocked_as_task"] = not any(out["as_task"][r] for r in risks)
    return out


# ---- walking one person's moves ------------------------------------------------------------------

class Replay:
    def __init__(self, screen: Screen, persona: Persona, vocab, config: dict[str, Any], risks: list[str], checks: list[str]):
        self.screen, self.persona, self.vocab, self.config = screen, persona, vocab, config
        self.risks, self.checks = risks, checks
        self.gray = [i.id for i in persona.items.values() if i.kind == ICON and i.result == NONE]
        self.step = 0

    def _candidates(self, move: dict[str, Any]) -> list[dict[str, Any]]:
        kind = "control" if move["kind"] == "control" else "field"
        return [c for c in self.screen.page.evaluate(SNAPSHOT, kind) if names_match(move["label"], c["name"]) or names_match(move["label"], c["plain"])]

    @staticmethod
    def _listed(obs, target: dict[str, Any]) -> dict[str, Any] | None:
        if target["i"] is None:
            return None
        return next((e for e in obs.elements if not e.get("virtual") and str(e["index"]) == target["i"]
                     and e["box"]["x"] == target["x"] and e["box"]["y"] == target["y"]), None)

    def _wheel_to(self, target: dict[str, Any]) -> None:
        """The wheel, with the mouse over the panel the control is in, as far as it takes to bring it
        to the middle of that panel. A person aims the wheel and scrolls by eye."""
        screen, page = self.screen, self.screen.page
        middle = target["y"] + target["h"] / 2
        if target.get("scroller"):
            x, y = target["scroller"]["cx"], target["scroller"]["cy"]
        else:
            x, y = target["x"] + target["w"] / 2, screen.page_height / 2
        page.mouse.move(max(1, x), max(1, min(y, screen.page_height - 2)))
        page.mouse.wheel(0, middle - y)
        screen.settle()

    def _engine_scroll_reaches(self, target: dict[str, Any], move: dict[str, Any]) -> bool:
        """Does one turn of the engine's own scroll action move this control? It turns the wheel wherever
        the mouse last was, or over the page's biggest panel when the page itself does not scroll. One
        turn that does not move it is a hint, not proof: the turn may have gone to an inner list first."""
        self.screen._scroll_state()
        self.screen.perform("scroll", None, "up" if target["above"] else "down")
        found = self._candidates(move)
        if not found:
            return False
        return (pick_target(found, move)["y"]) != target["y"]

    def _find(self, move: dict[str, Any]):
        """Looks, scrolling the way a person would until the control is whole in view. Returns the
        look, the control as on the page, the element as on the engine's list, how that went, the
        scrolling it took, and what was off about it on the way (see row "seen")."""
        screen = self.screen
        screen.reveal_hover = False
        scrolls, last, seen = 0, None, []
        while True:
            obs = screen.observe(self.step, self.gray)
            found = self._candidates(move)
            if not found:
                return obs, None, None, "not_in_dom", scrolls, seen
            target = pick_target(found, move)
            element = self._listed(obs, target)
            cut = bool(element) and (element["box"]["y"] < 0 or element["box"]["y"] + element["box"]["h"] > screen.page_height)
            if cut:
                seen.append("cut_off_by_the_window")
            elif target["covered"]:
                seen.append("covered:" + target["covered"])
            if target["missed"]:
                seen.append("listed_but_a_click_misses_it")
                cut = True
            if element and not cut:
                return obs, target, element, "found", scrolls, seen
            place = (target["x"], target["y"])
            if (target["offscreen"] or target["missed"]) and not scrolls:
                if self._engine_scroll_reaches(target, move):
                    seen.append("engine_scroll_moves_it")
                else:
                    seen.append("engine_scroll_does_not_move_it")
                scrolls += 1
                continue
            if (target["offscreen"] or target["covered"] or cut) and target["h"] < screen.page_height and scrolls < MAX_SCROLLS and place != last:
                last = place
                self._wheel_to(target)
                scrolls += 1
                continue
            if element:  # it will not come further into view
                return obs, target, element, "found", scrolls, seen
            if target["opacity0"] and not target["offscreen"]:
                screen.reveal_hover = True
                obs = screen.observe(self.step, self.gray)
                found = self._candidates(move)
                target = pick_target(found, move) if found else target
                element = self._listed(obs, target)
                screen.reveal_hover = False
                if element:
                    return obs, target, element, "found", scrolls, seen + ["hidden_until_hover"]
            return obs, target, None, why_left_out(target), scrolls, seen

    def _describe(self, obs, target: dict[str, Any], element: dict[str, Any], move: dict[str, Any], action: str, value: Any) -> dict[str, Any]:
        rewritten = self.vocab.rewrite(element.get("original") or "")
        verdict = own_words(element.get("text") or "", obs.hits, obs.visible_text)
        unknown = [h.original for h in rewritten.hits if h.level == NONE]
        row: dict[str, Any] = {
            "shown": element.get("text"),
            "original": element.get("original"),
            "names_same": thing(element.get("original")) == thing(move["label"]),
            "understanding": element.get("understanding"),
            "own_words": {"level": verdict.level, "ref": verdict.ref, "reason": verdict.reason} if verdict and verdict.level != VOID else None,
            "unknown_words": unknown,
            "font_size": (element.get("font") or {}).get("size"),
            "kl": element.get("kl"),
            "disabled": element.get("disabled"),
            "box": element.get("box"),
            "rules": rule_check(element, action, value, obs, self.persona, self.vocab, self.config, self.risks, self.checks),
        }
        if action == "choose":
            # The option as his list names it, found by its place: what the engine's choose compares with.
            originals = [thing(o) for o in target.get("options") or []]
            listed = element.get("options") or []
            at = originals.index(thing(value)) if thing(value) in originals else None
            row["option_shown"] = listed[at] if at is not None and at < len(listed) else str(value)
            row["option_readable"] = all(h.level != NONE for h in self.vocab.rewrite(str(value)).hits)
            row["options_listed"], row["selected_shown"] = listed, element.get("selected")
        return row

    def _act(self, move: dict[str, Any], target: dict[str, Any], element: dict[str, Any], row: dict[str, Any], action: str, value: Any) -> None:
        screen = self.screen
        try:
            if action == "click":
                if move["kind"] == "field" and target.get("checked") == value:
                    row["note"] = "already so"
                else:
                    row["note"] = screen.perform("click", element, None)
            elif action == "choose":
                row["note"] = screen.perform("choose", element, row["option_shown"])
            elif action == "type":
                if _same_value(target.get("value"), value):
                    row["note"] = "already so"
                else:
                    row["note"] = screen.perform("type", element, value)
            if move["kind"] == "enter":
                row["note"] = (row.get("note") or "") + "; " + screen.perform("press", element, "Enter")
        except Exception as error:  # noqa: BLE001 - a failure of the engine's own hands is a finding, and the walk goes on
            row["perform_error"] = str(error).splitlines()[0][:300]
            row["same_index"] = screen.page.evaluate(  # what the engine's _handle finds under this element's number
                "i => [...document.querySelectorAll(`[data-sue-i=\"${i}\"]`)].map((e) => e.tagName.toLowerCase() + ':' + (e.innerText || e.value || '').slice(0, 30))",
                element["index"])
            if move["kind"] == "field" and action == "choose":
                self._force_choice(target, value)
        if str(row.get("note", "")).startswith("not done"):
            row["perform_error"] = row["note"]
            if action == "choose":
                self._force_choice(target, value)
        if move["kind"] == "field":
            self._check_took(move, target, row)

    def _force_choice(self, target: dict[str, Any], value: Any) -> None:
        """The engine's hands failed: the page is put where the person's was, so the walk can go on."""
        self.screen.page.evaluate(
            """([n, want]) => {
                 const el = document.querySelectorAll('input, select, textarea')[n];
                 if (!el || el.tagName !== 'SELECT') return;
                 const said = (o) => ((o.firstChild && o.firstChild.__sueOrig) || o.textContent).trim();
                 const i = [...el.options].findIndex((o) => said(o) === want);
                 if (i >= 0) { el.selectedIndex = i; el.dispatchEvent(new Event('change', { bubbles: true })); }
               }""", [target["n"], str(value)])

    def _check_took(self, move: dict[str, Any], target: dict[str, Any], row: dict[str, Any]) -> None:
        now = self._candidates(move)
        if not now or target.get("row", 0) >= len(now):
            return  # the form moved on or was drawn again without that field
        c = now[target.get("row", 0)]
        value = move.get("value")
        row["took"] = (c.get("checked") == value) if isinstance(value, bool) else _same_value(c.get("value"), value)

    def do(self, move: dict[str, Any]) -> dict[str, Any]:
        self.step += 1
        page = self.screen.page
        row: dict[str, Any] = {"seq": move["seq"], "kind": move["kind"], "label": move["label"], "recorded_route": move.get("route"),
                               "recorded_screen": move.get("screen"), "found": False}
        if move["kind"] == "nothing":
            row["found"] = True
            if move.get("x") is not None and page.evaluate(QUIET_SPOT, [move["x"], move["y"]]):
                page.mouse.click(move["x"], move["y"])
                self.screen.settle()
                row["note"] = "clicked the same empty spot"
            else:
                row["note"] = "skipped: something else is at that spot now"
            return row
        if move["kind"] == "back":
            row["found"] = True
            row["note"] = self.screen.perform("back", None, None)
            return row
        try:
            obs, target, element, status, scrolls, seen = self._find(move)
        except RewriteError as error:
            row.update(status="rewrite_error", error=str(error))
            return row
        where = page.evaluate(WHERE)
        row.update(status=status, scrolls=scrolls, seen=seen, route_now=where["route"], screen_now=where["screen"],
                   in_step=(move.get("route") in (None, where["route"])) and _same_screen(move.get("screen"), where["screen"]))
        if target:
            row["target"] = {k: target.get(k) for k in ("tag", "type", "role", "clickable", "shown", "offscreen", "covered", "opacity0", "disabled", "row", "aria", "value", "checked", "x", "y", "w", "h")}
        if not element:
            return row
        row["found"] = True
        row["hidden_until_hover"] = "hidden_until_hover" in seen
        if move["kind"] == "control":
            action, value = "click", None
        elif target["tag"] == "select":
            action, value = "choose", move.get("value")
        elif target.get("checked") is not None:
            action, value = "click", move.get("value")
        else:
            action, value = "type", move.get("value")
        row["action"] = action
        row.update(self._describe(obs, target, element, move, action, value))
        self._act(move, target, element, row, action, value)
        return row


def _same_screen(recorded: str | None, now: str | None) -> bool:
    if not recorded:
        return True
    squeeze = lambda t: re.sub(r"\s+", "", str(t or "")).lower()  # noqa: E731
    return squeeze(recorded) == squeeze(now)


def replay_person(path: Path, config: dict[str, Any], log=print) -> dict[str, Any]:
    person = load(path)
    workflow = config["workflow"]
    name = person["questionnaire"]["answers"]["name"]
    card = card_of(Path(config["paths"]["personas"]), name, workflow["name"])
    if not card:
        raise ValueError(f"{name}: no card; import {path.name} in Persona Studio first")
    w, h = (int(x) for x in engine_window(person).split("x"))
    config["platform"]["viewport_width"], config["platform"]["viewport_height"] = w, h
    persona = load_card(config["paths"]["personas"], card, workflow.get("file"))
    vocab = build_vocabulary(persona, config)
    traits = traits_of(persona.version, persona.tendency, persona.state, persona.perception)
    var = make(traits, config, 0)
    risks, checks = reachable(var.score("risk")), reachable(var.score("detailCheck"))
    target = make_target(config)
    session = target.start(model_id="replay", prompt_version="replay", persona_id=card)
    strip = Strip(persona.task, config["platform"]["harness_button_text"], w)
    rows: list[dict[str, Any]] = []
    moves = replay_moves(person["events"])
    with sync_playwright() as pw:
        browser, page = open_browser(pw, config, headless=True, strip=strip, state=None)
        screen = Screen(page, vocab, config, reveal_hover=False, strip=strip)
        screen.color = traits.color
        target.prepare(page)
        page.goto(session.link)
        walker = Replay(screen, persona, vocab, config, risks, checks)
        for move in moves:
            row = walker.do(move)
            rows.append(row)
            if is_real_move(move):
                log(f"  {name} {row['seq']:>4} {row.get('status', ''):<13} {move['label'][:44]!r:<48} shown {str(row.get('shown'))[:34]!r} "
                    f"own {(row.get('own_words') or {}).get('level', 'void' if row['found'] else '-')} "
                    f"{'BLOCKED' if row.get('rules', {}).get('blocked') else 'blocked-as-task' if row.get('rules', {}).get('blocked_as_task') else ''}{' ' + row['perform_error'][:80] if row.get('perform_error') else ''}")
        stored = page.evaluate(STORED)
        browser.close()
    difference = saved_difference(person.get("product"), stored)
    return {"name": name, "card": card, "window": f"{w}x{h}",
            "risk": traits.risk, "risks": risks, "check": traits.check, "checks": checks,
            "summary": summarise(rows, difference), "saved_difference": difference, "rows": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walks each person's real moves through their card, with no model")
    parser.add_argument("--flow", required=True, help="the workflow's flow.json")
    parser.add_argument("--participants", required=True, help="the folder of participant files")
    parser.add_argument("--only", action="append", help="a participant id, such as 001; repeat for more (default all)")
    parser.add_argument("--out", required=True, help="the JSON result, outside the repository")
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    if out.is_relative_to(Path(__file__).resolve().parents[4]):
        print(f"--out must be outside the repository: {out}", file=sys.stderr)
        return 1
    config = load_config(flow=args.flow)
    people = []
    for path in sorted(Path(args.participants).glob("participant-*.json")):
        pid = load(path)["session"]["participantId"]
        if args.only and pid not in args.only:
            continue
        print(f"\n##### {path.name}")
        result = replay_person(path, config)
        people.append(result)
        # after each person, so an interrupted walk keeps what it has
        out.write_text(json.dumps({"people": people}, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{result['name']}: {json.dumps(result['summary'], ensure_ascii=False)}")
    print(f"\nSaved to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
