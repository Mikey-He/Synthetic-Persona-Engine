"""The workflow the engine runs on (engine-design.md 6, 2026-10-19).

Everything that belongs to one workflow lives in its flow.json, under "engine": which pages
are on the route and which one lists what was made, which buttons commit or move on, which
items say where the entry is, which help icon he may know, which link opens what he saved,
the data words he always reads, the field names for comparing, what the made thing is
called, and the scripted success path for sue.plumbing. config.toml holds only what is the
same for every workflow. A new workflow needs its flow.json, not a code change:

    python -m sue.run --flow ../data/<workflow>/flow.json --card <card>

The settings are put where the rest of the engine has always read them (config["goal"],
config["words"], config["run"], config["compare"]), plus config["workflow"].
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .target import target_problems

LOCATE_KEYS = {"text", "label", "selector", "role", "region", "group", "match", "nth", "route"}
MATCHES = ("exact", "contains", "starts")


class WorkflowError(ValueError):
    """The flow file cannot drive the engine."""


def problems(flow: dict[str, Any]) -> list[str]:
    """What is missing or wrong in a flow's engine block; empty when it can drive the engine."""
    e = flow.get("engine")
    if not isinstance(e, dict):
        return ['engine: missing; the engine needs the workflow\'s routes, labels and items (engine-design.md 6)']
    out = []
    if not isinstance(e.get("created"), str) or not e["created"].strip():
        out.append("engine.created: name what the task makes, as it shows in the list (e.g. budget)")
    if e.get("createdArticle") not in (None, "a", "an"):
        out.append("engine.createdArticle: a or an")
    routes = e.get("routes") or {}
    for key in ("list", "path"):
        if not isinstance(routes.get(key), list) or not all(isinstance(r, str) and r.startswith("/") for r in routes.get(key) or []):
            out.append(f"engine.routes.{key}: a list of routes starting with /")
    if not (routes.get("path") or []):
        out.append("engine.routes.path: at least one route on the success path")
    if not set(routes.get("list") or []) <= set(routes.get("path") or []):
        out.append("engine.routes.list: every list route must also be on the path")
    labels = e.get("labels") or {}
    for key in ("consequential", "advancing"):
        if not isinstance(labels.get(key), list) or not all(isinstance(x, str) and x for x in labels.get(key) or []):
            out.append(f"engine.labels.{key}: a list of button labels")
    items = {i["id"] for i in flow.get("items", [])}
    for key, ids in (e.get("items") or {}).items():
        for i in ids or []:
            if i not in items:
                out.append(f"engine.items.{key}: unknown item {i}")
    words = e.get("words") or {}
    for key in ("dataTerms", "forceFake"):
        if not isinstance(words.get(key, []), list):
            out.append(f"engine.words.{key}: a list of words")
    if not isinstance((e.get("compare") or {}).get("fieldLabels", []), list):
        out.append("engine.compare.fieldLabels: a list of field names")
    for n, step in enumerate(e.get("plumbing") or [], 1):
        if not isinstance(step, dict) or not (step.get("observe") or (step.get("action") and step.get("label"))
                                              or (step.get("action") == "press" and step.get("value"))):
            out.append(f"engine.plumbing step {n}: needs an action and a label (a key for press), or observe")
    out += target_problems(e.get("target"))
    out += locator_problems(flow)
    from .prompt import EXTRA_ACTIONS
    actions = e.get("actions")
    if actions is not None and (not isinstance(actions, list) or set(actions) - set(EXTRA_ACTIONS)):
        out.append(f"engine.actions: a list of {', '.join(EXTRA_ACTIONS)}")
    outcome = e.get("outcome") or {"kind": "change"}
    if outcome.get("kind") not in OUTCOMES:
        out.append(f"engine.outcome.kind: one of {', '.join(OUTCOMES)}")
    elif outcome["kind"] == "answer" and not (isinstance(outcome.get("question"), str) and outcome["question"].strip()):
        out.append("engine.outcome.question: the question whose answer the person must find")
    if "maxSteps" in e and not (isinstance(e["maxSteps"], int) and 10 <= e["maxSteps"] <= 500):
        out.append("engine.maxSteps: a number of actions from 10 to 500")
    if not isinstance(e.get("files", []), list):
        out.append("engine.files: a list of sample files a person uploads, relative to the flow")
    return out


# What the task leaves behind (engine-design.md 6.3): something saved or changed in the product,
# an answer the person finds and reports, or a page they reach.
OUTCOMES = ("change", "answer", "place")


def _routes(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.startswith("/")) or (
        isinstance(value, list) and all(isinstance(r, str) and r.startswith("/") for r in value))


