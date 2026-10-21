"""A draft flow.json from one recording (engine-design.md 6.3).

What can be read off the recording is never left to the model: the screens and their routes,
the order of the actions, the scripted success path (engine.plumbing), which control each item
is on and its locator, the routes on the path, the start page and the sign-in. The model drafts
what needs judgement, from the screens' text and controls: names for the screens, steps that
group the actions, the knowledge items a person needs at each step (words, places, ideas, icons,
habits from other products), the experiences that teach them with their questions in English and
Chinese, Persona Studio's knowledge groups, which buttons commit, the data words, and what the
task should leave behind. A researcher then reviews and confirms every part in the platform;
nothing runs on a draft that has not been confirmed.

    python -m sue.draft --recording ../data/workflows/x/recording/recording.json --basics basics.json --out flow.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from . import locate
from .config import load_config, load_env, require_env
from .workflow import problems as engine_problems

KINDS = ("word", "icon", "location", "concept", "habit")
INFO = ("newtab", "download")  # written down while recording, but not something the person does
SOURCES = [
    {"id": "product", "label": {"en": "Products and tools", "zh": "用过的产品和工具"}},
    {"id": "work", "label": {"en": "Work", "zh": "工作经历"}},
    {"id": "study", "label": {"en": "Study", "zh": "学习经历"}},
    {"id": "life", "label": {"en": "Everyday life", "zh": "日常生活"}},
]
MAX_CONTROLS, MAX_TEXT = 140, 2500

SYSTEM = """You help a UX researcher prepare a usability test that a synthetic user engine will run. You are given one recording of the researcher doing the task correctly on a web product: every screen (its route, its visible text, and its numbered controls) and every action. Draft the parts of the workflow definition that need judgement. Do not invent screens, controls or actions that are not in the recording, and refer to them only by their numbers.

The engine simulates people with different knowledge. Your most important output is the knowledge items: what a person must know, at each step, to do the task correctly. Kinds:
- word: a term shown on screen whose meaning matters for this task (a product term, a label, a menu name). text is the term exactly as on screen. meaning: what it means in this product. everyday: if the term is an ordinary English word or phrase, its everyday sense when that differs (else ""). common: "common" if a typical adult English speaker knows the word, "rare" if only educated or specialist speakers do, "none" if it is product jargon.
- icon: a control shown only as a picture that the task relies on (the controls list marks it "icon only"; its label is what it shows). text says what it shows and does. A help button drawn as a question mark is an icon, never a word.
- location: where something is or how to get there ("Invites are under People in the left menu").
- concept: how something in this product works that the task depends on ("Unticked projects are not shared with the new member").
- habit: a habit from other products that could mislead here ("In many apps, inviting someone gives them access to everything").
Give each item a key (i1, i2, ...), the key of the step it belongs to, needed (true when a person cannot finish correctly without it), and, when it is about one control, onAction: the number of the action that used it (a5 is 5), or else onScreen and onControl: the screen number and the control number (screen 3, c12 is 3 and 12). Use onAction 0, onScreen -1 and onControl -1 for an item that is not about one control, and explainedBy "" when no help text explains it. For a help icon, explainedBy is a short phrase copied exactly from the help text that opens. Mark entry=true on the location item that says where the task's starting control is, help=true on an icon that opens help, review=true on a link that opens what was just made to check it. Typically 15 to 40 items. Include the defaults a person must change, and the traps.

Experiences are things a person may have done that teach some items, asked in a questionnaire: each has a key (e1, e2, ...), a group key, text (third person), and the question in English and in Simplified Chinese. Groups belong to a source: product (products and tools used), work, study or life; each group has a key and English and Chinese labels. Link every item to the experiences that would teach it (exps: their keys).

Knowledge groups are how a persona editor sets knowledge in bulk: a few themes (4 to 10), each with a key (lower-case, short), a title, a description, examples, default (0 unknown, 1 partly, 2 known, for a typical user of this product), word=true for a group of word items only, else only non-word items, and items: the item keys. Every item that is not a habit is in exactly one group.

Steps, each with a key (s1, s2, ...), group consecutive actions on the same screen into what a person would call one step ("Fill in the email and display name, then click Continue"). actions lists the action numbers (a3 is 3). Every action is in exactly one step, in order. risky: a step whose mistake is costly or hard to undo. defaults: the defaults on that screen the task requires changing, in words, or "".

