"""The checks a workflow passes before it is used for testing (engine-design.md 6.3).

1. The flow file can drive the engine (sue/workflow.py; refused otherwise).
2. The full card, following the scripted success path with no model, is graded a pass: the
   path, the sign-in, the task bar and the success checks all work on the product.
3. The blank card on the same path does not pass: it is stopped where it cannot read the
   screen. If it gets through, the knowledge items block nothing and the test measures nothing.
4. Every locator found its control where the path goes, once, word for word.
5. With --with-model, the full card with the model, once: the product can be used from its
   screenshots. Optional, because it calls the model.

    python -m sue.check --flow ../data/workflows/teamspace-invite/flow.json [--with-model]

The result goes to check.json next to the flow; the platform shows it and marks the workflow
ready only when every required check passed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import load_config, load_env, require_env
from .model import LabelScriptModel, gemini_for
from .run import run
from .target import make_target
from .workflow import WorkflowError


def entry(name: str, ok: bool, detail: str, required: bool = True, run_dir: str | None = None) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail, "required": required, "run": run_dir}


def marks_check(summary: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    marks = summary.get("marks") or {}
    expected = {loc["item"] + (":explains" if loc["kind"] == "explains" else "") for loc in config["workflow"]["locators"]}
    seen = set((marks.get("by_item") or {}).keys())
    never = sorted(expected - seen)
    bad = {"not found where the path goes": marks.get("not_found") or [],
           "found more than once": marks.get("several") or [],
           "found only by a looser match": marks.get("loose") or [],
           "never looked for (its page is not on the path)": never}
    problems = "; ".join(f"{k}: {', '.join(v)}" for k, v in bad.items() if v)
    ok = not (marks.get("not_found") or never)
    return entry("Every locator finds its control", ok, problems or f"all {len(expected)} found, once, word for word",
                 run_dir=summary.get("dir")) | {"marks": bad}


def isolation_check(config: dict[str, Any]) -> dict[str, Any]:
    """Runs must not see each other's data: graded on what the product saved, a run would pass on
    what an earlier run saved. A reset address, a clean-up, or a value of each run's own ({run}) in
    what the checks look for keeps them apart. Our UAT platform keeps sessions apart itself."""
    target = config["workflow"].get("target") or {}
    if target.get("kind") != "web":
        return entry("Runs cannot see each other's data", True, "each session on our platform is its own")
    saved = [c for c in target.get("success") or [] if c.get("type") in ("json", "text")]
    if not saved:
        return entry("Runs cannot see each other's data", True, "nothing is graded on saved data")
    how = ("a reset before each run" if target.get("reset") else "a clean-up after each run" if target.get("cleanup")
           else "values of each run's own" if "{run}" in json.dumps(saved) else None)
    return entry("Runs cannot see each other's data", bool(how),
                 f"kept apart by {how}" if how else "graded on saved data with no reset, no clean-up and no value of the run's own: "
                 "a run could pass on what an earlier run saved. Make the identifying value different in every run, or record a clean-up")


def check(flow: Path, with_model: bool = False, headed: bool = False) -> dict[str, Any]:
    out: dict[str, Any] = {"flow": str(flow), "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "checks": [],
                           # the version checked: an edited flow needs checking again
                           "flowHash": hashlib.sha1(Path(flow).read_bytes()).hexdigest()}
    try:
        config = load_config(flow=flow)
    except WorkflowError as error:
        out["checks"].append(entry("The flow file can drive the engine", False, str(error)))
        out["passed"] = False
        return out
    out["workflow"] = config["workflow"]["name"]
    out["checks"].append(entry("The flow file can drive the engine", True, "no problems"))
    path = config["workflow"]["plumbing"]
    if not path:
        out["checks"].append(entry("The full card passes the scripted path", False, "the flow has no engine.plumbing path"))
        out["passed"] = False
        return out
    target = make_target(config)
    steps = len(path) + 8
    out["checks"].append(isolation_check(config))

    # The blank card first: a run after the full card's could find what the full card saved.
    blank = run("blank", config, target, LabelScriptModel(path), headed=headed, max_steps=steps)
    passed = bool((blank.get("evaluation") or {}).get("overall"))
    blank_entry = entry(
        "The blank card does not get through", not passed,
        f"did not get through ({blank['stop']['why'].rstrip('.')}, after {blank['actions']} actions)"
        if not passed else "the blank card passed: no knowledge item blocks anything, so the test would measure nothing",
        run_dir=blank["dir"])

    full = run("full", config, target, LabelScriptModel(path), headed=headed, max_steps=steps)
    ev = full.get("evaluation") or {}
    failed = [k for k, v in (ev.get("criteria") or {}).items() if not v]
    out["checks"].append(entry(
        "The full card passes the scripted path", bool(ev.get("overall")),
        "graded a pass" if ev.get("overall") else
        f"stopped: {full['stop']['why']}" + (f"; failed: {', '.join(failed)}" if failed else ""), run_dir=full["dir"]))
    out["checks"].append(marks_check(full, config))
    out["checks"].append(blank_entry)

    if with_model:
        model = gemini_for(config, require_env("GEMINI_API_KEY"))
        live = run("full", config, target, model, headed=headed)
        ok = bool((live.get("evaluation") or {}).get("overall"))
        out["checks"].append(entry("The full card passes with the model", ok,
                                   "graded a pass" if ok else f"stopped: {live['stop']['why']}", required=False,
                                   run_dir=live["dir"]))
    out["passed"] = all(c["ok"] for c in out["checks"] if c["required"])
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--flow", required=True)
    parser.add_argument("--with-model", action="store_true", help="also one run of the full card with the model")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args(argv)
    load_env()
    flow = Path(args.flow).resolve()
    result = check(flow, args.with_model, args.headed)
    (flow.parent / "check.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== Workflow checks: " + ("ready" if result["passed"] else "not ready"))
    for c in result["checks"]:
        print(f"  [{'pass' if c['ok'] else 'FAIL' if c['required'] else 'warn'}] {c['name']}: {c['detail']}")
    print(f"Saved to {flow.parent / 'check.json'}")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