def locator_problems(flow: dict[str, Any]) -> list[str]:
    """Item locators (engine-design.md 6.3): how the engine finds an item's control, or the help
    text that explains it, on a page that carries no data-kl marks of its own."""
    out = []
    for s in flow.get("screens", []):
        if not _routes(s.get("route")):
            out.append(f"screen {s.get('id')}: route is a route starting with / (or a list of them)")
    for i in flow.get("items", []):
        for key in ("locate", "explainedBy"):
            loc = i.get(key)
            if loc is None:
                continue
            where = f"item {i.get('id')}.{key}"
            if not isinstance(loc, dict):
                out.append(f"{where}: an object")
                continue
            if set(loc) - LOCATE_KEYS:
                out.append(f"{where}: unknown keys {', '.join(sorted(set(loc) - LOCATE_KEYS))}")
            if key == "locate" and not any(isinstance(loc.get(k), str) and loc[k].strip() for k in ("text", "label", "selector")):
                out.append(f"{where}: needs text, label or selector")
            if key == "explainedBy" and not (isinstance(loc.get("text"), str) and loc["text"].strip()):
                out.append(f"{where}: needs text, a phrase from the help text")
            if loc.get("match", "exact") not in MATCHES:
                out.append(f"{where}: match is one of {', '.join(MATCHES)}")
            if "nth" in loc and not (isinstance(loc["nth"], int) and loc["nth"] >= 0):
                out.append(f"{where}: nth is a number from 0")
            if not _routes(loc.get("route")):
                out.append(f"{where}: route is a route starting with / (or a list of them)")
    return out


def locators(flow: dict[str, Any]) -> list[dict[str, Any]]:
    """Every item locator, with the routes it applies on: its own, else its step's screen's."""
    screen_of = {s["id"]: s.get("screen") for s in flow.get("steps", [])}
    route_of = {s["id"]: s.get("route") for s in flow.get("screens", [])}
    out = []
    for i in flow.get("items", []):
        for key, kind in (("locate", "control"), ("explainedBy", "explains")):
            loc = i.get(key)
            if not loc:
                continue
            routes = loc.get("route", route_of.get(screen_of.get(i.get("step"))))
            routes = [routes] if isinstance(routes, str) else list(routes or [])
            out.append({**{k: v for k, v in loc.items() if k != "route"}, "item": i["id"], "kind": kind, "routes": routes})
    return out


def apply(config: dict[str, Any], path: Path) -> dict[str, Any]:
    """Reads the flow at path and puts its engine settings into config."""
    try:
        flow = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise WorkflowError(f"cannot read the workflow {path}: {error}") from None
    bad = problems(flow)
    if bad:
        raise WorkflowError(f"{Path(path).name} cannot drive the engine:\n  " + "\n  ".join(bad))
    e = flow["engine"]
    items, labels, words = e.get("items") or {}, e["labels"], e.get("words") or {}
    config["goal"] = {
        "list_routes": e["routes"]["list"],
        "path_routes": e["routes"]["path"],
        "advancing_labels": labels["advancing"],
        "entry_items": items.get("entry", []),
        "help_items": items.get("help", []),
        "review_items": items.get("review", []),
    }
    config["run"]["consequential_labels"] = labels["consequential"]
    config["words"]["data_terms"] = words.get("dataTerms", [])
    config["words"]["force_fake"] = words.get("forceFake", [])
    config["compare"]["field_labels"] = (e.get("compare") or {}).get("fieldLabels", [])
    from .prompt import EXTRA_ACTIONS
    target = e.get("target") or {"kind": "uat"}
    if e.get("maxSteps"):
        config["run"]["max_steps"] = e["maxSteps"]
    folder = Path(path).resolve().parent
    config["workflow"] = {"name": flow["name"], "file": str(Path(path).resolve()), "created": e["created"].strip(),
                          # extra actions: the flow's own list, else all of them on a web product, none on Version A
                          "actions": e["actions"] if e.get("actions") is not None else (list(EXTRA_ACTIONS) if target.get("kind") == "web" else []),
                          "outcome": e.get("outcome") or {"kind": "change"},
                          "files": [str(folder / f) for f in e.get("files") or []],
                          "article": e.get("createdArticle"),
                          "plumbing": e.get("plumbing") or [],
                          "target": target,
                          "locators": locators(flow),
                          # checks the researcher does not count towards "done right" (still graded and shown)
                          "ignored_checks": list(e.get("gradingIgnored") or []),
                          "task": flow.get("task", "")}
    return config
