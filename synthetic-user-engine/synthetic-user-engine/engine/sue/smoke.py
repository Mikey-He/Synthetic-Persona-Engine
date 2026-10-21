"""Smoke check of the model-free half of the engine, against the local platform.

For each card it opens a fresh synthetic session, follows a scripted click path, and
at every screen saves the processed screenshot and the element list as that person
sees them. No model is called. Example:

    python -m sue.smoke --cards blank full mikey --path "Budgets & caps" "Create new"
"""

from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

from .config import load_config, load_env
from .memory import SessionMemory
from .persona import load_card
from .run import gray_icon_ids
from .runlog import RunLog
from .screen import Screen, Strip, open_browser
from .target import make_target
from .words import build_vocabulary


def find(elements, label: str):
    """The first element whose original text starts with label, ignoring a leading "+"
    (so "Budgets & caps" finds "Budgets & caps Preview")."""
    label = label.strip().lower()
    for e in elements:
        if e["original"].strip().lower().lstrip("+ ").startswith(label):
            return e
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cards", nargs="+", default=["blank", "full", "mikey"])
    parser.add_argument("--path", nargs="*", default=[], help="original labels to click, in order")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--flow", help="the workflow's flow.json (default paths.flow in config.toml)")
    args = parser.parse_args(argv)

    config = load_config(flow=args.flow)
    load_env()
    target = make_target(config)
    log = RunLog(config["paths"]["runs"], "smoke")

    with sync_playwright() as pw:
        for card in args.cards:
            persona = load_card(config["paths"]["personas"], card, config["workflow"]["file"])
            session = target.start(model_id="none", prompt_version="smoke", persona_id=persona.id)
            platform = config["platform"]
            strip = Strip(persona.task, platform["harness_button_text"], platform["viewport_width"]) if target.harness == "strip" else None
            browser, page = open_browser(pw, config, headless=not args.headed, strip=strip)
            screen = Screen(page, build_vocabulary(persona, config), config, strip=strip)
            memory = SessionMemory()
            target.prepare(page)
            page.goto(session.link)
            print(f"\n=== {card} ({persona.name}) session {session.id}")
            obs = None
            for step, label in enumerate([None, *args.path]):
                if label is not None:
                    target = find(obs.elements, label)
                    if target is None:
                        print(f'  cannot find "{label}" to click; stopping')
                        break
                    screen.perform("click", target, None)
                obs = screen.observe(step, gray_icon_ids(persona, memory))
                shot = f"{card}_step_{step:03d}.png"
                (log.dir / shot).write_bytes(obs.screenshot)
                log.write_json(f"{card}_step_{step:03d}_elements.json", obs.elements)
                print(f"  step {step} {obs.route}  rewrite rounds {obs.rewrite_rounds}  {shot}")
                for e in obs.elements:
                    if e["harness"] or not e["text"]:
                        continue
                    seen = e["text"] if e["text"] == e["original"] else f"{e['text']}  <- {e['original']}"
                    extra = "; ".join(e["understanding"])
                    print(f"    {e['id']:>6} {seen}" + (f"  [{extra}]" if extra else ""))
            browser.close()
            target.end(session.id, "abandoned")
    log.close()
    print(f"\nScreenshots and element lists are in {log.dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
