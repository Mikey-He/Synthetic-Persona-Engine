from types import SimpleNamespace

from sue.completion import asks_message, check_found, missing_confirmation
from sue.persona import KNOW
from sue.prompt import MESSAGE_KEY
from sue.words import Hit

SIGNALS = {"toast": False, "list": True, "external": False, "test": False}


def person(*ways):
    return SimpleNamespace(goal={"confirmBy": list(ways), "productSignals": SIGNALS})


def test_none_of_his_confirmations_exists_in_the_product():
    joy = person("toast", "test", "external")
    assert missing_confirmation(joy) == ["toast", "test", "external"]


def test_one_working_confirmation_is_enough():
    assert missing_confirmation(person("list", "external")) == []
    assert missing_confirmation(person("action")) == []


def test_the_success_message_is_asked_only_when_the_product_has_one():
    assert asks_message(SimpleNamespace(goal={"confirmBy": ["toast"], "productSignals": {"toast": True}}))
    assert not asks_message(SimpleNamespace(goal={"confirmBy": ["toast"], "productSignals": {"toast": False}}))
    assert not asks_message(SimpleNamespace(goal={"confirmBy": ["list"], "productSignals": {"toast": True}}))


def test_the_message_must_be_on_screen_and_readable():
    hit = Hit("Budget created successfully", "Budget created successfully", KNOW, "offlist")
    said = {MESSAGE_KEY: {"answer": True, "quote": "Budget created successfully"}}
    assert check_found(said, MESSAGE_KEY, [hit], "Budget created successfully", "the success message").done
    assert not check_found(said, MESSAGE_KEY, [hit], "Nothing here", "the success message").done
    assert not check_found({MESSAGE_KEY: {"answer": False}}, MESSAGE_KEY, [hit], "x", "the success message").done
