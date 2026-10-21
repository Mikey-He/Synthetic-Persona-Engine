"""The workflow lives in flow.json, not in the code or config.toml (sue/workflow.py)."""

import json

import pytest

from sue.config import load_config
from sue.prompt import list_key, list_question, response_schema
from sue.workflow import WorkflowError, problems

OLD_QUESTION = ("Also answer one question, in observations.list_has_new_budget: is there a list on this screen with a budget in it? "
                "answer is true or false. If true, quote copies that row's text exactly as they see it. Only what is on screen; do not guess.")


def test_version_a_settings_come_from_its_flow(config):
    assert config["workflow"]["created"] == "budget"
    assert config["goal"]["list_routes"] == ["/billing/budgets"] and config["goal"]["entry_items"] == ["T04"]
    assert config["run"]["consequential_labels"] == ["Finish", "Save", "Cancel"]
    assert "Atlas" in config["words"]["data_terms"] and config["words"]["force_fake"] == ["FinOps", "CUD"]
    assert config["workflow"]["plumbing"][-1] == {"observe": "Atlas monthly"}


def test_the_version_a_prompt_is_word_for_word_what_it_was():
    # PROMPT_VERSION did not change: the generic question renders Version A's text exactly.
    assert list_question("budget") == OLD_QUESTION
    assert list(response_schema("budget")["properties"]["observations"]["properties"]) == ["list_has_new_budget"]


def test_another_workflow_names_its_own_thing():
    assert list_key("Service account") == "list_has_new_service_account"
    assert "with an alert policy in it" in list_question("alert policy")
    assert "with a user in it" in list_question("user", "a")


def test_another_flow_file_drives_the_engine(config, tmp_path):
    flow = json.loads(config["paths"]["flow"].read_text(encoding="utf-8"))
    flow["name"] = "Permissions setup"
    flow["engine"] = {"created": "role binding", "routes": {"list": ["/iam"], "path": ["/iam", "/iam/new"]},
                      "labels": {"consequential": ["Grant"], "advancing": ["Continue"]}, "items": {"entry": ["T04"]},
                      "words": {"dataTerms": ["Priya Shah"]}}
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(flow), encoding="utf-8")
    other = load_config(flow=path)
    assert other["workflow"]["name"] == "Permissions setup" and other["workflow"]["created"] == "role binding"
    assert other["goal"]["path_routes"] == ["/iam", "/iam/new"] and other["goal"]["help_items"] == []
    assert other["run"]["consequential_labels"] == ["Grant"] and other["words"]["data_terms"] == ["Priya Shah"]


def test_a_flow_that_cannot_drive_the_engine_is_refused(config, tmp_path):
    flow = json.loads(config["paths"]["flow"].read_text(encoding="utf-8"))
    flow["engine"]["routes"]["list"] = ["/elsewhere"]
    flow["engine"]["items"]["help"] = ["T999"]
    del flow["engine"]["created"]
    found = problems(flow)
    assert any("routes.list" in p for p in found) and any("T999" in p for p in found) and any("created" in p for p in found)
    path = tmp_path / "flow.json"
    path.write_text(json.dumps(flow), encoding="utf-8")
    with pytest.raises(WorkflowError):
        load_config(flow=path)


def test_a_card_from_another_workflow_is_not_run_on_this_one(config, monkeypatch):
    from sue import run as run_module
    from sue.persona import load_card

    card = load_card(config["paths"]["personas"], "full")
    assert card.flow == config["workflow"]["name"]  # cards record the workflow they were built for
    monkeypatch.setitem(config["workflow"], "name", "Some other workflow")
    with pytest.raises(ValueError, match="was built for the workflow"):
        run_module.run("full", config, target=None, model=None)
