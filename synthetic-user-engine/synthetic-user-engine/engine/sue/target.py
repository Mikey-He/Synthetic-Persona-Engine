"""Where a run happens: the product under test, behind one small interface (engine-design.md 6.3).

The engine used to talk to one product only, our own UAT platform: its researcher API opened
the session and graded what was saved, its task bar held the I'm finished button, and its
pages carried data-kl marks. A workflow now names its target in flow.json, engine.target:

- "uat": a platform that keeps the engine's contract (sessions, task bar, marks, grading).
  Version A runs here. Nothing about it changed.
- "web": any web product, unchanged. The engine opens its start page in a fresh browser,
  signs in as a test account if asked, draws the task bar outside the page (screen.Strip),
  puts the marks on the page itself from the flow's locators (page_script.js mark), keeps
  the steps in its own log, and grades the result with the flow's own success checks: text
  on a page, a field in a JSON answer, or the final address.

    "target": {"kind": "web", "start": "http://127.0.0.1:4100/home",
               "login": {"url": "/login", "user": "TEAMSPACE_USER", "password": "TEAMSPACE_PASSWORD"},
               "reset": {"method": "POST", "url": "/api/reset"},
               "success": [{"name": "Priya is invited", "type": "json", "url": "/api/invites",
                            "where": {"email": "priya.shah@lumenlabs.example"}, "expect": {"role": "Viewer"}}]}

Credentials are never in flow.json: user and password name variables in engine/.env.

Products that do not fit that (2026-10-19):
- single sign-on, two-step sign-in: "login": {"mode": "session"}. The researcher signs in by hand
  once when recording; the browser's saved sign-in (session.json beside the flow, kept local) starts
  every run, and a run that lands on a sign-in page says the saved sign-in has expired.
- no reset address: "setup" and "cleanup" are steps the engine replays itself before and after each
  run (recorded once, like the task), e.g. create the pending request to approve, delete the invite.
  "{run}" in the task, the steps and the checks becomes a value of its own in every run
  (priya+{run}@example.test), so runs never meet each other's data.
- an answer to find: an "answer" check compares what the person reported with the expected answer.
- a file to download: a "download" check matches the file the product gave.
- an email: a "json" or "text" check may read any address, such as a test inbox's API.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse

END_REASONS = {"abandoned", "step_limit", "time_limit", "loop", "technical_error"}
KINDS = ("uat", "web")
CHECK_TYPES = ("text", "json", "url", "answer", "download")
STEP_ACTIONS = ("request", "goto", "click", "type", "choose", "press", "wait")


class TargetError(RuntimeError):
    """The product cannot be reached, signed in to, or graded."""


@dataclass(frozen=True)
class Session:
    id: str
    token: str
    link: str
    variant: str


class Target(Protocol):
    kind: str
    harness: str  # "page": the product draws the task bar; "strip": the engine draws it outside the page

    def start(self, *, model_id: str, prompt_version: str, persona_id: str) -> Session: ...

    def prepare(self, page) -> None:
        """Before the person starts: sign in, open the start page."""

    def record_step(self, session_id: str, step: dict[str, Any]) -> None: ...

    def end(self, session_id: str, reason: str) -> str: ...

    def result(self, session_id: str, page, report: dict[str, Any] | None = None) -> dict[str, Any]:
        """{"evaluation": {"overall": bool, "criteria": {name: bool}}, "saves": ..., "saved": [...]}.
        report: what the person reported and the product gave them (answer, downloads)."""

    def cleanup(self, page) -> None:
        """After the run: put the product back."""

    def storage_state(self) -> str | None:
        """A saved sign-in to start the browser from."""

    def substitute(self, text: str) -> str:
        """This run's own values put into a text ({run})."""


# ---- our own UAT platform -------------------------------------------------------------------

