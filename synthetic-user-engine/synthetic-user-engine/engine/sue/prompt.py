"""Step 4's input and output (engine-design.md 4.2).

The prompt carries no personality and no identity. It has only four things: the
processed screenshot (sent beside the text), the visible elements with what he takes
them to mean, the items he knows or vaguely remembers, and the task with his idea of
done. The model lists candidates with evidence; code decides."""

from __future__ import annotations

import json
import re
from typing import Any

from .completion import ways_text
from .persona import Persona

PROMPT_VERSION = "engine-p2-v4-en"  # recorded on the platform session; bump on any prompt change

ACTIONS = ["click", "type", "scroll", "back", "open_help"]

# What a candidate is for. Code weighs it with the person's tendencies (engine-design.md 3.2, 4.3).
TASK, FIX, CHECK, EXPLORE, RETREAT = "advance", "fix", "check", "explore", "retreat"
PURPOSES = [TASK, FIX, CHECK, EXPLORE, RETREAT]

SYSTEM = """You are helping a person use a web page. You see only what they see: a screenshot, and the list of the clickable elements on it.

The text in the screenshot has already been processed to match this person's understanding. Words they do not understand have been replaced with meaningless made-up words, and icons they do not recognise are covered with gray blocks. Do not guess what a made-up word was: a made-up word is a word they cannot read. Where the element list marks a word "knows only the everyday meaning" or "reads it as", take the word in that marked sense.

People do not take in a whole screen at once. Only the part they are looking at is clear in the screenshot; the rest is covered, and the element list shows only that part.

Your job is to list every action they might take in this part, each with its evidence and its purpose. Do not list only the one you are surest of: other rules decide which one is done, not you. The purpose is one of five:
- advance: a direct step toward finishing the task, such as choosing the option the task asks for or clicking Next.
- fix: a value or setting here does not match the task; change it or delete it.
- check: something here is unclear to them, or they are not sure it is set right; open it, expand it, open a dropdown to see the options, or try selecting it.
- explore: there is nothing to do in this part; click into somewhere else to look.
- retreat: go back to the previous page, or close what was just opened.
If there is really nothing to do in this part, candidates may be empty; they will look elsewhere.

Evidence is of two kinds only. Your own experience with this kind of website is never evidence:
- A word on screen: type "word", and ref copies the text on screen exactly as they see it.
- Something they know: type "item", and ref is the item id, such as T04.
An action with no evidence may still be listed, with evidence left empty.

The actions:
- click: click an element.
- type: type value into a text box.
- scroll: value is down or up.
- back: go back to the previous page.
- open_help: click a question-mark icon or similar to read the help.

element is the element id, such as el_12; scroll and back need none. List at most {max_candidates}. Output JSON only."""

# The completion question names what the workflow makes (flow.json engine.created; Version A: budget).
# For Version A the text and the schema are exactly what they were, so PROMPT_VERSION stays.


def list_key(created: str) -> str:
    """The observation the model answers in, e.g. list_has_new_budget."""
    return "list_has_new_" + re.sub(r"[^a-z0-9]+", "_", created.lower()).strip("_")


def list_question(created: str, article: str | None = None) -> str:
    """article: from flow.json engine.createdArticle when the first letter misleads (a user, an hour)."""
    article = article or ("an" if created[:1].lower() in "aeiou" else "a")
    return (f"Also answer one question, in observations.{list_key(created)}: is there a list on this screen with {article} {created} in it? "
            "answer is true or false. If true, quote copies that row's text exactly as they see it. Only what is on screen; do not guess.")


