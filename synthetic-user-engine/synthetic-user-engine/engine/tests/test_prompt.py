import json
import re

import pytest

from sue.model import LabelScriptModel
from sue.prompt import SYSTEM, ReplyError, build_turn, element_lines, parse_reply

ELEMENTS = [
    {"id": "el_1", "tag": "button", "role": "", "type": "", "text": "I'm finished", "original": "I'm finished",
     "value": None, "checked": None, "disabled": False, "expanded": None, "harness": True,
     "box": {"x": 1300, "y": 5, "w": 100, "h": 36}, "filled": True, "understanding": []},
    {"id": "el_2", "tag": "a", "role": "", "type": "", "text": "Budgets & caps", "original": "Budgets & caps",
     "value": None, "checked": None, "disabled": False, "expanded": None, "harness": False,
     "box": {"x": 10, "y": 570, "w": 200, "h": 30}, "filled": False, "understanding": []},
    {"id": "el_3", "tag": "input", "role": "", "type": "checkbox", "text": "Read-only for project users",
     "original": "Read-only for project users", "value": None, "checked": False, "disabled": False, "expanded": None,
     "harness": False, "box": {"x": 300, "y": 300, "w": 16, "h": 16}, "filled": False,
     "understanding": ["Read-only for project users (reads it as: Alerts go only to project users)"]},
]


def test_prompt_carries_no_identity_or_personality(cards):
    mikey = cards["mikey"]
    text = SYSTEM + build_turn(mikey, ELEMENTS, {"y": 0, "max": 400})
    assert mikey.name not in text
    for word in ("risk", "patience", "patient", "careful", "personality", "cautious", "tendency", "persona", "Mikey"):
        assert not re.search(rf"\b{word}\b", text, re.I), word
    assert mikey.task in text  # the task goes in word for word


def test_prompt_lists_knowledge_and_how_he_reads_each_element(cards):
    turn = build_turn(cards["mikey"], ELEMENTS, {"y": 0, "max": 0})
    assert "[T24]" in turn  # known: save before it takes effect
    assert "(vaguely remembered, not sure)" in turn  # vague items are written in the weakened form
    assert "reads it as: Alerts go only to project users" in turn
    assert "More content below: no" in turn
    assert element_lines(ELEMENTS)[2].startswith("el_3 | checkbox (not ticked)")


def test_reply_parsing():
    reply = {"candidates": [{"element": "el_2", "action": "click", "evidence": [], "why": "x"},
                            {"element": "el_2", "action": "teleport", "evidence": [], "why": "y"}]}
    out, observations = parse_reply(json.dumps(reply))
    assert [c["action"] for c in out] == ["click"] and observations == {}
    reply["observations"] = {"list_has_new_budget": {"answer": True, "quote": "Atlas"}}
    assert parse_reply(json.dumps(reply))[1]["list_has_new_budget"]["answer"] is True
    with pytest.raises(ReplyError):
        parse_reply("not json")
    with pytest.raises(ReplyError):
        parse_reply('{"nothing": 1}')


def _obs_parts(vocab, card, lines):
    hits = [h for t in lines for h in vocab(card).rewrite(t).hits]
    text = "\n".join(vocab(card).rewrite(t).text for t in lines)
    return hits, text


ROW = ["Atlas monthly", "Monthly", "Alerts only", "Atlas", "80%", "$523.40 / $1,000.00"]


def test_list_check_confirms_only_a_quote_he_can_read_on_the_list(cards, vocab):
    from sue.completion import check_list

    routes = ["/billing/budgets"]
    hits, text = _obs_parts(vocab, "full", ROW)
    seen = {"list_has_new_budget": {"answer": True, "quote": "Atlas monthly Monthly Alerts only Atlas 80%"}}
    assert check_list(cards["full"], seen, "/billing/budgets", hits, text, routes, "list_has_new_budget").done
    assert not check_list(cards["full"], seen, "/billing/budgets/create", hits, text, routes, "list_has_new_budget").done  # not the list
    made_up = {"list_has_new_budget": {"answer": True, "quote": "Atlas budget $1,000 monthly"}}
    assert check_list(cards["full"], made_up, "/billing/budgets", hits, text, routes, "list_has_new_budget").why == "the quote is not on screen"
    # The blank card sees fake words in the row, so it cannot recognise its own budget.
    bhits, btext = _obs_parts(vocab, "blank", ROW)
    bquote = "\n".join(vocab("blank").rewrite(t).text for t in ROW[:3]).replace("\n", " ")
    blank = {"list_has_new_budget": {"answer": True, "quote": bquote}}
    assert not check_list(cards["blank"], blank, "/billing/budgets", bhits, btext, routes, "list_has_new_budget").done


def test_label_script_prefers_an_exact_match_and_scrolls_when_missing():
    turn = "\n".join(element_lines(ELEMENTS) + ["el_9 | button | Finish"])
    m = LabelScriptModel([{"action": "click", "label": "Finish", "evidence": []}])
    assert json.loads(m.propose("", turn, b""))["candidates"][0]["element"] == "el_9"
    m = LabelScriptModel([{"action": "click", "label": "Next", "evidence": []}])
    assert json.loads(m.propose("", turn, b""))["candidates"] == []  # not in this piece: look elsewhere
    whole = turn + "\nThey are looking at: the whole screen"
    assert json.loads(m.propose("", whole, b""))["candidates"][0]["action"] == "scroll"
    assert m.script  # the step is kept for the next screen
