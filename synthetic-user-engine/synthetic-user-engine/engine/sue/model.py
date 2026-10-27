"""The model behind step 4. Only Google-approved Gemini models (CLAUDE.md rule 9)."""

from __future__ import annotations

import time
from typing import Protocol

import re

from .prompt import response_schema


class ModelError(Exception):
    """A call that returned nothing usable. label is a platform failure code."""

    def __init__(self, label: str, message: str):
        super().__init__(message)
        self.label = label


class Model(Protocol):
    model_id: str

    def propose(self, system: str, turn: str, screenshot: bytes) -> str:
        """Returns the raw reply text for one screen."""
        ...


class GeminiModel:
    def __init__(self, api_key: str, model_id: str, temperature: float, timeout_s: int, created: str,
                 extras: list[str] | tuple = (), outcome: dict | None = None):
        """created: what the workflow makes (flow.json engine.created), for the reply schema; extras and
        outcome: the workflow's extra actions and kind of result (engine-design.md 6.3)."""
        from google import genai  # imported here so tests run without the SDK configured

        self.model_id = model_id
        self.temperature = temperature
        self.timeout_ms = timeout_s * 1000
        self.schema = response_schema(created, extras, outcome)
        self.client = genai.Client(api_key=api_key)

    def propose(self, system: str, turn: str, screenshot: bytes) -> str:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=self.schema,
            temperature=self.temperature,
            http_options=types.HttpOptions(timeout=self.timeout_ms),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = [types.Part.from_text(text=turn), types.Part.from_bytes(data=screenshot, mime_type="image/png")]
        try:
            response = self.client.models.generate_content(model=self.model_id, contents=contents, config=config)
        except errors.APIError as error:
            raise ModelError("model_timeout", f"API error {error.code}: {error.message}") from error
        except Exception as error:  # noqa: BLE001 - network timeouts surface as several exception types
            raise ModelError("model_timeout", str(error)) from error
        if not response.text:
            raise ModelError("invalid_json", "empty reply")
        return response.text


def gemini_for(config: dict, api_key: str) -> "GeminiModel":
    """The model for this workflow: config's model, the workflow's made thing, actions and result."""
    m, w = config["model"], config["workflow"]
    return GeminiModel(api_key, m["id"], m["temperature"], m["timeout_s"], w["created"], w.get("actions") or (), w.get("outcome"))


class ScriptedModel:
    """Replays fixed replies, for tests and for checking a run's plumbing without a model."""

    def __init__(self, replies: list[str], model_id: str = "scripted"):
        self.model_id = model_id
        self.replies = list(replies)
        self.turns: list[str] = []

    def propose(self, system: str, turn: str, screenshot: bytes) -> str:
        self.turns.append(turn)
        if not self.replies:
            return '{"candidates": []}'
        return self.replies.pop(0)


class LabelScriptModel:
    """Proposes one fixed action per screen, finding the element by the text he sees.
    Checks a whole run's plumbing on the real platform without calling a model; it
    proves nothing about how a model would behave."""

    def __init__(self, script: list[dict], model_id: str = "label-script"):
        self.model_id = model_id
        self.script = list(script)
        self.substitute = lambda text: text  # the run's own values ({run}), set by the run

    def propose(self, system: str, turn: str, screenshot: bytes) -> str:
        import json

        if not self.script:
            return '{"candidates": []}'
        step = self.script[0]
        if "observe" in step:  # answer the turn's question (the list, the answer, the page) with this quote
            self.script.pop(0)
            asked = re.search(r"observations\.(\w+):", turn)  # the key the turn's question names
            key = asked.group(1) if asked else "list_has_new_item"
            return json.dumps({"candidates": [], "observations": {
                key: {"answer": True, "quote": self.substitute(step["observe"])}}}, ensure_ascii=False)
        candidate = {k: v for k, v in step.items() if k not in ("label", "target")}
        if isinstance(candidate.get("value"), str):
            candidate["value"] = self.substitute(candidate["value"])
        candidate.setdefault("why", "script")
        label = self.substitute(step["label"]) if step.get("label") else None
        rows = [[c.strip() for c in line.split("|")] for line in turn.splitlines()]
        rows = [r for r in rows if len(r) >= 3 and r[0].startswith("el_")]

        whole = "They are looking at: the whole screen" in turn

        def find(name):
            # An exact match first, so "Finish" is not found inside "I'm finished". A looser match
            # only when the whole screen is in view: in one piece of it, "♧ Atlas Billing" in the
            # middle must not stand in for the menu's "Billing" in a piece not looked at yet.
            exact = next((r for r in rows if r[2].lower() == name.lower()), None)
            return exact or (next((r for r in rows if name.lower() in r[2].lower()), None) if whole else None)

        if label:
            match = find(label)
            drop = find(self.substitute(step["target"])) if step.get("target") else None
            if match and step.get("target") and not drop:
                match = None  # dragging: both ends must be in view
            if match:
                candidate["element"] = match[0]
                if drop:
                    candidate["value"] = drop[0]
            elif "They are looking at: the whole screen" in turn:
                # Not on this screen: look further down, and try the same step next time.
                return json.dumps({"candidates": [{"action": "scroll", "value": "down", "evidence": [], "why": f"looking for {label}"}]})
            else:
                return '{"candidates": []}'  # not in the piece he is looking at: he looks elsewhere
        self.script.pop(0)
        return json.dumps({"candidates": [candidate]}, ensure_ascii=False)


def timed(model: Model, system: str, turn: str, screenshot: bytes) -> tuple[str, int]:
    start = time.monotonic()
    text = model.propose(system, turn, screenshot)
    return text, int((time.monotonic() - start) * 1000)