def response_schema(created: str) -> dict[str, Any]:
    return {
    "type": "object",
    "properties": {
        "observations": {
            "type": "object",
            "properties": {
                list_key(created): {
                    "type": "object",
                    "properties": {"answer": {"type": "boolean"}, "quote": {"type": "string"}},
                    "required": ["answer"],
                },
            },
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "element": {"type": "string"},
                    "action": {"type": "string", "enum": ACTIONS},
                    "value": {"type": "string"},
                    "purpose": {"type": "string", "enum": PURPOSES},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string", "enum": ["word", "item"]},
                                "ref": {"type": "string"},
                            },
                            "required": ["type", "ref"],
                        },
                    },
                    "why": {"type": "string"},
                },
                "required": ["action", "purpose", "evidence", "why"],
            },
        },
    },
    "required": ["candidates"],
    }


def _kind(e: dict[str, Any]) -> str:
    tag, role, typ = e["tag"], e.get("role", ""), e.get("type", "")
    if typ == "checkbox" or role == "checkbox":
        return "checkbox (ticked)" if e.get("checked") else "checkbox (not ticked)"
    if typ == "radio" or role == "radio":
        return "radio button (selected)" if e.get("checked") else "radio button (not selected)"
    if tag in ("input", "textarea"):
        return f"text box (now {e['value']!r})" if e.get("value") else "text box (empty)"
    if role == "option":
        return "option"
    if e.get("icon"):
        return "icon button (the text is what the icon means)"
    if e.get("expanded") is not None:
        return "dropdown (open)" if e["expanded"] else "dropdown"
    if tag == "a":
        return "link"
    return "button"


def element_lines(elements: list[dict[str, Any]]) -> list[str]:
    lines = []
    for e in elements:
        text = e["text"] or "(no text)"
        line = f"{e['id']} | {_kind(e)}{', disabled' if e.get('disabled') else ''} | {text}"
        if e.get("understanding"):
            line += " | " + "; ".join(e["understanding"])
        lines.append(line)
    return lines


def build_turn(persona: Persona, elements: list[dict[str, Any]], scroll: dict[str, int], ask_list: bool = False,
               history: list[str] | None = None, looking_at: str | None = None, situation: str | None = None,
               created: str = "", article: str | None = None) -> str:
    """created: what the workflow makes (config["workflow"]["created"]); needed when ask_list."""
    if ask_list and not created:
        raise ValueError("ask_list needs created: what the workflow makes, from flow.json engine.created")
    known, vague = persona.knowledge_lines()
    done = ways_text(persona.goal.get("confirmBy") or []) or "not given"
    parts = [
        "The task (verbatim):",
        persona.task,
        "",
        f"How they make sure it is done: {done}",
        "",
        "What they know:",
        *(f"- {k}" for k in known or ["(nothing)"]),
        "",
        "What they vaguely remember but are not sure of:",
        *(f"- {v}" for v in vague or ["(nothing)"]),
        "",
        "What they did recently (oldest first):",
        *(f"- {h}" for h in history or ["(just started; nothing yet)"]),
        "",
        *([f"Their situation now: {situation}", ""] if situation else []),
        f"They are looking at: {looking_at or 'the whole screen'}",
        "Clickable elements in this part (id | kind | text they see | how they understand it):",
        *(element_lines(elements) or ["(nothing clickable in this part)"]),
        "",
        f"More content below: {'yes' if scroll.get('y', 0) < scroll.get('max', 0) else 'no'}",
    ]
    if ask_list:
        parts += ["", list_question(created, article)]
    return "\n".join(parts)


class ReplyError(ValueError):
    """The model's reply cannot be used."""


def parse_reply(text: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Returns the usable candidates and the observations (possibly empty)."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise ReplyError(f"invalid JSON: {error}") from error
    candidates = data.get("candidates") if isinstance(data, dict) else None
    if not isinstance(candidates, list):
        raise ReplyError("no candidates list")
    out = []
    for c in candidates:
        if not isinstance(c, dict) or c.get("action") not in ACTIONS:
            continue
        c.setdefault("evidence", [])
        if c.get("purpose") not in PURPOSES:
            c["purpose"] = TASK
        out.append(c)
    observations = data.get("observations")
    return out, observations if isinstance(observations, dict) else {}
