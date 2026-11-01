"""What went wrong, part by part, read from what happened (2026-11-01).

A person's event log and an engine run's steps are first put into the same plain facts, and one piece
of code then looks for trouble in those facts, so both sides are held to the same yardstick. What counts
as trouble, each with what it means for the person:

- lost the way: before the form, a click that is not on the way to it (flow.json engine.compare.way);
- changed a value: a setting given one value, then another (typing the same value again is not one);
- went back: in the form, back to a section already passed;
- left unsaved: out of the form without saving, losing the work;
- wrong when saved: the saved value fails the task's check (parts.wrong_parts).

Pressing OK twice, or opening a dropdown and picking the option of the same name, is none of these.
The answer on the six people was read off their logs by eye first; tests/test_events.py holds it."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .parts import AFTER, BEFORE, read_steps, wrong_parts

LOST, CHANGED, WENT_BACK, UNSAVED, WRONG = "lost the way", "changed a value", "went back", "left unsaved", "wrong when saved"


@dataclass(frozen=True)
class Fact:
    part: str
    kind: str  # click, value, section, left, saved
    what: str = ""
    value: str = ""


def _plain(label: Any) -> str:
    return re.sub(r"\s*[⌄⋮]\s*$", "", str(label or "")).strip()


def _number(value: Any) -> str:
    """So that $800, 800 and 800% are one value; words stay as they are, whatever the case."""
    text = str(value if value is not None else "").strip().lower()
    return re.sub(r"[$,%\s]", "", text) if re.fullmatch(r"[$\s\d,.%]+", text) else text


def person_facts(events: Iterable[dict[str, Any]], parts: list[str], options: dict[str, str]) -> list[Fact]:
    """A participant file's events. A form section is entered when its screen is shown; leaving it for a
    screen that is not a section, with no save just before, is leaving it unsaved."""
    out: list[Fact] = []
    part, saved_now, saved = BEFORE, False, False
    in_form = False
    for e in events:
        payload = e.get("payload") if isinstance(e.get("payload"), dict) else {}
        kind = e.get("type")
        if kind == "save_succeeded":
            saved_now, saved = True, True
            out.append(Fact(part, "saved"))
        elif kind == "screen_viewed":
            screen = str(e.get("target") or "")
            section = next((p for p in parts if screen.endswith(p)), None)
            if section:
                if section != part or not in_form:
                    out.append(Fact(section, "section", section))
                part, in_form = section, True
            else:
                if in_form and not saved_now:
                    out.append(Fact(part, "left"))
                part, in_form = (AFTER if saved else BEFORE), False
            saved_now = False
        elif kind == "field_changed":
            field = _plain(payload.get("field") or e.get("target"))
            out.append(Fact(part, "value", field, _number(payload.get("value"))))
        elif kind == "control_clicked":
            label = _plain(e.get("target"))
            out.append(Fact(part, "value", options[label], label.lower()) if label in options else Fact(part, "click", label))
    return out


def _kind_of(prompt: str | None, element: str | None) -> str:
    for line in (prompt or "").splitlines():
        if element and line.startswith(element + " |"):
            return line.split("|")[1]
    return ""


def engine_facts(steps: Iterable[dict[str, Any]], parts: list[str], options: dict[str, str], commit: Iterable[str] = ()) -> list[Fact]:
    """An engine run's steps, by the same names. A box's value is what the click leaves it as."""
    final = {c.lower() for c in commit}
    rows = list(steps)
    out: list[Fact] = []
    part, saved, in_form = BEFORE, False, False
    for r in rows:
        section = (r.get("signature") or "").split("|")
        section = section[1] if len(section) > 1 else ""
        here = next((p for p in parts if p in section), None)
        if here:
            if here != part or not in_form:
                out.append(Fact(here, "section", here))
            part, in_form = here, True
        elif in_form:  # out of the form: by its final button, the previous step says so
            last = (out[-1].kind == "saved") if out else False
            if not last:
                out.append(Fact(part, "left"))
            part, in_form = (AFTER if saved else BEFORE), False
        a = r.get("action") or {}
        kind, label = a.get("type"), _plain(a.get("aria") or a.get("original") or a.get("text"))
        if kind not in ("click", "type", "choose", "press", "open_help") or a.get("misclick") or str(a.get("note") or "").endswith("the test's own bar)"):
            continue
        if kind in ("type", "choose"):
            out.append(Fact(part, "value", label, _number(a.get("value"))))
        elif kind == "click" and label in options:
            out.append(Fact(part, "value", options[label], label.lower()))
        elif kind == "click" and "checkbox" in _kind_of(r.get("prompt"), a.get("element")):
            out.append(Fact(part, "value", label, "false" if "(ticked)" in _kind_of(r.get("prompt"), a.get("element")) else "true"))
        elif kind == "click":
            out.append(Fact(part, "click", label))
        if str(a.get("text") or "").strip().lower() in final:
            saved = True
            out.append(Fact(part, "saved"))
    return out


def troubles(facts: Iterable[Fact], parts: list[str], way: Iterable[str], free_text: Iterable[str] = ()) -> list[tuple[str, str, str]]:
    """(part, kind of trouble, what) for everything that went wrong in a session, saved values aside."""
    on_way = {w.lower() for w in way}
    free = {f.lower() for f in free_text}
    out: list[tuple[str, str, str]] = []
    values: dict[str, str] = {}
    previous = -1
    for f in facts:
        if f.kind == "section":
            at = parts.index(f.part)
            if at < previous:
                out.append((f.part, WENT_BACK, f"from a later section back to {f.part}"))
            previous = at
        elif f.kind == "left":
            out.append((f.part, UNSAVED, f"left the form from {f.part}"))
        if f.kind in ("left", "saved"):  # a new form starts clean
            values, previous = {}, -1
        elif f.kind == "click" and f.part == BEFORE and f.what.lower() not in on_way:
            out.append((BEFORE, LOST, f.what))
        elif f.kind == "value":
            if f.part == BEFORE and f.what.lower() not in on_way:
                out.append((BEFORE, LOST, f.what))
            elif f.what.lower() not in free and f.part != AFTER:
                if f.what in values and values[f.what] != f.value:
                    out.append((f.part, CHANGED, f"{f.what}: {values[f.what]} to {f.value}"))
                values[f.what] = f.value
    return out


def person_trouble(person: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str, str]]:
    c = config["compare"]
    facts = person_facts(person["events"], c["parts"], c["options"])
    out = troubles(facts, c["parts"], c["way"], c["free_text"])
    return out + [(p, WRONG, "the saved value fails the check") for p in sorted(wrong_parts(person.get("product"), config["workflow"]["target"]["success"], c["field_parts"]))]


def run_trouble(run_dir: str, summary: dict[str, Any], config: dict[str, Any]) -> list[tuple[str, str, str]]:
    c = config["compare"]
    facts = engine_facts(read_steps(run_dir), c["parts"], c["options"], config["run"].get("commit_labels") or [])
    out = troubles(facts, c["parts"], c["way"], c["free_text"])
    wrong = wrong_parts(summary.get("stored"), config["workflow"]["target"]["success"], c["field_parts"], summary.get("last_saved"))
    return out + [(p, WRONG, "the saved value fails the check") for p in sorted(wrong)]
