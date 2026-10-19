"""Checks a whole run against the real platform without a model: a scripted
"model" proposes the workflow's correct path (flow.json engine.plumbing) one screen at a time, and everything
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--card", default="full")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--watch", action="store_true", help="show the engine's browser and a live log side by side")
    parser.add_argument("--flow", help="the workflow's flow.json (default paths.flow in config.toml)")
    args = parser.parse_args(argv)
    config = load_config(flow=args.flow)
    path = config["workflow"]["plumbing"]
    if not path:
        print(f"{config['workflow']['file']} has no engine.plumbing path to follow", file=sys.stderr)
        return 1
    load_env()
    console = ResearchConsole(platform_url(config), require_env("ADMIN_PASSWORD"))
    run(args.card, config, console, LabelScriptModel(path), headed=args.headed, watch=args.watch,
        max_steps=len(path) + 8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
