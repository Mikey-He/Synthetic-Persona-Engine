"""Grading past web runs again after the definition of done changed, without running them again.

A run's own record (steps.jsonl) is performed again on the product, action by action, in a fresh
browser: the same clicks on the same controls (found by the text the run acted on), the same
values typed and chosen. What the product then saved is graded with the workflow's current
success checks. The run's summary keeps its first grading beside the new one, with how the new
one was made, so nothing is overwritten silently.

    python -m sue.regrade --flow ../data/workflows/<id>/flow.json runs/<run dir> [runs/<run dir> ...]

Only for products whose result does not depend on time or on other runs (the replay starts from a
fresh browser, as every run does). A replay that cannot find a control stops and says which.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .config import load_config, load_env
from .screen import PAGE_SCRIPT
from .target import WebTarget

SKIP = ("scroll", "none", None)
VIRTUAL = ("i'm finished", "i am finished")  # the engine's own task bar, not the product


TOPMOST = """name => {
  const norm = s => String(s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  const want = norm(name);
  document.querySelectorAll('[data-sue-target]').forEach(e => e.removeAttribute('data-sue-target'));
  const pool = [...document.querySelectorAll('button, a, input, select, textarea, label, summary, [role=button], [role=option], [role=checkbox], [role=menuitem], [role=tab], [tabindex]')];
  const named = el => {
    const field = ['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName);
    const lab = field && el.labels && el.labels[0] ? el.labels[0].innerText : '';
    return norm(field ? (lab || el.getAttribute('placeholder') || el.getAttribute('aria-label')) : el.innerText);
  };
  for (const el of pool) {
    if (named(el) !== want) continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    el.scrollIntoView({block: 'center'});
    const q = el.getBoundingClientRect();
    const hit = document.elementFromPoint(q.left + q.width / 2, q.top + q.height / 2);
    if (hit && (hit === el || el.contains(hit) || hit.contains(el))) { el.setAttribute('data-sue-target', ''); return true; }
  }
  return false;
}"""


class ReplayError(RuntimeError):
    pass


def act(page, action: dict[str, Any]) -> str:
    kind, text, value = action.get("type"), (action.get("original") or action.get("text") or "").strip(), action.get("value")
    if kind in SKIP:
        return "skipped"
    if kind == "back":
        page.go_back()
        return "went back"
    if text.lower() in VIRTUAL:
        return "task bar (not the product)"
    found = page.evaluate(TOPMOST, text)  # of controls with this name, the one on top (a dialog over the page)
    if not found:
        found = page.evaluate("l => window.__sue.target(l)", {"text": text})
    if not found:
        found = page.evaluate("l => window.__sue.target(l)", {"text": text, "match": "contains"})
    box = action.get("box")
    if not found and box and kind == "click":
        # A control with no text of its own (an icon such as ☰): the run clicked it at this place.
        page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
        page.wait_for_timeout(250)
        return f"click {text} at its recorded place"
    if not found:
        raise ReplayError(f"no control named “{text}” on the page")
    el = page.locator("[data-sue-target]").first
    if kind == "click":
        el.click()
    elif kind == "type":
        el.fill(str(value or ""))
    elif kind == "choose":
        el.select_option(label=str(value))
    elif kind == "press":
        el.press(str(value or "Enter"))
    else:
        raise ReplayError(f"cannot replay action {kind!r}")
    page.wait_for_timeout(250)
    return f"{kind} {text}" + (f" = {value}" if value not in (None, "") else "")


def replay(run_dir: Path, spec: dict[str, Any], viewport: dict[str, int]) -> tuple[dict[str, Any], list[str]]:
    rows = [json.loads(line) for line in (run_dir / "steps.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    target = WebTarget(spec)
    done: list[str] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport=viewport, device_scale_factor=1)
        context.add_init_script(path=str(PAGE_SCRIPT))
        page = context.new_page()
        page.set_default_timeout(8000)  # a replay that cannot act says so quickly
        target.prepare(page)
        page.goto(spec["start"])
        page.wait_for_load_state("networkidle")
        for row in rows:
            try:
                done.append(f"{row['step']}: {act(page, row.get('action') or {})}")
            except ReplayError as error:
                browser.close()
                raise ReplayError(f"step {row['step']}: {error}") from None
        criteria, details = {}, {}
        for check in spec["success"]:
            ok, why = target.check(check, page, {})
            criteria[check["name"]], details[check["name"]] = ok, why
        saved = {c["key"]: target._stored(page, c["key"]) for c in spec["success"] if c.get("type") == "storage"}
        browser.close()
    return {"overall": bool(criteria) and all(criteria.values()), "criteria": criteria, "details": details, "saved": saved}, done


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--flow", required=True)
    parser.add_argument("runs", nargs="+")
    args = parser.parse_args(argv)
    load_env()
    config = load_config(flow=args.flow)
    spec = config["workflow"]["target"]
    viewport = {"width": config["platform"]["viewport_width"], "height": config["platform"]["viewport_height"] - 56}
    for r in args.runs:
        d = Path(r)
        summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
        ev, done = replay(d, spec, viewport)
        summary.setdefault("evaluation_first", summary.get("evaluation"))
        summary["evaluation"] = {k: v for k, v in ev.items() if k != "saved"}
        summary["regrade"] = {"at": datetime.now().isoformat(timespec="seconds"), "method": "the run's actions performed again on the product",
                              "flow": str(Path(args.flow).resolve()), "saved": ev["saved"], "replayed": len(done)}
        (d / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{d.name}: {'pass' if ev['overall'] else 'fail'} {ev['criteria']}")
        print("   saved:", json.dumps(ev["saved"], ensure_ascii=False)[:400])
    return 0


if __name__ == "__main__":
    sys.exit(main())
