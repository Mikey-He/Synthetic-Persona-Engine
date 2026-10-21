"""The engine runs any web product from its flow.json (engine-design.md 6.3): targets, locators,
self-test cards, the task bar drawn outside the page, and a draft assembled from a recording."""

import io
import json
from pathlib import Path

import pytest

from sue import locate
from sue.draft import assemble
from sue.screen import Strip, route_of
from sue.selfcards import build
from sue.target import json_check, target_problems
from sue.workflow import locator_problems, locators, problems

ROOT = Path(__file__).resolve().parents[2]


def test_version_a_self_cards_are_what_the_persona_builder_saved(config):
    flow = json.loads(config["paths"]["flow"].read_text(encoding="utf-8"))
    for kind in ("full", "blank"):
        saved = json.loads((config["paths"]["personas"] / f"{kind}-card.json").read_text(encoding="utf-8"))
        made = build(flow, kind)
        assert {k: v for k, v in made.items() if k != "builtAt"} == {k: v for k, v in saved.items() if k != "builtAt"}


def test_version_a_needs_no_target_and_no_locators(config):
    assert config["workflow"]["target"] == {"kind": "uat"} and config["workflow"]["locators"] == []


def test_a_web_target_needs_a_start_page_and_a_check():
    assert target_problems(None) == [] and target_problems({"kind": "uat"}) == []
    bad = target_problems({"kind": "web", "start": "/home", "success": []})
    assert any("start" in p for p in bad) and any("success" in p for p in bad)
    good = {"kind": "web", "start": "http://127.0.0.1:4100/home", "login": {"url": "/login", "user": "U", "password": "P"},
            "success": [{"name": "Invited", "type": "json", "url": "/api/invites", "where": {"email": "a@b.c"}}]}
    assert target_problems(good) == []
    assert any("contains" in p for p in target_problems({**good, "success": [{"name": "x", "type": "text"}]}))


def test_json_checks_ignore_case_and_list_order():
    answer = {"invites": [{"email": "priya@x.example", "role": "viewer", "projects": ["Lyra"]},
                          {"email": "sam@x.example", "role": "admin", "projects": ["Orion", "Vega"]}]}
    ok, _ = json_check(answer, {"where": {"email": "PRIYA@x.example"}, "expect": {"role": "Viewer", "projects": ["Lyra"]}})
    assert ok
    ok, why = json_check(answer, {"where": {"email": "priya@x.example"}, "expect": {"projects": ["Lyra", "Orion"]}})
    assert not ok and "projects" in why
    assert json_check(answer, {"where": {"email": "sam@x.example"}, "expect": {"projects": ["Vega", "Orion"]}})[0]
    assert not json_check(answer, {"where": {"email": "nobody@x.example"}})[0]
    assert json_check(answer, {"list": "invites", "where": {"role": "admin"}, "count": 1})[0]


def test_routes_keep_a_fragment_route_and_drop_the_session():
    assert route_of("http://x/s/abc123/billing/budgets") == "/billing/budgets"
    assert route_of("http://x/app/#/members/invite") == "/app/#/members/invite"
    assert route_of("http://x/app/#!/members") == "/app/#/members"
    assert route_of("http://x/members#top") == "/members"


CONTROLS = [
    {"tag": "a", "role": "link", "text": "Members", "label": "", "region": "nav", "group": "People"},
    {"tag": "a", "role": "link", "text": "Manage members", "label": "", "region": "main", "group": ""},
    {"tag": "button", "role": "button", "text": "Send invite", "label": "", "region": "main", "group": ""},
    {"tag": "button", "role": "button", "text": "", "label": "About roles", "region": "main", "group": ""},
    {"tag": "a", "role": "link", "text": "Members", "label": "", "region": "main", "group": ""},
]


def test_a_locator_is_the_simplest_that_finds_one_control():
    assert locate.build(CONTROLS, 0) == {"text": "Members", "region": "nav"}
    assert locate.build(CONTROLS, 4) == {"text": "Members", "region": "main"}
    assert locate.build(CONTROLS, 2) == {"text": "Send invite"}
    assert locate.build(CONTROLS, 3) == {"label": "About roles"}
    for i in range(len(CONTROLS)):
        assert locate.find(CONTROLS, locate.build(CONTROLS, i)) == [i]