Also: created, what the task makes, as a short noun as a list would show it (invite, budget, user); consequential, the labels of buttons that commit or cancel something (Send, Save, Delete, Cancel); advancing, labels that only move on (Next, Continue); listRoute, the route of the page that lists what was made, if any; listQuote, the text that page shows for the new one (usually a name typed during the task); dataTerms, names and values in the simulated data that are always shown as they are: names of people, projects, companies, email addresses and ids, never product terms or option names; forceFake, jargon that most people would not know even if it looks English; signals, which confirmations the product gives the person doing the task (toast: a success message, list: what was made appears in a list, external: an email or notification to them, test: it can be triggered to see it work); checks, the task's success criteria in plain words; success, machine checks of what the task should leave behind, each named by a short plain sentence a report can show ("Priya is invited as a viewer of Lyra only", never code like check_invite), which must still be true later (never a message that disappears), one per criterion where possible. Prefer type "json" when the recording shows where what was saved can be read: a request that sent it (POST) and a GET of the same path, even if that GET answered an empty list before the task, or a GET whose answer later holds it. Check every value the task asks for (who, which role, which projects), not only that the row exists: {name, type: "json", url: a GET path from the requests, list: the dotted path to the list in the answer if it is not the answer itself, where: [{field, value}] picking the new row, expect: [{field, value}] its values; a list value is written as JSON, e.g. ["Lyra"]}. Else {name, type: "text", url: a route to open, contains: text that must be on it} or {name, type: "url", matches: a regular expression for the final address}; org, one sentence on who the person is in the product and what they may do; situation {urgency: calm or urgent, stakes: low or high}; outcome, what the task leaves behind: {kind: "change"} when it saves or changes something in the product, {kind: "answer", question: the question the person must answer in a few words, expected: the right answers as they appear on the recorded screens} when the task asks them to find something out and tell it, {kind: "place", heading: the heading of the page they must reach} when it asks them to find a page.