class UatTarget:
    """The UAT platform's researcher API (sue/platform.py), as before."""

    kind, harness = "uat", "page"

    def __init__(self, console, variant: str):
        self.console = console
        self.variant = variant

    def start(self, *, model_id: str, prompt_version: str, persona_id: str) -> Session:
        s = self.console.create_session(model_id=model_id, prompt_version=prompt_version, persona_id=persona_id,
                                        variant=self.variant)
        return Session(s.id, s.token, s.link, s.variant)

    def prepare(self, page) -> None:
        pass

    def record_step(self, session_id: str, step: dict[str, Any]) -> None:
        self.console.record_step(session_id, step)

    def end(self, session_id: str, reason: str) -> str:
        return self.console.end(session_id, reason)

    def result(self, session_id: str, page, report: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.console.result(session_id)

    def cleanup(self, page) -> None:
        pass

    def storage_state(self) -> str | None:
        return None

    def substitute(self, text: str) -> str:
        return text


# ---- any web product ------------------------------------------------------------------------

def secret(name: str) -> str:
    """A credential named in flow.json, read from the environment (engine/.env)."""
    value = os.environ.get(name, "")
    if not value:
        raise TargetError(f"{name} is not set. Put the test account in engine/.env; flow.json only names the variable.")
    return value


def _norm(value: Any) -> Any:
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip().lower()
    if isinstance(value, list):
        return sorted(json.dumps(_norm(v), sort_keys=True) for v in value)
    if isinstance(value, dict):
        return {k: _norm(v) for k, v in value.items()}
    return value


def dig(data: Any, path: str | None) -> Any:
    """data at a dotted path (invites, data.items, ...); the whole answer when path is empty."""
    for part in (path or "").split("."):
        if not part:
            continue
        data = data.get(part) if isinstance(data, dict) else None
    return data


def rows_of(data: Any, path: str | None) -> list[Any]:
    """The list a json check looks in: at path, else the answer itself, else the one list it holds."""
    found = dig(data, path)
    if isinstance(found, list):
        return found
    if isinstance(found, dict):
        lists = [v for v in found.values() if isinstance(v, list)]
        if len(lists) == 1:
            return lists[0]
        return [found]
    return []


def same(actual: Any, expected: Any) -> bool:
    """Strings ignore case and spacing, lists ignore order."""
    return _norm(actual) == _norm(expected)


def json_check(data: Any, check: dict[str, Any]) -> tuple[bool, str]:
    rows = rows_of(data, check.get("list"))
    where = check.get("where") or {}
    hits = [r for r in rows if isinstance(r, dict) and all(same(dig(r, k), v) for k, v in where.items())]
    if "count" in check and len(hits) != check["count"]:
        return False, f"{len(hits)} rows match, expected {check['count']}"
    if not hits:
        return False, "no row matches " + json.dumps(where, ensure_ascii=False)
    expect = check.get("expect") or {}
    for row in hits:
        wrong = {k: dig(row, k) for k, v in expect.items() if not same(dig(row, k), v)}
        if not wrong:
            return True, "a row matches and has every expected value"
    return False, "the matching row has " + json.dumps(wrong, ensure_ascii=False)


def check_problems(check: Any, n: int) -> list[str]:
    where = f"engine.target.success {n}"
    if not isinstance(check, dict):
        return [f"{where}: an object"]
    out = []
    if not isinstance(check.get("name"), str) or not check["name"].strip():
        out.append(f"{where}: a name, as the report shows it")
    kind = check.get("type")
    if kind not in CHECK_TYPES:
        out.append(f"{where}: type is one of {', '.join(CHECK_TYPES)}")
    elif kind == "text" and not (isinstance(check.get("contains"), str) and check["contains"].strip()):
        out.append(f"{where}: a text check needs contains")
    elif kind == "json" and not (isinstance(check.get("url"), str) and (check.get("where") or check.get("expect") or "count" in check)):
        out.append(f"{where}: a json check needs url and where, expect or count")
    elif kind == "url" and not isinstance(check.get("matches"), str):
        out.append(f"{where}: a url check needs matches (a regular expression)")
    elif kind == "answer" and not (isinstance(check.get("expected"), list) and check["expected"]):
        out.append(f"{where}: an answer check needs expected, the right answers as a list")
    elif kind == "download" and not isinstance(check.get("matches"), str):
        out.append(f"{where}: a download check needs matches (a regular expression for the file name)")
    return out


def step_problems(steps: Any, where: str) -> list[str]:
    if steps is None:
        return []
    if not isinstance(steps, list):
        return [f"{where}: a list of steps"]
    out = []
    for n, st in enumerate(steps, 1):
        a = st.get("action") if isinstance(st, dict) else None
        if a not in STEP_ACTIONS:
            out.append(f"{where} step {n}: action is one of {', '.join(STEP_ACTIONS)}")
        elif a in ("request", "goto") and not isinstance(st.get("url"), str):
            out.append(f"{where} step {n}: needs url")
        elif a in ("click", "type", "choose") and not isinstance(st.get("locate"), dict):
            out.append(f"{where} step {n}: needs locate, the control as an item locator names it")
    return out


def target_problems(target: Any) -> list[str]:
    """What is missing in flow.json engine.target; empty when it can be run."""
    if target is None:
        return []  # no target: the UAT platform, as Version A always ran
    if not isinstance(target, dict) or target.get("kind") not in KINDS:
        return [f"engine.target.kind: one of {', '.join(KINDS)}"]
    if target["kind"] == "uat":
        return []
    out = []
    start = target.get("start")
    if not isinstance(start, str) or urlparse(start).scheme not in ("http", "https"):
        out.append("engine.target.start: the full address of the page the task starts on")
    login = target.get("login")
    if login is not None and not (isinstance(login, dict) and (login.get("mode") == "session" or (
            isinstance(login.get("url"), str) and isinstance(login.get("user"), str) and isinstance(login.get("password"), str)))):
        out.append("engine.target.login: mode session, or url and the names of the user and password variables in engine/.env")
    out += step_problems(target.get("setup"), "engine.target.setup")
    out += step_problems(target.get("cleanup"), "engine.target.cleanup")
    reset = target.get("reset")
    if reset is not None and not (isinstance(reset, dict) and isinstance(reset.get("url"), str)):
        out.append("engine.target.reset: url (and method), called before every run")
    success = target.get("success")
    if not isinstance(success, list) or not success:
        out.append("engine.target.success: at least one check of what the task should leave behind")
    else:
        for n, check in enumerate(success, 1):
            out += check_problems(check, n)
    return out


class WebTarget:
    """Any web product, as it is. Nothing is sent to it but what a person would do, plus the
    flow's own reset and checks."""

    kind, harness = "web", "strip"

    def __init__(self, spec: dict[str, Any], settle_ms: int = 400, folder: str | os.PathLike | None = None):
        """folder: where the flow lives (its saved sign-in, its files)."""
        self.spec = spec
        self.start_url = os.environ.get(spec["startEnv"], spec["start"]) if spec.get("startEnv") else spec["start"]
        self.settle_ms = settle_ms
        self.folder = folder
        self.steps: dict[str, list[dict[str, Any]]] = {}
        self.ended: dict[str, str] = {}
        self.run_id = ""

    def url(self, path: str) -> str:
        return urljoin(self.start_url, self.substitute(path))

    def substitute(self, text: Any) -> Any:
        """{run} becomes this run's own short value, in texts and in the values of checks."""
        if isinstance(text, str):
            return text.replace("{run}", self.run_id)
        if isinstance(text, list):
            return [self.substitute(t) for t in text]
        if isinstance(text, dict):
            return {k: self.substitute(v) for k, v in text.items()}
        return text

    def storage_state(self) -> str | None:
        login = self.spec.get("login") or {}
        if login.get("mode") != "session":
            return None
        from pathlib import Path
        path = Path(self.folder or ".") / (login.get("file") or "session.json")
        if not path.exists():
            raise TargetError("This product signs in by hand: record the task once and sign in there, so the sign-in is saved.")
        return str(path)

    def start(self, *, model_id: str, prompt_version: str, persona_id: str) -> Session:
        sid = f"web-{time.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
        self.run_id = "r" + secrets.token_hex(2)
        self.steps[sid] = []
        return Session(sid, sid, self.start_url, "web")

    def _reset(self, page) -> None:
        reset = self.spec.get("reset")
        if not reset:
            return
        response = page.request.fetch(self.url(reset["url"]), method=(reset.get("method") or "POST").upper())
        if not response.ok:
            raise TargetError(f"Resetting the product failed: {reset['url']} answered {response.status}")

    def _sign_in(self, page) -> None:
        """Signs in the way a person would: the user name in the first text or email box, the
        password in the password box, then Enter. Done by code, never by the persona. A saved
        sign-in only needs checking: the start page must not send him to a sign-in page."""
        login = self.spec.get("login")
        if not login:
            return
        if login.get("mode") == "session":
            from .screen import route_of
            page.goto(self.start_url)
            page.wait_for_load_state("domcontentloaded")
            if route_of(page.url).split("?")[0] != route_of(self.start_url).split("?")[0]:
                raise TargetError("The saved sign-in has expired: the start page sent the browser to "
                                  f"{route_of(page.url)}. Record the task again and sign in there.")
            return
        page.goto(self.url(login["url"]))
        page.wait_for_load_state("domcontentloaded")
        user = page.locator("input[type=email], input[type=text], input:not([type])").first
        password = page.locator("input[type=password]").first
        user.fill(secret(login["user"]))
        password.fill(secret(login["password"]))
        password.press("Enter")
        try:
            page.wait_for_url(lambda u: urlparse(u).path != urlparse(self.url(login["url"])).path, timeout=10000)
        except Exception as error:  # noqa: BLE001 - any failure means the sign-in did not go through
            raise TargetError(f"Signing in at {login['url']} did not leave the sign-in page; check the test account") from error

    def replay(self, page, steps: list[dict[str, Any]], what: str) -> None:
        """Steps the engine does itself, not the persona: setting up before a run, cleaning up after."""
        for n, st in enumerate(steps or [], 1):
            a = st["action"]
            try:
                if a == "request":
                    body = self.substitute(st.get("body"))
                    r = page.request.fetch(self.url(st["url"]), method=(st.get("method") or "POST").upper(),
                                           data=json.dumps(body) if body is not None else None,
                                           headers={"Content-Type": "application/json"} if body is not None else None)
                    if not r.ok:
                        raise TargetError(f"{st['url']} answered {r.status}")
                    continue
                if a == "goto":
                    page.goto(self.url(st["url"]))
                elif a == "wait":
                    page.wait_for_timeout(int(st.get("ms", 500)))
                elif a == "press":
                    page.keyboard.press(st.get("value") or "Enter")
                else:
                    if not page.evaluate("l => window.__sue.target(l)", self.substitute(st["locate"])):
                        raise TargetError(f"no control matches {st['locate']} on {page.url}")
                    el = page.locator("[data-sue-target]").first
                    if a == "click":
                        el.click()
                    elif a == "type":
                        el.fill(self.substitute(str(st.get("value", ""))))
                    elif a == "choose":
                        el.select_option(label=self.substitute(str(st.get("value", ""))))
                try:
                    page.wait_for_load_state("networkidle", timeout=3000)
                except Exception:  # noqa: BLE001 - a page that keeps polling
                    pass
                page.wait_for_timeout(self.settle_ms)
            except TargetError as error:
                raise TargetError(f"{what} step {n} ({a}) did not work: {error}") from None
            except Exception as error:  # noqa: BLE001 - any browser failure in a scripted step
                raise TargetError(f"{what} step {n} ({a}) did not work: {str(error).splitlines()[0]}") from None

    def prepare(self, page) -> None:
        self._reset(page)
        self._sign_in(page)
        if self.spec.get("setup"):
            self.replay(page, self.spec["setup"], "Set-up")

    def cleanup(self, page) -> None:
        if self.spec.get("cleanup"):
            self.replay(page, self.spec["cleanup"], "Clean-up")

    def record_step(self, session_id: str, step: dict[str, Any]) -> None:
        self.steps.setdefault(session_id, []).append(step)

    def end(self, session_id: str, reason: str) -> str:
        if reason not in END_REASONS:
            raise ValueError(f"unknown termination reason {reason!r}")
        self.ended.setdefault(session_id, reason)
        return self.ended[session_id]

    def check(self, check: dict[str, Any], page, report: dict[str, Any] | None = None) -> tuple[bool, str]:
        check = self.substitute(check)
        kind, report = check["type"], report or {}
        if kind == "answer":
            said = report.get("answer")
            if not said:
                return False, "they reported no answer"
            ok = any(answer_matches(said, e) for e in check["expected"])
            return ok, f"they reported {said!r}" + ("" if ok else f"; expected {' or '.join(map(repr, check['expected']))}")
        if kind == "download":
            files = report.get("downloads") or []
            ok = any(re.search(check["matches"], f) for f in files)
            return ok, ("downloaded " + ", ".join(files)) if files else "nothing was downloaded"
        if kind == "url":
            ok = re.search(check["matches"], page.url) is not None
            return ok, f"ended on {page.url}"
        if kind == "json":
            response = page.request.get(self.url(check["url"]))
            if not response.ok:
                return False, f"{check['url']} answered {response.status}"
            try:
                return json_check(response.json(), check)
            except ValueError:
                return False, f"{check['url']} did not answer JSON"
        # text: open the page in a new tab of the same browser (same sign-in), read what it shows
        other = page.context.new_page()
        try:
            other.goto(self.url(check.get("url") or page.url))
            try:
                other.wait_for_load_state("networkidle", timeout=5000)
            except Exception:  # noqa: BLE001 - a page that keeps polling is read after its settle time
                pass
            other.wait_for_timeout(self.settle_ms)
            scope = other.locator(check["selector"]).first if check.get("selector") else other.locator("body")
            text = scope.inner_text(timeout=5000)
        finally:
            other.close()
        ok = _norm(check["contains"]) in _norm(text)
        return ok, ("the page shows " if ok else "the page does not show ") + repr(check["contains"])

    def result(self, session_id: str, page, report: dict[str, Any] | None = None) -> dict[str, Any]:
        criteria, details = {}, {}
        for check in self.spec["success"]:
            try:
                ok, why = self.check(check, page, report)
            except Exception as error:  # noqa: BLE001 - a check that cannot be made counts as failed, with why
                ok, why = False, f"could not check: {error}"
            criteria[check["name"]] = ok
            details[check["name"]] = why
        return {"evaluation": {"overall": bool(criteria) and all(criteria.values()), "criteria": criteria,
                               "details": details}, "saves": None, "saved": []}


def answer_matches(said: str, expected: str) -> bool:
    """An answer counts when it holds the expected one, ignoring case and spacing; a number counts
    when it is the same number however it is written ($1,000 and 1000)."""
    if _norm(expected) in _norm(said):
        return True
    num = lambda t: [float(x.replace(",", "")) for x in re.findall(r"-?\d[\d,]*\.?\d*", t)]  # noqa: E731
    want = num(expected)
    return bool(want) and all(w in num(said) for w in want)


def make_target(config: dict[str, Any]) -> Target:
    """The target the workflow names; the UAT platform when it names none."""
    spec = config["workflow"].get("target") or {"kind": "uat"}
    if spec["kind"] == "web":
        from pathlib import Path
        return WebTarget(spec, config["platform"]["settle_ms"], Path(config["workflow"]["file"]).parent)
    from .config import platform_url, require_env
    from .platform import ResearchConsole

    return UatTarget(ResearchConsole(platform_url(config), require_env("ADMIN_PASSWORD")),
                     spec.get("variant") or config["platform"]["variant"])
