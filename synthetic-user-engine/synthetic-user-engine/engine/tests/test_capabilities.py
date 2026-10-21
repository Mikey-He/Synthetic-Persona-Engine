"""What a product may be made of, run end to end (engine-design.md 6.3).

One small page per capability (tests/fixtures/apps), served locally: a native dropdown, a key, an
answer to find, a closed shadow root, an embedded frame, a new tab, a menu under the mouse, a drag,
a file to upload, a file to download, a panel that scrolls inside the page, a Chinese page, text on
a canvas, set-up and clean-up steps with values of the run's own, and a saved sign-in. Each is a
whole run with the full card and a scripted model (no model calls); the product's own grading
(success checks) decides. The pages save what was done in the browser and result.html shows it.
"""

import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

from sue.config import load_config
from sue.model import LabelScriptModel
from sue.run import run
from sue.target import TargetError, make_target

APPS = Path(__file__).parent / "fixtures" / "apps"
pytestmark = pytest.mark.filterwarnings("ignore")


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def site():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as pw:
        try:
            pw.chromium.launch().close()
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"no browser: {error}")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(APPS)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def word(ref):
    return [{"type": "word", "ref": ref}]


def flow_for(site, page, task, plumbing, success, consequential=(), **engine):
    return {
        "format": "sue-flow", "version": 1, "name": f"Fixture {page}", "task": task,
        "screens": [{"id": "S1", "name": page, "route": f"/{page}"}],
        "steps": [{"id": "A1", "screen": "S1", "action": "Do the task", "ways": [], "risky": False, "defaults": ""}],
        "items": [], "signals": {}, "checks": [], "situation": {"urgency": "calm", "stakes": "low"}, "org": "",
        "engine": {"created": "item", "routes": {"list": [], "path": [f"/{p.name}" for p in APPS.glob("*.html")]},
                   "labels": {"consequential": list(consequential), "advancing": []}, "items": {},
                   "words": {"dataTerms": [], "forceFake": []}, "plumbing": plumbing,
                   "target": {"kind": "web", "start": f"{site}/{page}", "success": success, **engine.pop("target", {})},
                   **engine},
    }


def go(tmp_path, flow, card="full", steps=None):
    path = tmp_path / f"{flow['name'].split()[-1].replace('.', '_')}.json"
    path.write_text(json.dumps(flow), encoding="utf-8")
    config = load_config(flow=path)
    config["paths"]["runs"] = tmp_path / "runs"
    return run(card, config, make_target(config), LabelScriptModel(flow["engine"]["plumbing"]),
               max_steps=steps or len(flow["engine"]["plumbing"]) + 8)


def shows(text, url="/result.html"):
    return {"name": f"shows {text}", "type": "text", "url": url, "contains": text}


def passed(summary):
    ev = summary.get("evaluation") or {}
    assert ev.get("overall"), json.dumps({"stop": summary["stop"], "evaluation": ev}, indent=1)


def test_a_native_dropdown(site, tmp_path):
    f = flow_for(site, "select.html", "Make the member a viewer.",
                 [{"action": "choose", "label": "Role", "value": "Viewer", "evidence": word("Role")},
                  {"action": "click", "label": "Save role", "evidence": word("Save role")}],
                 [shows("role=Viewer")], ["Save role"])
    passed(go(tmp_path, f))


def test_a_key_and_an_answer_to_find(site, tmp_path):
    f = flow_for(site, "search.html", "Find out the monthly price of the Pro plan.",
                 [{"action": "type", "label": "Search plans", "value": "pro", "evidence": word("Search plans")},
                  {"action": "press", "value": "Enter", "evidence": word("Search plans")},
                  {"observe": "$49"}],
                 [{"name": "the right price", "type": "answer", "expected": ["$49"]}],
                 outcome={"kind": "answer", "question": "the monthly price of the Pro plan"})
    s = go(tmp_path, f)
    passed(s)
    assert s["reported"] == "$49"


def test_a_closed_shadow_root(site, tmp_path):
    f = flow_for(site, "shadow.html", "Approve Sam's leave request.",
                 [{"action": "click", "label": "Approve request", "evidence": word("Approve request")}],
                 [shows("approved=Sam Rivera")], ["Approve request"])
    passed(go(tmp_path, f))


def test_an_embedded_frame(site, tmp_path):
    f = flow_for(site, "frame.html", "Pay with the card 4111 1111 1111 1111.",
                 [{"action": "type", "label": "Card number", "value": "4111 1111 1111 1111", "evidence": word("Card number")},
                  {"action": "click", "label": "Pay now", "evidence": word("Pay now")}],
                 [shows("paid=4111 1111 1111 1111")], ["Pay now"])
    passed(go(tmp_path, f))


def test_a_new_tab(site, tmp_path):
    f = flow_for(site, "newtab.html", "Confirm the monthly report.",
                 [{"action": "click", "label": "Open the monthly report", "evidence": word("Open the monthly report")},
                  {"action": "click", "label": "Confirm report", "evidence": word("Confirm report")}],
                 [shows("confirmed=monthly")], ["Confirm report"])
    passed(go(tmp_path, f))


