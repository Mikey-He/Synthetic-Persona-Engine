"""Checks a whole run against the real platform without a model: a scripted
"model" proposes the correct Version A path one screen at a time, and everything
else (rewriting, evidence, choosing, acting, logging, the platform result) is real.

    python -m sue.plumbing --card full

It proves the plumbing, not the engine: the full card should reach a passing
evaluation; the blank card should be stopped where its evidence is void."""

from __future__ import annotations

import argparse
import sys

from .config import load_config, load_env, platform_url, require_env
from .model import LabelScriptModel
from .platform import ResearchConsole
from .run import run

W = lambda ref: {"type": "word", "ref": ref}  # noqa: E731
I = lambda ref: {"type": "item", "ref": ref}  # noqa: E731

CORRECT_PATH = [
    {"action": "click", "label": "Budgets & caps", "evidence": [W("Budgets & caps")]},
    {"action": "click", "label": "Create new", "evidence": [I("T10")]},
    {"action": "click", "label": "Alerts only", "evidence": [W("Alerts only")]},
    {"action": "type", "label": "Name", "value": "Atlas monthly", "evidence": [W("Name")]},
    {"action": "click", "label": "Next", "evidence": [I("T15")]},
    {"action": "click", "label": "Projects", "evidence": [W("Projects")]},
    {"action": "click", "label": "Atlas", "evidence": [W("Atlas")]},
    {"action": "click", "label": "OK", "evidence": [I("T31")]},
    {"action": "click", "label": "Next", "evidence": [I("T15")]},
    {"action": "type", "label": "Target amount", "value": "1000", "evidence": [W("Target amount")]},
    {"action": "click", "label": "Next", "evidence": [I("T15")]},
    {"action": "type", "label": "Percent of budget 1", "value": "80", "evidence": [W("Percent")]},
    {"action": "click", "label": "billing admins and users", "evidence": [W("billing admins and users")]},
    {"action": "click", "label": "project owners", "evidence": [W("project owners")]},
    {"action": "click", "label": "Finish", "evidence": [I("T24")]},
    # Back on the list: the code asks whether the new budget is there; code then declares completion.
    {"observe": "Atlas monthly"},
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", default="full")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--watch", action="store_true", help="show the engine's browser and a live log side by side")
    args = parser.parse_args(argv)
    config = load_config()
    load_env()
    console = ResearchConsole(platform_url(config), require_env("ADMIN_PASSWORD"))
    run(args.card, config, console, LabelScriptModel(CORRECT_PATH), headed=args.headed, watch=args.watch,
        max_steps=len(CORRECT_PATH) + 8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
