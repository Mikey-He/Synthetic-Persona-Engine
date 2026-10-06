from types import SimpleNamespace

from sue.completion import missing_confirmation

SIGNALS = {"toast": False, "list": True, "external": False, "test": False}


def person(*ways):
    return SimpleNamespace(goal={"confirmBy": list(ways), "productSignals": SIGNALS})


def test_none_of_his_confirmations_exists_in_the_product():
    joy = person("toast", "test", "external")
    assert missing_confirmation(joy) == ["toast", "test", "external"]


def test_one_working_confirmation_is_enough():
    assert missing_confirmation(person("list", "external")) == []
    assert missing_confirmation(person("action")) == []
