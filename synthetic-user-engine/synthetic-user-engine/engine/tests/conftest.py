import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from sue.config import load_config  # noqa: E402
from sue.persona import load_card  # noqa: E402
from sue.words import CommonWords, Vocabulary  # noqa: E402

# A small fixed word list, so the tests do not depend on wordfreq's ranking.
COMMON = CommonWords.from_words({
    "cost", "table", "report", "price", "only", "project", "budget", "single", "read", "for",
    "set", "alert", "rule", "the", "a", "of", "and", "management", "ok", "id", "account", "pub", "sub",
})


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def cards(config):
    return {name: load_card(config["paths"]["personas"], name) for name in ("mikey", "blank", "full")}


@pytest.fixture
def vocab(config, cards):
    def make(name):
        return Vocabulary(
            cards[name],
            COMMON,
            data_terms=config["words"]["data_terms"],
            harness_terms=[config["platform"]["harness_button_text"]],
            force_fake=config["words"]["force_fake"],
        )

    return make
