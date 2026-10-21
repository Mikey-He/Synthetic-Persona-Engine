"""page_script.js mark(): the flow's locators put data-kl marks on a page that has none of its own
(engine-design.md 6.3). Runs in a real browser; skipped when Playwright's browser is missing."""

import pytest

from sue.screen import PAGE_SCRIPT

PAGE = """<!doctype html><body>
<nav aria-label="Main"><p>People</p><ul><li><a href="/members">Members</a></li><li><a href="/groups">Groups</a></li></ul></nav>
<main>
  <h1>Members</h1><a href="/members/invite">Invite people</a> <a href="/x">Manage members</a>
  <label for="e">Email address</label><input id="e">
  <button aria-label="About roles"><svg width="16" height="16"></svg></button>
  <div role="tooltip">Viewer can open the projects they're added to.</div>
  <button>Send invite</button><label><input type="checkbox"> Send a welcome email</label>
  <button data-kl="T99">Own mark</button>
</main></body>"""


@pytest.fixture(scope="module")
def page():
    sync = pytest.importorskip("playwright.sync_api")
    with sync.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as error:  # noqa: BLE001
            pytest.skip(f"no browser: {error}")
        p = browser.new_page()
        p.add_init_script(path=str(PAGE_SCRIPT))
        p.set_content(PAGE)
        p.evaluate(PAGE_SCRIPT.read_text(encoding="utf-8"))
        yield p
        browser.close()


def marked(page, item):
    return page.evaluate(f"() => [...document.querySelectorAll('[data-kl=\"{item}\"]')].map(e => e.textContent.trim() || e.getAttribute('aria-label'))")


def test_locators_mark_their_controls_and_help_text(page):
    locs = [
        {"item": "T01", "kind": "control", "text": "Members", "region": "nav", "routes": []},
        {"item": "T02", "kind": "control", "text": "Invite people", "routes": ["/members"]},
        {"item": "T03", "kind": "control", "label": "About roles", "routes": []},
        {"item": "T03", "kind": "explains", "text": "Viewer can open the projects", "routes": []},
        {"item": "T04", "kind": "control", "text": "Email address", "routes": []},
        {"item": "T05", "kind": "control", "text": "Send", "routes": []},
        {"item": "T06", "kind": "control", "text": "Own mark", "routes": []},
    ]
    report = page.evaluate("([l, r]) => window.__sue.mark(l, r)", [locs, "/members"])
    assert marked(page, "T01") == ["Members"]  # the link, not the nav labelled Main around it
    assert marked(page, "T02") == ["Invite people"]
    assert marked(page, "T03") == ["About roles"]
    assert page.evaluate("() => document.querySelector('[data-kl-explains]').getAttribute('role')") == "tooltip"
    assert page.evaluate("() => document.querySelector('[data-kl=T04]').id") == "e"
    assert report["T05"] == {"n": 0, "how": "exact"}  # Send is in two controls: a loose match marks neither
    assert report["T06"]["n"] == 1 and marked(page, "T99") == ["Own mark"]  # the page's own mark is kept
    assert report["T01"] == {"n": 1, "how": "exact"} and report["T03:explains"]["n"] == 1


def test_marks_follow_the_route_and_are_taken_off_again(page):
    locs = [{"item": "T02", "kind": "control", "text": "Invite people", "routes": ["/members"]}]
    assert page.evaluate("([l, r]) => window.__sue.mark(l, r)", [locs, "/groups"]) == {}
    assert marked(page, "T02") == [] and marked(page, "T01") == []
    page.evaluate("([l, r]) => window.__sue.mark(l, r)", [locs, "/members?tab=1"])
    assert marked(page, "T02") == ["Invite people"]


def test_the_inventory_lists_controls_not_named_containers(page):
    texts = page.evaluate("() => window.__sue.inventory().map(c => c.text || c.label)")
    assert "Members" in texts and "About roles" in texts and not any("Groups" in t and "Members" in t for t in texts)
    first = page.evaluate("() => window.__sue.inventory()[0]")
    assert first["role"] == "link" and first["region"] == "nav" and first["group"] == "People"
