"""Doing the task once from steps the researcher wrote, instead of doing it by hand (engine-design.md 6.3).

The researcher writes the right way to do the task, one step per line, as they would for a
person. For each line the model sees the page (a screenshot and the numbered list of its
controls) and names which controls to use and what to type or choose; code performs each with a
real click or real typing, so sue.record writes the recording exactly as when a person does it.
After that the recording goes through the same draft, review and checks as any other.

The model only picks controls from the list; it cannot invent one. A line it cannot carry out
stops the recording with that line named, so the researcher can say it more plainly.
"""

from __future__ import annotations

import json
from typing import Any

from .config import require_env

SYSTEM = """You carry out one written step of a task on a web page, the way a person who knows the product would.
You get the whole task, the step to carry out now, a screenshot of the page and the numbered list of the controls on it.
Return JSON {"actions": [...], "stuck": "" }. Each action is {"control": <number from the list>, "do": "click" | "type" | "choose" | "press", "value": "..."}.
- click: press the control (a button, a link, a checkbox, a tab, a menu item).
- type: replace what is in a text box with value.
- choose: pick the option named value in a dropdown (a native select).
- press: press a key (value such as "Enter"); control is the box it is pressed in.
Give the actions for this step only, in order; usually one, sometimes a few (fill two boxes, then click Save).
When the step needs something that appears only after an earlier action of the same step (a menu that opens),
give only the actions up to that point; you will be asked again with the new page.
When the step is already done on this page, return no actions. When no control on the list can do it, return
no actions and say in "stuck" what is missing. Never invent a control number."""

SCHEMA = {"type": "object", "properties": {
    "actions": {"type": "array", "items": {"type": "object", "properties": {
        "control": {"type": "integer"}, "do": {"type": "string", "enum": ["click", "type", "choose", "press"]},
        "value": {"type": "string"}}, "required": ["control", "do"]}},
    "stuck": {"type": "string"}}, "required": ["actions"]}


def controls_text(controls: list[dict[str, Any]]) -> str:
    lines = []
    for i, c in enumerate(controls):
        name = c.get("text") or c.get("label") or ""
        bits = [f"[{i}]", c.get("role") or c.get("tag") or "", f"“{name[:80]}”" if name else "(no name)"]
        if c.get("label") and c.get("label") != name:
            bits.append(f"label “{c['label'][:60]}”")
        if c.get("value"):
            bits.append(f"value “{str(c['value'])[:40]}”")
        if c.get("checked") is not None:
            bits.append("checked" if c["checked"] else "not checked")
        if c.get("group"):
            bits.append(f"in “{c['group'][:40]}”")
        lines.append(" ".join(b for b in bits if b))
    return "\n".join(lines)


def ask(config: dict[str, Any], task: str, step: str, done: list[str], shot: bytes, controls: list[dict[str, Any]]) -> dict[str, Any]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=require_env("GEMINI_API_KEY"))
    text = (f"The whole task:\n{task}\n\nSteps already carried out:\n" + ("\n".join(f"- {d}" for d in done) or "- none")
            + f"\n\nThe step to carry out now:\n{step}\n\nControls on the page:\n{controls_text(controls)}")
    response = client.models.generate_content(
        model=config["model"]["id"], contents=[types.Part.from_bytes(data=shot, mime_type="image/png"), types.Part.from_text(text=text)],
        config=types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json",
                                           response_json_schema=SCHEMA, temperature=0.0,
                                           http_options=types.HttpOptions(timeout=120_000)))
    return json.loads(response.text)


class WrittenStepError(RuntimeError):
    pass


def perform(page_of, steps: list[str], task: str, recorder, config: dict[str, Any], rounds: int = 4) -> None:
    """Carries out each written step on the page; page_of() gives the page the recording follows."""
    done: list[str] = []
    for n, step in enumerate(steps, 1):
        for _ in range(rounds):
            page = page_of()
            controls = page.evaluate("() => window.__sue.inventory()")
            shot = page.screenshot()
            answer = ask(config, task, step, done, shot, controls)
            actions = answer.get("actions") or []
            if not actions:
                if answer.get("stuck"):
                    raise WrittenStepError(f"Step {n} (“{step}”) could not be carried out: {answer['stuck']}")
                break
            for a in actions:
                i = a.get("control")
                if not isinstance(i, int) or not 0 <= i < len(controls):
                    raise WrittenStepError(f"Step {n} (“{step}”): the model named a control that is not on the page.")
                if not page.evaluate("i => window.__sue.targetAt(i)", i):
                    raise WrittenStepError(f"Step {n} (“{step}”): control {i} is gone from the page.")
                el = page.locator("[data-sue-target]").first
                kind, value = a.get("do"), a.get("value") or ""
                if kind == "click":
                    el.click()
                elif kind == "type":
                    el.click()
                    el.fill(value)
                    el.press("Tab")
                elif kind == "choose":
                    el.select_option(label=value)
                elif kind == "press":
                    el.press(value or "Enter")
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:  # noqa: BLE001 - a page that keeps polling
                    pass
                page.wait_for_timeout(400)
                recorder.drain(page_of())
            # One more look: the step may need a control that only now appeared (a menu).
            if len(actions) and all(x.get("do") != "click" for x in actions):
                break
        done.append(step)