def test_a_menu_under_the_mouse_and_a_page_to_reach(site, tmp_path):
    f = flow_for(site, "hover.html", "Find the page where you change your password.",
                 [{"action": "hover", "label": "Account menu", "evidence": word("Account menu")},
                  {"action": "click", "label": "Account settings", "evidence": word("Account settings")},
                  {"observe": "Account settings"}],
                 [{"name": "on the settings page", "type": "url", "matches": r"settings\.html"}],
                 outcome={"kind": "place"})
    passed(go(tmp_path, f))


def test_a_drag(site, tmp_path):
    f = flow_for(site, "drag.html", "Move the summary task to Done.",
                 [{"action": "drag", "label": "Write the summary", "target": "Done column", "evidence": word("Write the summary")}],
                 [shows("moved=Write the summary")], ["Write the summary"])
    passed(go(tmp_path, f))


def test_a_file_to_upload(site, tmp_path):
    f = flow_for(site, "upload.html", "Attach your receipt and submit the expense.",
                 [{"action": "click", "label": "Upload receipt", "evidence": word("Upload receipt")},
                  {"action": "click", "label": "Submit expense", "evidence": word("Submit expense")}],
                 [shows("receipt=sample.pdf")], ["Submit expense"])
    passed(go(tmp_path, f))


def test_a_file_to_download(site, tmp_path):
    f = flow_for(site, "download.html", "Export the report as CSV.",
                 [{"action": "click", "label": "Export as CSV", "evidence": word("Export as CSV")}],
                 [{"name": "the CSV", "type": "download", "matches": r"\.csv$"}], ["Export as CSV"])
    s = go(tmp_path, f)
    passed(s)
    assert s["downloads"] == ["report.csv"] and (Path(s["dir"]) / "report.csv").exists()


def test_a_panel_that_scrolls_inside_the_page(site, tmp_path):
    f = flow_for(site, "scroll.html", "Archive all messages.",
                 [{"action": "click", "label": "Archive all messages", "evidence": word("Archive all messages")}],
                 [shows("archived=all")], ["Archive all messages"])
    passed(go(tmp_path, f, steps=30))


def test_a_chinese_page(site, tmp_path):
    f = flow_for(site, "chinese.html", "Set the budget to 1000.",
                 [{"action": "type", "label": "预算金额", "value": "1000", "evidence": word("预算金额")},
                  {"action": "click", "label": "保存预算", "evidence": word("保存预算")}],
                 [shows("budget=1000")], ["保存预算"])
    passed(go(tmp_path, f))
    blank = go(tmp_path, f, card="blank", steps=3)
    first = json.loads((Path(blank["dir"]) / "steps.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert "保存预算" not in first["prompt"] and "预算金额" not in first["prompt"]  # the blank card cannot read them


def test_text_on_a_canvas(site, tmp_path):
    pytest.importorskip("rapidocr_onnxruntime")
    f = flow_for(site, "canvas.html", "Choose to continue.",
                 [{"action": "click", "label": "Continue", "evidence": word("Continue")}],
                 [shows("continued=yes")], ["Continue"])
    passed(go(tmp_path, f))


def test_set_up_and_clean_up_steps_with_values_of_the_run(site, tmp_path):
    f = flow_for(site, "requests.html", "Approve Request {run}.",
                 [{"action": "click", "label": "Approve Request {run}", "evidence": word("Approve Request {run}")}],
                 [shows("approved=Request {run}")], ["Approve Request {run}"],
                 target={"setup": [{"action": "goto", "url": "/setup.html"},
                                   {"action": "type", "locate": {"text": "Title"}, "value": "Request {run}"},
                                   {"action": "click", "locate": {"text": "Create request"}}],
                         "cleanup": [{"action": "goto", "url": "/requests.html"},
                                     {"action": "click", "locate": {"text": "Clear all requests"}}]})
    s = go(tmp_path, f)
    passed(s)
    assert s["cleanup_error"] is None


def test_a_saved_sign_in(site, tmp_path):
    from playwright.sync_api import sync_playwright

    f = flow_for(site, "app.html", "Start the review.",
                 [{"action": "click", "label": "Start the review", "evidence": word("Start the review")}],
                 [shows("reviewed=yes")], ["Start the review"], target={"login": {"mode": "session"}})
    with pytest.raises(TargetError, match="signs in by hand"):
        go(tmp_path, f)
    with sync_playwright() as pw:  # the researcher signs in once, by hand
        browser = pw.chromium.launch()
        ctx = browser.new_context()
        page = ctx.new_page()
        page.goto(f"{site}/login.html")
        page.click("text=Continue with company account")
        page.wait_for_url("**/app.html")
        ctx.storage_state(path=str(tmp_path / "session.json"))
        browser.close()
    passed(go(tmp_path, f))
    (tmp_path / "session.json").write_text('{"cookies": [], "origins": []}', encoding="utf-8")
    with pytest.raises(TargetError, match="expired"):
        go(tmp_path, f)