def test_a_loose_match_counts_only_when_it_finds_one_control():
    assert locate.find(CONTROLS, {"text": "Send"}) == [2]  # one control contains it
    assert locate.find(CONTROLS, {"text": "embers"}) == []  # three do: none is marked


def test_locators_take_their_step_screen_route(config):
    flow = {"screens": [{"id": "S1", "name": "Members", "route": "/members"}], "steps": [{"id": "A1", "screen": "S1"}],
            "items": [{"id": "T01", "step": "A1", "locate": {"text": "Invite people"}, "explainedBy": {"text": "We'll send"}},
                      {"id": "T02", "step": "A1", "locate": {"label": "Help", "route": ["/a", "/b"]}}]}
    assert locator_problems(flow) == []
    locs = locators(flow)
    assert locs[0] == {"text": "Invite people", "item": "T01", "kind": "control", "routes": ["/members"]}
    assert locs[1]["kind"] == "explains" and locs[2]["routes"] == ["/a", "/b"]
    flow["items"][0]["locate"] = {"role": "button", "colour": "red"}
    found = locator_problems(flow)
    assert any("unknown keys" in p for p in found) and any("text, label or selector" in p for p in found)


def test_the_task_bar_is_drawn_below_the_page():
    pytest.importorskip("PIL")
    from PIL import Image

    strip = Strip("Invite Priya Shah as a viewer. " * 20, "I'm finished", 1440)
    assert strip.line.endswith("...") and strip.line.startswith("Task: Invite Priya")
    page = io.BytesIO()
    Image.new("RGB", (1440, 844), (255, 255, 255)).save(page, format="PNG")
    out = Image.open(io.BytesIO(strip.compose(page.getvalue())))
    assert out.size == (1440, 900)
    button = strip.element(844)
    assert button["harness"] and button["virtual"] and button["box"]["y"] >= 844


def recording():
    shot = lambda n, route, controls, text: {"n": n, "route": route, "title": route, "controls": controls, "text": text}  # noqa: E731
    members = [{"tag": "a", "role": "link", "text": "Members", "label": "", "region": "nav", "group": "People"},
               {"tag": "a", "role": "link", "text": "Invite people", "label": "", "region": "main", "group": ""}]
    form = [{"tag": "input", "role": "textbox", "text": "Email address", "label": "", "region": "main", "group": ""},
            {"tag": "button", "role": "button", "text": "", "label": "About roles", "region": "main", "group": ""},
            {"tag": "button", "role": "button", "text": "Send invite", "label": "", "region": "main", "group": ""}]
    return {
        "start": "http://127.0.0.1:4100/members", "viewport": {"width": 1440, "height": 844},
        "login": {"url": "/login", "user": "U", "password": "P"},
        "states": [shot(0, "/members", members, "Members"), shot(1, "/members/invite", form, "Invite people"),
                   shot(2, "/members/invite", form, "Invite people\nViewer can open projects but cannot change anything."),
                   shot(3, "/members", members, "Members\nPriya Shah Invited")],
        "actions": [
            {"n": 1, "before": 0, "after": 1, "action": "click", "control": members[1]},
            {"n": 2, "before": 1, "after": 1, "action": "type", "control": form[0], "value": "priya@x.example"},
            {"n": 3, "before": 1, "after": 2, "action": "click", "control": form[1]},
            {"n": 4, "before": 2, "after": 3, "action": "click", "control": form[2]},
        ],
        "network": [{"after": 4, "method": "POST", "path": "/api/invites", "status": None, "sent": {"email": "priya@x.example"}},
                    {"after": 4, "method": "GET", "path": "/api/invites", "status": 200, "answer": {"invites": []}}],
    }


