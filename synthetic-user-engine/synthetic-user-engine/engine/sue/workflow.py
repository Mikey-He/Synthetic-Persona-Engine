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
        if not isinstance(step, dict) or not (step.get("observe") or (step.get("action") and step.get("label"))):
            out.append(f"engine.plumbing step {n}: needs an action and a label, or observe")
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
    config["workflow"] = {"name": flow["name"], "file": str(Path(path).resolve()), "created": e["created"].strip(),
                          "article": e.get("createdArticle"),
                          "plumbing": e.get("plumbing") or []}
    return config
