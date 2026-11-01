"""How this person reads the task (engine-design.md 4.11, 2026-11-01).

The words a person cannot read are swapped for made-up words before the model sees the screen. The
same is done here for the task: what a reader could take in more than one way is listed once per
workflow (the task's own property, kept beside the flow as readings.json, where a researcher can read
and edit it), and each run draws one reading per ambiguity. The model is told what the person takes
the task to mean, not what it says, so it fills in $1,000 as confidently as a person who read it that
way. When a screen shows the words that bear on an ambiguity, the person may think again, more often
the more carefully they check; the new reading is drawn like the first. Which readings exist is the
model's one-time reading of the text; which one a run gets is code's seeded draw, so the group's share
of each reading, and so of each mistake, comes from the task and not from one person.

Why: the six Billing Config people all read every word, and still half of them changed the amount
(800, 1000, 600) or the trigger. Swapping words cannot produce that; it produces not daring to click."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

READINGS_FILE = "readings.json"

SYSTEM = """You read a task given to a person who will carry it out in a web product. List the places where a careful reader could take the task in more than one way, each with the readings a reader might settle on. Only readings the text itself allows; not mistakes of carelessness. For each, give the words that appear on the screens where that choice is made, so that seeing them might make the reader think again. At most five such places; none if the task is unambiguous. Output JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "about": {"type": "string"},
                    "shows_as": {"type": "array", "items": {"type": "string"}},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["about", "shows_as", "options"],
            },
        }
    },
    "required": ["ambiguities"],
}


def ask_readings(task: str, client: Any, model_id: str) -> list[dict[str, Any]]:
    """The model's one reading of the task text: where it forks, and into what."""
    from google.genai import types

    config = types.GenerateContentConfig(system_instruction=SYSTEM, response_mime_type="application/json", response_json_schema=SCHEMA, temperature=0.0)
    reply = client.models.generate_content(model=model_id, contents=[types.Part.from_text(text="The task:\n\n" + task)], config=config)
    out = []
    for a in json.loads(reply.text).get("ambiguities") or []:
        options = [str(o).strip() for o in a.get("options") or [] if str(o).strip()]
        if len(options) >= 2:
            out.append({"about": str(a.get("about") or "").strip(), "shows_as": [str(w).strip() for w in a.get("shows_as") or [] if str(w).strip()], "options": options[:4]})
    return out[:5]


def load_readings(flow_file: str | Path, task: str, client: Any, model_id: str) -> "Readings":
    """The workflow's readings file, made by the model the first time and kept for every run after."""
    path = Path(flow_file).resolve().parent / READINGS_FILE
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("task") == task:
            return Readings(data["ambiguities"])
    ambiguities = ask_readings(task, client, model_id)
    path.write_text(json.dumps({"task": task, "model": model_id, "ambiguities": ambiguities}, ensure_ascii=False, indent=2), encoding="utf-8")
    return Readings(ambiguities)


@dataclass
class Readings:
    ambiguities: list[dict[str, Any]]
    thought: set[tuple[int, str]] = field(default_factory=set)  # (ambiguity, form part) already thought about again

    def draw(self, rng) -> dict[int, int]:
        """One reading per ambiguity, each equally likely: the text allows them all."""
        return {i: rng.randrange(len(a["options"])) for i, a in enumerate(self.ambiguities)}

    def line(self, chosen: dict[int, int]) -> str | None:
        """What they take the task to mean, for the prompt."""
        parts = [self.ambiguities[i]["options"][k] for i, k in sorted(chosen.items()) if i < len(self.ambiguities)]
        return " ".join(parts) or None

    def rethink(self, rng, visible_text: str, part: str, care: float, chosen: dict[int, int]) -> dict[str, Any] | None:
        """On a part of the form that shows the words an ambiguity turns on, they may think again, with
        chance care (detail when checking, 0 to 1), once per ambiguity and part. The new reading is drawn
        like the first, so it may be the same one; returns what changed, or None."""
        text = (visible_text or "").lower()
        for i, a in enumerate(self.ambiguities):
            if (i, part) in self.thought or not any(w.lower() in text for w in a["shows_as"]):
                continue
            self.thought.add((i, part))
            if rng.random() >= care:
                continue
            was, now = chosen[i], rng.randrange(len(a["options"]))
            if now != was:
                chosen[i] = now
                return {"about": a["about"], "part": part, "was": a["options"][was], "now": a["options"][now]}
        return None
