"""The research side of a run: the platform's researcher console API (uat-platform
README, "Connecting an AI engine"). It runs in its own HTTP client, never in the
browser the screenshots come from."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

END_REASONS = {"abandoned", "step_limit", "time_limit", "loop", "technical_error"}


@dataclass(frozen=True)
class Session:
    id: str
    token: str
    link: str
    variant: str


class ResearchConsole:
    def __init__(self, base_url: str, password: str, client: httpx.Client | None = None):
        self.base = base_url.rstrip("/")
        self.http = client or httpx.Client(timeout=30)
        response = self.http.post(f"{self.base}/api/admin/login", data={"password": password}, follow_redirects=False)
        if response.status_code != 303 or not response.headers.get("location", "").endswith("/admin"):
            raise RuntimeError("Researcher console sign-in failed. Check ADMIN_PASSWORD in engine/.env.")

    def create_session(self, *, model_id: str, prompt_version: str, persona_id: str, variant: str) -> Session:
        response = self.http.post(
            f"{self.base}/api/admin/sessions",
            json={
                "actorType": "synthetic",
                "modelId": model_id,
                "promptVersion": prompt_version,
                "personaId": persona_id,
                "calibrationId": None,
                "variant": variant,
            },
        )
        response.raise_for_status()
        body = response.json()
        return Session(body["id"], body["token"], body["link"], body["variant"])

    def record_step(self, session_id: str, step: dict[str, Any]) -> None:
        self.http.post(f"{self.base}/api/admin/sessions/{session_id}/agent-steps", json=step).raise_for_status()

    def status(self, session_id: str) -> dict[str, Any]:
        response = self.http.get(f"{self.base}/api/admin/sessions/{session_id}")
        response.raise_for_status()
        return response.json()

    def result(self, session_id: str) -> dict[str, Any]:
        """Saved budgets and the platform's own evaluation, read after the run stops
        (engine-design.md 4.7, 7)."""
        response = self.http.get(f"{self.base}/api/admin/sessions/{session_id}/result")
        response.raise_for_status()
        return response.json()

    def events(self, *session_ids: str) -> dict[str, list[dict[str, Any]]]:
        """The platform's own event log for these sessions, from the researcher export.
        Human and engine sessions are logged the same way, so the two can be compared."""
        response = self.http.get(f"{self.base}/api/admin/exports/events.json")
        response.raise_for_status()
        wanted = set(session_ids)
        return {s["session_id"]: s["events"] for s in response.json()["sessions"] if s["session_id"] in wanted}

    def end(self, session_id: str, reason: str) -> str:
        """Ends the session and returns the reason it ended with. If it had already
        ended (the agent clicked I'm finished), that reason wins."""
        if reason not in END_REASONS:
            raise ValueError(f"unknown termination reason {reason!r}")
        response = self.http.post(f"{self.base}/api/admin/sessions/{session_id}/end", json={"terminationReason": reason})
        if response.status_code == 409:
            return self.status(session_id)["terminationReason"]
        response.raise_for_status()
        return reason