Write in plain, short English. Output JSON only."""


def schema() -> dict[str, Any]:
    s = {"type": "string"}
    i = {"type": "integer"}
    b = {"type": "boolean"}
    arr = lambda x: {"type": "array", "items": x}  # noqa: E731
    obj = lambda props, req=None: {"type": "object", "properties": props, "required": req or list(props)}  # noqa: E731
    return obj({
        "screens": arr(obj({"route": s, "name": s})),
        "steps": arr(obj({"key": s, "actions": arr(i), "action": s, "risky": b, "defaults": s})),
        "items": arr(obj({"key": s, "step": s, "kind": {"type": "string", "enum": list(KINDS)}, "text": s, "meaning": s, "everyday": s,
                          "common": {"type": "string", "enum": ["common", "rare", "none"]}, "needed": b,
                          "onAction": i, "onScreen": i, "onControl": i, "explainedBy": s,
                          "entry": b, "help": b, "review": b, "exps": arr(s), "basis": s},
                         ["key", "step", "kind", "text", "meaning", "everyday", "common", "needed", "onAction", "onScreen",
                          "onControl", "explainedBy", "entry", "help", "review", "exps", "basis"])),
        "groups": arr(obj({"key": s, "source": {"type": "string", "enum": [x["id"] for x in SOURCES]}, "labelEn": s, "labelZh": s})),
        "experiences": arr(obj({"key": s, "group": s, "text": s, "questionEn": s, "questionZh": s})),
        "knowledgeGroups": arr(obj({"key": s, "title": s, "description": s, "examples": s, "default": i, "word": b,
                                    "items": arr(s)})),
        "created": s, "consequential": arr(s), "advancing": arr(s), "listRoute": s, "listQuote": s,
        "dataTerms": arr(s), "forceFake": arr(s),
        "signals": obj({"toast": b, "list": b, "external": b, "test": b}),
        "checks": arr(s),
        "success": arr(obj({"name": s, "type": {"type": "string", "enum": ["json", "text", "url"]}, "url": s, "list": s,
                            "where": arr(obj({"field": s, "value": s})), "expect": arr(obj({"field": s, "value": s})),
                            "contains": s, "matches": s}, ["name", "type"])),
        "org": s,
        "situation": obj({"urgency": {"type": "string", "enum": ["calm", "urgent"]}, "stakes": {"type": "string", "enum": ["low", "high"]}}),
        "outcome": obj({"kind": {"type": "string", "enum": ["change", "answer", "place"]}, "question": s, "expected": arr(s), "heading": s},
                       ["kind"]),
    }, ["outcome", "screens", "steps", "items", "groups", "experiences", "knowledgeGroups", "created", "consequential", "advancing",
        "dataTerms", "signals", "checks", "success", "org", "situation"])


# ---- what the model sees ---------------------------------------------------------------------

def control_line(i: int, c: dict[str, Any]) -> str:
    bits = [f"c{i}", c.get("role") or c.get("tag") or "", (c.get("text") or "")[:80] or "(icon only)"]
    if c.get("label") and c.get("label") != c.get("text"):
        bits.append(f"label: {c['label'][:60]}")
    if c.get("region") and c["region"] != "other":
        bits.append(f"in {c['region']}")
    if c.get("group"):
        bits.append(f"under {c['group'][:40]}")
    if c.get("checked") is not None:
        bits.append("ticked" if c["checked"] else "not ticked")
    if c.get("value"):
        bits.append(f"value {c['value'][:40]!r}")
    return " | ".join(b for b in bits if b)


def action_line(a: dict[str, Any], recording: dict[str, Any]) -> str:
    state = recording["states"][a["before"]]
    c = a.get("control") or {}
    idx = next((i for i, o in enumerate(state["controls"]) if _same_control(o, c)), None)
    where = f"screen {a['before']}" + (f" control c{idx}" if idx is not None else "")
    name = c.get("text") or c.get("label") or c.get("role") or "control"
    if a["action"] == "type":
        what = "typed a password" if a.get("secret") else f"typed {a.get('value', '')!r} into {name!r}"
    elif a["action"] == "select":
        what = f"chose {a.get('value', '')!r} in {name!r}"
    elif a["action"] == "press":
        what = f"pressed {a.get('key', 'Enter')}" + (f" in {name!r}" if a.get("control") else "")
    elif a["action"] == "drag":
        t = a.get("target") or {}
        what = f"dragged {name!r} onto {t.get('text') or t.get('label') or 'another element'!r}"
    elif a["action"] == "upload":
        what = f"uploaded {', '.join(a.get('files') or []) or 'a file'} in {name!r}"
    elif a["action"] == "newtab":
        return f"(a{a['n']}: a new tab opened on {a.get('route', '')}); screen {a['after']}"
    elif a["action"] == "download":
        return f"(a{a['n']}: the product gave a file to download: {a.get('value', '')})"
    else:
        what = f"clicked {name!r}"
    return f"a{a['n']}: {what} ({where}); then screen {a['after']}"


def _same_control(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return all(a.get(k) == b.get(k) for k in ("tag", "role", "text", "label", "region", "group")) and (
        abs((a.get("box") or {}).get("x", 0) - (b.get("box") or {}).get("x", 0)) < 4 and
        abs((a.get("box") or {}).get("y", 0) - (b.get("box") or {}).get("y", 0)) < 40)


def prompt(recording: dict[str, Any], basics: dict[str, Any]) -> str:
    lines = [
        f"Product: {basics.get('product') or '(not given)'}",
        f"Who uses it: {basics.get('users') or '(not given)'}",
        f"Workflow name: {basics['name']}",
        "The task as participants read it:", basics["task"], "",
        "Screens:",
    ]
    for st in recording["states"]:
        lines += ["", f"screen {st['n']}: route {st['route']}, title {st.get('title', '')!r}",
                  "controls:", *[control_line(i, c) for i, c in enumerate(st["controls"][:MAX_CONTROLS])],
                  "text:", (st.get("text") or "")[:MAX_TEXT]]
    lines += ["", "Actions, in order:", *[action_line(a, recording) for a in recording["actions"]]]
    net = recording.get("network") or []
    if net:
        lines += ["", "Requests the product made (after action N; answers shortened):"]
        for r in net[:40]:
            lines.append(f"after a{r['after']}: {r['method']} {r['path']} -> {r['status']}"
                         + (f" sent {json.dumps(r['sent'], ensure_ascii=False)[:400]}" if r.get("sent") else "")
                         + f" answer {json.dumps(r['answer'], ensure_ascii=False)[:600]}")
        gets = {r["path"] for r in net if r["method"] == "GET" and (r.get("status") or 0) < 400}
        for r in net:
            if r["method"] != "GET" and r.get("sent") and r["path"] in gets:
                lines.append(f"What the task saved can be read back: it sent {r['method']} {r['path']} and the product "
                             f"reads GET {r['path']}. Check the new row there.")
    return "\n".join(lines)


def ask(text: str, config: dict[str, Any]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    response = client.models.generate_content(
        model=config["model"]["id"], contents=[types.Part.from_text(text=text)],
        config=types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json",
                                           response_json_schema=schema(), temperature=0.0,
                                           http_options=types.HttpOptions(timeout=300_000)))
    return json.loads(response.text)


# ---- the draft, assembled by code ---------------------------------------------------------------

WORD = re.compile(r"[A-Za-z][A-Za-z'-]{2,}")
STOP = {"the", "and", "for", "with", "from", "that", "this", "into", "under", "next", "button", "link", "icon", "page",
        "click", "opens", "open", "shows", "show", "they", "their", "can", "only", "not", "are", "its", "one", "you", "all"}


def words(text: str | None) -> set[str]:
    return {w.lower() for w in WORD.findall(text or "") if w.lower() not in STOP}


def appeared(recording: dict[str, Any], action: dict[str, Any]) -> list[str]:
    """Lines of text that were not on the screen before the action and are after it: what a
    click opened, such as a help popover."""
    before = set((recording["states"][action["before"]].get("text") or "").splitlines())
    after = (recording["states"][action["after"]].get("text") or "").splitlines()
    return [ln.strip() for ln in after if ln.strip() and ln not in before]


def tie(row: dict[str, Any], step_actions: list[dict[str, Any]], recording: dict[str, Any]) -> tuple[dict[str, Any], int] | None:
    """The control an item is about, found by code: (state, control index), or None.

    An icon item: the picture-only control at its step whose name shares most words with it.
    A word item: the control at its step whose text or name is the word. A place item: the
    control clicked at its step whose text it names."""
    states = recording["states"]
    seen = _unique([a["before"] for a in step_actions] + [a["after"] for a in step_actions])
    if row["kind"] == "icon":
        best, score = None, 0
        for n in seen:
            for i, c in enumerate(states[n]["controls"]):
                if c.get("text") or not c.get("label"):
                    continue
                k = len(words(c["label"]) & words(row["text"] + " " + row.get("meaning", "")))
                clicked = any(_same_control(c, a.get("control") or {}) for a in step_actions)
                if (k, clicked) > (score, False) and (k or clicked):
                    best, score = (states[n], i), k
        return best
    if row["kind"] == "word":
        for n in seen:
            for i, c in enumerate(states[n]["controls"]):
                if locate.norm(c.get("text")) == locate.norm(row["text"]) or locate.norm(c.get("label")) == locate.norm(row["text"]):
                    return states[n], i
        return None
    if row["kind"] == "location":
        named = [a for a in step_actions if a["action"] == "click" and (a.get("control") or {}).get("text")
                 and locate.norm(a["control"]["text"]) in locate.norm(row["text"])]
        if named:
            a = max(named, key=lambda x: len(x["control"]["text"]))
            st = states[a["before"]]
            i = next((i for i, c in enumerate(st["controls"]) if _same_control(c, a["control"])), None)
            return (st, i) if i is not None else None
    return None


def help_phrase(row: dict[str, Any], step_actions: list[dict[str, Any]], recording: dict[str, Any]) -> str:
    """For an item the help explains: the sentence of help text opened at its step that shares
    the most words with it (at least two), copied as it is on screen."""
    best, score = "", 1
    for a in step_actions:
        c = a.get("control") or {}
        if a["action"] != "click" or c.get("text"):
            continue  # help opens from a picture-only button
        for line in appeared(recording, a):
            for sentence in re.split(r"(?<=[.!?])\s+", line):
                k = len(words(sentence) & words(row["text"] + " " + row.get("meaning", "")))
                if k > score:
                    best, score = sentence.strip(), k
    return best


def _unique(xs):
    out = []
    for x in xs:
        if x and x not in out:
            out.append(x)
    return out


def assemble(recording: dict[str, Any], basics: dict[str, Any], ai: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """The flow.json, and notes for the reviewer on what code had to fix or leave out."""
    notes: list[str] = []
    states = recording["states"]
    actions = [a for a in recording["actions"] if a["action"] not in INFO]
    by_n = {a["n"]: a for a in actions}

    # Screens: one per route visited, in order; the model only names them.
    routes = _unique([states[a["before"]]["route"] for a in actions] + [states[-1]["route"]] if actions else [states[0]["route"]])
    names = {s["route"]: s["name"] for s in ai.get("screens", []) if s.get("route") and s.get("name")}
    screens = [{"id": f"S{k}", "name": names.get(r) or (next((st["title"] for st in states if st["route"] == r), "") or r),
                "route": r} for k, r in enumerate(routes, 1)]
    screen_of_route = {s["route"]: s["id"] for s in screens}

    # Steps: the model's grouping when it covers every action once, in order, each on one screen.
    groups = [s for s in ai.get("steps", []) if s.get("actions")]
    flat = [n for s in groups for n in s["actions"]]
    ok = flat == [a["n"] for a in actions] and all(
        len({states[by_n[n]["before"]]["route"] for n in s["actions"]}) == 1 for s in groups)
    if not ok:
        notes.append("The draft's steps did not cover every action once and in order; there is one step per action instead.")
        groups = [{"actions": [a["n"]], "action": action_line(a, recording).split(": ", 1)[1].split(" (")[0].capitalize(),
                   "risky": False, "defaults": ""} for a in actions]
    steps = []
    step_of_action = {}
    step_index = {g.get("key"): k for k, g in enumerate(groups, 1) if ok and g.get("key")}
    for k, g in enumerate(groups, 1):
        route = states[by_n[g["actions"][0]]["before"]]["route"]
        steps.append({"id": f"A{k}", "screen": screen_of_route[route], "action": g["action"].strip(), "note": "",
                      "ways": [], "risky": bool(g.get("risky")), "defaults": (g.get("defaults") or "").strip(),
                      "recorded": list(g["actions"])})  # the recorded actions it groups, for the review page
        for n in g["actions"]:
            step_of_action[n] = f"A{k}"

    # Experiences and their groups.
    group_ids = {}
    flow_groups = []
    for g in ai.get("groups", []):
        gid = re.sub(r"[^a-z0-9]+", "-", (g.get("key") or "").lower()).strip("-") or f"group-{len(flow_groups) + 1}"
        if gid in group_ids.values():
            continue
        group_ids[g.get("key")] = gid
        flow_groups.append({"id": gid, "source": g["source"], "label": {"en": g["labelEn"], "zh": g["labelZh"]}})
    exps, exp_ids = [], {}
    for e in ai.get("experiences", []):
        gid = group_ids.get(e.get("group"))
        if not gid:
            notes.append(f"Experience {e.get('text')!r} named an unknown group; left out.")
            continue
        xid = f"X{len(exps) + 1:02d}"
        exp_ids[e.get("key")] = xid
        exps.append({"id": xid, "group": gid, "text": e["text"], "question": {"en": e["questionEn"], "zh": e["questionZh"]}})

    # Items, with the control each is on and its locator.
    items, item_ids = [], {}
    entry, help_items, review = [], [], []
    for it in ai.get("items", []):
        if it.get("kind") not in KINDS or not (it.get("text") or "").strip():
            continue
        s_idx = step_index.get(it.get("step"))
        if s_idx is None and it.get("onAction") in step_of_action:
            s_idx = int(step_of_action[it["onAction"]][1:])
        if s_idx is None:
            s_idx = 1
            notes.append(f"Item {it.get('text')!r} had no valid step; put on step 1.")
        iid = f"T{len(items) + 1:02d}"
        item_ids[it.get("key")] = iid
        row = {"id": iid, "step": steps[s_idx - 1]["id"], "way": None, "needed": bool(it.get("needed")), "kind": it["kind"],
               "text": it["text"].strip(), "meaning": (it.get("meaning") or "").strip(),
               "everyday": (it.get("everyday") or "").strip(), "common": it.get("common") or "none" if it["kind"] == "word" else "",
               "altOf": None, "exps": _unique([exp_ids[x] for x in it.get("exps") or [] if x in exp_ids]),
               "basis": (it.get("basis") or "Drafted from the recording").strip()}
        if row["kind"] != "word":
            row["common"] = ""
        control, state = None, None
        step_actions = [by_n[n] for n in groups[s_idx - 1]["actions"]]
        if it.get("onAction") in by_n:
            a = by_n[it["onAction"]]
            state = states[a["before"]]
            control = next((i for i, o in enumerate(state["controls"]) if _same_control(o, a.get("control") or {})), None)
        elif isinstance(it.get("onScreen"), int) and 0 <= it["onScreen"] < len(states) and isinstance(it.get("onControl"), int) \
                and it["onControl"] >= 0:
            state = states[it["onScreen"]]
            control = it["onControl"] if 0 <= it["onControl"] < len(state["controls"]) else None
        if control is None:
            found = tie(row, step_actions, recording)
            if found:
                state, control = found
        if control is not None:
            loc = locate.build(state["controls"], control)
            step_route = next(s["route"] for s in screens if s["id"] == steps[s_idx - 1]["screen"])
            if state["route"] != step_route:
                loc["route"] = state["route"]
            row["locate"] = loc
        phrase = (it.get("explainedBy") or "").strip()
        if not phrase and row["kind"] in ("word", "concept"):
            phrase = help_phrase(row, step_actions, recording)
        if phrase:
            if any(locate.norm(phrase) in locate.norm(st.get("text")) for st in states):
                row["explainedBy"] = {"text": phrase}
            else:
                notes.append(f"{iid}: the help text phrase {phrase!r} is on no recorded screen; open the help while recording to use it.")
        if it.get("entry"):
            entry.append(iid)
        if it.get("help") and "locate" in row and "label" in row["locate"] and "text" not in row["locate"]:
            row["kind"] = "icon"  # a help button with no text is a picture, whatever the draft called it
            row["common"] = ""
        if it.get("help") and row["kind"] == "icon":
            help_items.append(iid)
        if it.get("review") and "locate" in row:
            review.append(iid)
        items.append(row)
    if not any(i["kind"] == "word" for i in items):
        notes.append("The draft has no word items: the engine will swap only words outside the vocabulary.")

    # Persona Studio's knowledge groups: every item that is not a habit in exactly one group.
    kgroups, owner = [], {}
    for g in ai.get("knowledgeGroups", []):
        ids = [item_ids[x] for x in g.get("items") or [] if x in item_ids]
        kinds = {i["id"]: i["kind"] for i in items}
        ids = [i for i in ids if i not in owner and kinds[i] != "habit" and (kinds[i] == "word") == bool(g.get("word"))]
        if not ids:
            continue
        key = re.sub(r"[^a-z0-9]+", "-", (g.get("key") or g.get("title") or "group").lower()).strip("-")
        while any(x["key"] == key for x in kgroups):
            key += "-2"
        for i in ids:
            owner[i] = key
        kgroups.append({"key": key, "title": g["title"], "word": bool(g.get("word")), "default": min(2, max(0, int(g.get("default", 1)))),
                        "description": g.get("description") or g["title"], "examples": g.get("examples") or "", "items": ids})
    left = [i for i in items if i["kind"] != "habit" and i["id"] not in owner]
    for word, title in ((True, "Other terms"), (False, "Other knowledge")):
        ids = [i["id"] for i in left if (i["kind"] == "word") == word]
        if ids:
            kgroups.append({"key": "other-terms" if word else "other-knowledge", "title": title, "word": word, "default": 1,
                            "description": f"{title} on this workflow's screens", "examples": "", "items": ids})
            notes.append(f"{len(ids)} items were in no knowledge group; they are in {title!r}.")

    # The scripted success path, straight from the recording.
    plumbing = []
    for a in actions:
        c = a.get("control") or {}
        name = (c.get("text") or c.get("label") or "").strip()
        if a["action"] == "click" and name:
            plumbing.append({"action": "click", "label": name, "evidence": [{"type": "word", "ref": name}]})
        elif a["action"] == "type" and name and not a.get("secret"):
            plumbing.append({"action": "type", "label": name, "value": a.get("value", ""),
                             "evidence": [{"type": "word", "ref": name}]})
        elif a["action"] == "press":
            plumbing.append({"action": "press", "value": a.get("key", "Enter"),
                             "evidence": [{"type": "word", "ref": name}] if name else []})
        elif a["action"] == "select" and name:
            plumbing.append({"action": "choose", "label": name, "value": a.get("value", ""),
                             "evidence": [{"type": "word", "ref": name}]})
        elif a["action"] == "drag" and name and ((a.get("target") or {}).get("text") or (a.get("target") or {}).get("label")):
            t = a["target"]
            plumbing.append({"action": "drag", "label": name, "target": (t.get("text") or t.get("label")).strip(),
                             "evidence": [{"type": "word", "ref": name}]})
        elif a["action"] == "upload":
            pass  # the click that opened the file picker is the step; the engine picks the task's file
        elif a.get("secret"):
            notes.append(f"Action a{a['n']} typed a password during the task; sign-in belongs in the target's login.")
        else:
            notes.append(f"Action a{a['n']} was on a control with no text or label; the scripted path skips it.")
    outcome = ai.get("outcome") or {"kind": "change"}
    if outcome.get("kind") == "answer" and not ((outcome.get("question") or "").strip() and outcome.get("expected")):
        notes.append("The task looks like finding an answer, but the draft named no question or answer; add them in Success.")
    list_route = ai.get("listRoute") if ai.get("listRoute") in routes else None
    signals = {k: bool((ai.get("signals") or {}).get(k)) for k in ("toast", "list", "external", "test")}
    if signals["list"] and not list_route:
        signals["list"] = False
        notes.append("The draft said the product lists what was made, but named no recorded route for it; list is off.")
    if outcome.get("kind") == "answer" and outcome.get("expected"):
        plumbing.append({"observe": outcome["expected"][0]})
    elif outcome.get("kind") == "place" and (outcome.get("heading") or "").strip():
        plumbing.append({"observe": outcome["heading"].strip()})
    elif signals["list"] and (ai.get("listQuote") or "").strip():
        plumbing.append({"observe": ai["listQuote"].strip()})

    clicked = [(by_n[n].get("control") or {}).get("text") for n in by_n if by_n[n]["action"] == "click"]
    consequential = _unique([x.strip() for x in ai.get("consequential", []) if x and x.strip() in clicked or x])
    typed = [a.get("value") for a in actions if a["action"] == "type" and a.get("value") and not a.get("secret")]
    data_terms = _unique([*(ai.get("dataTerms") or []), *[t for t in typed if not re.fullmatch(r"[\d.,%$ ]+", t)]])

    target: dict[str, Any] = {"kind": "web", "start": recording["start"], "success": []}
    if recording.get("login"):
        target["login"] = recording["login"]
    if recording.get("reset"):
        target["reset"] = recording["reset"]
    gets = {r["path"] for r in recording.get("network") or [] if r["method"] == "GET" and r["status"] < 400}

    def value(v: str):
        try:
            return json.loads(v) if v.strip()[:1] in "[{" else v
        except ValueError:
            return v

    for c in ai.get("success", []):
        check = {"name": c["name"], "type": c["type"]}
        if c["type"] == "json" and c.get("url") in gets and (c.get("where") or c.get("expect")):
            check.update(url=c["url"], where={w["field"]: value(w["value"]) for w in c.get("where") or []},
                         expect={w["field"]: value(w["value"]) for w in c.get("expect") or []})
            if c.get("list"):
                check["list"] = c["list"]
        elif c["type"] == "json":
            notes.append(f"Check {c['name']!r} reads {c.get('url')!r}, which the product never fetched while recording; left out.")
            continue
        elif c["type"] == "text" and (c.get("contains") or "").strip():
            check.update(url=c.get("url") or list_route or routes[-1], contains=c["contains"].strip())
        elif c["type"] == "url" and c.get("matches"):
            check["matches"] = c["matches"]
        else:
            continue
        target["success"].append(check)
    if outcome.get("kind") == "answer" and outcome.get("expected"):
        target["success"].insert(0, {"name": f"Reports the right answer to: {outcome.get('question', '').strip()}",
                                     "type": "answer", "expected": [str(e) for e in outcome["expected"]]})
    for a in recording["actions"]:
        if a["action"] == "download" and a.get("value"):
            ext = Path(a["value"]).suffix
            target["success"].append({"name": f"Downloads the {ext.lstrip('.').upper() or 'file'}", "type": "download",
                                      "matches": re.escape(ext) + "$" if ext else "."})
    if outcome.get("kind") in ("answer", "place"):
        # Nothing is saved: a check of saved data would hold whatever the person did.
        target["success"] = [c for c in target["success"] if c["type"] in ("answer", "url", "download")]
        if outcome["kind"] == "place" and not any(c["type"] == "url" for c in target["success"]):
            end = states[-1]["route"].split("?")[0]
            target["success"].append({"name": f"Reaches {screens[-1]['name']}", "type": "url", "matches": re.escape(end) + "$"})
    if not target["success"]:
        notes.append("No success check could be drafted; add at least one before the workflow can be run.")
    files = _unique([f for a in actions if a["action"] == "upload" for f in a.get("files") or []])
    if files:
        notes.append("The task uploads " + ", ".join(files) + ": put the same files in this workflow's files folder, "
                     "or the engine uses a small sample file of the same kind.")
    caps = recording.get("capabilities") or {}
    if caps.get("captcha"):
        notes.append("The product shows a CAPTCHA: the engine cannot pass it. Turn it off in the test environment.")
    if caps.get("canvas"):
        notes.append("Part of the product is drawn on a canvas: the engine reads and masks its text from the screenshot "
                     "(OCR), which is less exact than on an ordinary page.")
    for k, line in (("setup", "Set-up steps"), ("cleanup", "Clean-up steps")):
        steps_rec = recording.get(k)
        if steps_rec:
            target[k] = replay_steps(steps_rec)
            notes.append(f"{line}: {len(target[k])} recorded steps the engine replays " + ("before" if k == "setup" else "after") + " each run.")

    flow = {
        "format": "sue-flow", "version": 1, "name": basics["name"],
        "updatedAt": datetime.now().strftime("%Y-%m-%d"),
        "task": basics["task"],
        "start": f"The test starts on {screens[0]['name']} ({recording['start']})" + (", signed in as the test account." if recording.get("login") else "."),
        "note": "Drafted from a recording by sue/draft.py and confirmed in the platform.",
        "screenSize": f"{recording['viewport']['width']}x{recording['viewport']['height'] + 56} window; the task bar takes 56 px.",
        "situation": ai.get("situation") or {"urgency": "calm", "stakes": "low"},
        "org": (ai.get("org") or "").strip(),
        "signals": signals,
        "checks": [c.strip() for c in ai.get("checks", []) if c.strip()],
        "keySettings": [],
        "screens": screens,
        "steps": steps,
        "sources": SOURCES,
        "groups": flow_groups,
        "experiences": exps,
        "items": items,
        "knowledgeGroupsNote": "Drafted from the recording; every item that is not a habit is in exactly one group.",
        "knowledgeGroups": kgroups,
        "engine": {
            "note": "Drafted from a recording; the target, the success checks and the locators are reviewed in the platform.",
            "created": (ai.get("created") or "item").strip().lower(),
            "routes": {"list": [list_route] if list_route else [], "path": routes},
            "labels": {"consequential": consequential, "advancing": _unique([x.strip() for x in ai.get("advancing", []) if x.strip()])},
            "items": {"entry": entry, "help": help_items, "review": review},
            "words": {"dataTerms": data_terms, "forceFake": _unique(ai.get("forceFake") or [])},
            "compare": {"fieldLabels": []},
            "plumbing": plumbing,
            "target": target,
            "outcome": {k: v for k, v in outcome.items() if k in ("kind", "question") and v},
            **({"files": [f"files/{f}" for f in files]} if files else {}),
        },
    }
    return flow, notes


def replay_steps(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """A recording of what the engine does itself before or after each run (set-up, clean-up),
    as steps: each control by the simplest locator that finds it alone on its screen."""
    states = rec["states"]
    out = [{"action": "goto", "url": states[0]["route"]}] if states else []
    for a in rec.get("actions") or []:
        if a["action"] in INFO:
            continue
        if a["action"] == "press":
            out.append({"action": "press", "value": a.get("key", "Enter")})
            continue
        st = states[a["before"]]
        i = next((k for k, c in enumerate(st["controls"]) if _same_control(c, a.get("control") or {})), None)
        if i is None:
            continue
        loc = locate.build(st["controls"], i)
        if a["action"] == "click":
            out.append({"action": "click", "locate": loc})
        elif a["action"] == "type" and not a.get("secret"):
            out.append({"action": "type", "locate": loc, "value": a.get("value", "")})
        elif a["action"] == "select":
            out.append({"action": "choose", "locate": loc, "value": a.get("value", "")})
    return out


def draft(recording: dict[str, Any], basics: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], list[str], dict[str, Any]]:
    """The draft flow, the notes for the reviewer, and the model's own answer (kept for the record)."""
    if not recording.get("actions"):
        raise ValueError("The recording has no actions; record the task first.")
    ai = ask(prompt(recording, basics), config)
    flow, notes = assemble(recording, basics, ai)
    folder = Path(recording.get("__dir") or ".")
    for k in ("setup", "cleanup"):
        rec = folder / f"{k}.json"
        if rec.exists():
            flow["engine"]["target"][k] = replay_steps(json.loads(rec.read_text(encoding="utf-8")))
    notes += [f"Engine: {p}" for p in engine_problems(flow)]
    return flow, notes, ai


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recording", required=True)
    parser.add_argument("--basics", required=True, help="JSON with name, task, product, users")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    load_env()
    config = load_config()
    recording = json.loads(Path(args.recording).read_text(encoding="utf-8"))
    recording["__dir"] = str(Path(args.recording).parent)
    basics = json.loads(Path(args.basics).read_text(encoding="utf-8"))
    flow, notes, ai = draft(recording, basics, config)
    out = Path(args.out)
    out.write_text(json.dumps(flow, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_name("draft-notes.json").write_text(json.dumps({"notes": notes, "model": ai}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Draft: {len(flow['steps'])} steps, {len(flow['items'])} items, {len(flow['knowledgeGroups'])} knowledge groups -> {out}")
    for n in notes:
        print("  note: " + n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