AI = {
    "screens": [{"route": "/members", "name": "Members"}, {"route": "/members/invite", "name": "Invite people"}],
    "steps": [{"key": "s1", "actions": [1], "action": "Click Invite people", "risky": False, "defaults": ""},
              {"key": "s2", "actions": [2, 3, 4], "action": "Fill in the email, then Send invite", "risky": True,
               "defaults": "Contributor is chosen"}],
    "items": [
        {"key": "i1", "step": "s1", "kind": "location", "text": "Invite people is above the member list", "meaning": "",
         "needed": True, "onAction": 0, "onScreen": -1, "onControl": -1, "explainedBy": "", "entry": True, "exps": ["e1"]},
        {"key": "i2", "step": "s2", "kind": "icon", "text": "The question mark about roles opens help", "meaning": "",
         "needed": False, "onAction": 0, "onScreen": -1, "onControl": -1, "explainedBy": "", "help": True, "exps": []},
        {"key": "i3", "step": "s2", "kind": "concept", "text": "A viewer cannot change anything",
         "meaning": "Viewer can open projects only", "needed": True, "onAction": 0, "onScreen": -1, "onControl": -1,
         "explainedBy": "", "exps": ["e1", "e9"]},
        {"key": "i4", "step": "s2", "kind": "word", "text": "Email address", "meaning": "Where the invite goes",
         "common": "common", "needed": True, "exps": []},
    ],
    "groups": [{"key": "admin", "source": "work", "labelEn": "Admin work", "labelZh": "管理工作"}],
    "experiences": [{"key": "e1", "group": "admin", "text": "Has invited people", "questionEn": "Have you invited people?",
                     "questionZh": "你邀请过别人吗？"}],
    "knowledgeGroups": [{"key": "terms", "title": "Terms", "description": "Words", "examples": "", "default": 1, "word": True,
                         "items": ["i4", "i1"]}],
    "created": "Invite", "consequential": ["Send invite"], "advancing": [], "listRoute": "/members", "listQuote": "Priya Shah",
    "dataTerms": ["Priya Shah"], "forceFake": [], "signals": {"toast": True, "list": True, "external": False, "test": False},
    "checks": ["Priya is invited"],
    "success": [{"name": "Invited", "type": "json", "url": "/api/invites", "where": [{"field": "email", "value": "priya@x.example"}],
                 "expect": [{"field": "projects", "value": "[\"Lyra\"]"}]},
                {"name": "Fetched nowhere", "type": "json", "url": "/api/secret", "where": [{"field": "a", "value": "b"}]}],
    "org": "An admin.", "situation": {"urgency": "calm", "stakes": "low"},
}


def test_a_draft_is_assembled_from_the_recording_and_can_drive_the_engine():
    flow, notes = assemble(recording(), {"name": "Invite", "task": "Invite Priya."}, AI)
    assert [s["route"] for s in flow["screens"]] == ["/members", "/members/invite"]
    assert [s["screen"] for s in flow["steps"]] == ["S1", "S2"]
    items = {i["id"]: i for i in flow["items"]}
    assert items["T01"]["locate"] == {"text": "Invite people"}  # a place item: the control clicked at its step
    assert items["T02"]["locate"] == {"label": "About roles"} and flow["engine"]["items"]["help"] == ["T02"]
    assert items["T03"]["explainedBy"] == {"text": "Viewer can open projects but cannot change anything."}
    assert items["T03"]["exps"] == ["X01"]  # e9 does not exist
    assert flow["engine"]["items"]["entry"] == ["T01"]
    # code puts every item that is not a habit in one knowledge group, words with words
    owned = {i for g in flow["knowledgeGroups"] for i in g["items"]}
    assert owned == {"T01", "T02", "T03", "T04"}
    assert all({items[i]["kind"] == "word" for i in g["items"]} == {g["word"]} for g in flow["knowledgeGroups"])
    engine = flow["engine"]
    assert engine["plumbing"][0] == {"action": "click", "label": "Invite people", "evidence": [{"type": "word", "ref": "Invite people"}]}
    assert engine["plumbing"][1]["value"] == "priya@x.example" and engine["plumbing"][-1] == {"observe": "Priya Shah"}
    assert engine["target"]["login"] == {"url": "/login", "user": "U", "password": "P"}
    assert engine["target"]["success"] == [{"name": "Invited", "type": "json", "url": "/api/invites",
                                            "where": {"email": "priya@x.example"}, "expect": {"projects": ["Lyra"]}}]
    assert any("/api/secret" in n for n in notes)
    assert problems(flow) == []
