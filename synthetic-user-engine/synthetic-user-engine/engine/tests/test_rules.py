from sue.choose import decide, score
from sue.evidence import HALF, SURE, VOID, check_evidence, check_item, check_word, quote_on_screen
from sue.memory import SessionMemory, action_key

WEIGHTS = {"area": 1.0, "top": 0.5, "filled": 2.0}
VIEW = (1440, 900)


def element(id, original, y=100, w=100, h=30, filled=False):
    return {"id": id, "original": original, "text": original, "box": {"x": 10, "y": y, "w": w, "h": h}, "filled": filled}


# ---- evidence -------------------------------------------------------------------

def test_item_evidence_follows_the_card(cards):
    mikey, memory = cards["mikey"], SessionMemory()
    assert check_item("T09", mikey, memory).level == SURE  # Budgets & caps: understands
    assert check_item("T23", mikey, memory).level == HALF  # billing admins: everyday meaning only
    assert check_item("T32", mikey, memory).level == HALF  # read-only: reads it as something else
    assert check_item("T18", mikey, memory).level == VOID  # alerts vs cap: none
    assert check_item("T26", mikey, memory).level == VOID  # a habit is never evidence
    assert check_item("T99", mikey, memory).level == VOID  # no such item


def test_learning_during_the_test_counts_as_knowing(cards):
    memory = SessionMemory()
    assert check_item("T18", cards["mikey"], memory).level == VOID
    assert memory.learn("T18", step=4) is True
    assert memory.learn("T18", step=6) is False
    assert check_item("T18", cards["mikey"], memory).level == SURE


def test_a_fake_word_is_void_and_a_kept_word_counts(vocab):
    hits = vocab("blank").rewrite("Budgets & caps for Atlas").hits
    fake_shown = next(h.shown for h in hits if h.item_id == "T09")
    assert check_word(fake_shown, hits).level == VOID
    assert check_word("Budgets & caps", hits).level == VOID  # not on his screen at all
    assert check_word("Atlas", hits).level == SURE  # data
    mikey_hits = vocab("mikey").rewrite("Budgets & caps").hits
    assert check_word("Budgets & caps", mikey_hits).level == SURE


def test_a_whole_element_label_counts_when_every_word_is_on_screen(vocab):
    # Seen in the first Gemini run: the model quotes the element's whole label, and
    # "Target amount" is one item, so its words never appear on screen on their own.
    screen = ["Target amount *", "Alerts only (available to all services)", "Atlas", "atlas-demo"]
    full = [h for t in screen for h in vocab("full").rewrite(t).hits]
    assert check_word("Target amount *", full).level == SURE
    assert check_word("Alerts only (available to all services)", full).level == SURE
    assert check_word("Atlas atlas-demo", full).level == SURE
    blank = [h for t in screen for h in vocab("blank").rewrite(t).hits]
    assert check_word("Target amount *", blank).level == VOID  # still void for the blank card
    mikey = [h for t in ["Read-only for project users"] for h in vocab("mikey").rewrite(t).hits]
    assert check_word("Read-only for project users", mikey).level == HALF  # he reads it another way


def test_word_evidence_must_be_on_the_element_acted_on(vocab):
    # Blank-card run, step 30: it pressed OK (seen as a fake word) citing "Atlas", which is
    # elsewhere on screen; step 40: it typed 80 into a field it could not read, citing "80%".
    screen = ["Atlas", "atlas-demo", "OK", "Percent of budget 1 *", "80%"]
    hits = [h for t in screen for h in vocab("blank").rewrite(t).hits]
    ok_seen = vocab("blank").rewrite("OK").text
    field_seen = vocab("blank").rewrite("Percent of budget 1 *").text
    assert check_word("Atlas", hits, on_element=ok_seen).level == VOID
    assert check_word("80%", hits, visible_text="80%", on_element=field_seen).level == VOID
    assert check_word("Atlas", hits, on_element="Atlas atlas-demo").level == SURE  # on the row itself
    assert check_word("Atlas", hits).level == SURE  # scroll and back still take evidence from anywhere


def test_numbers_count_only_when_on_screen():
    assert check_word("$ 1,000", [], visible_text="Target amount\n$ 1,000").level == SURE
    assert check_word("80", [], visible_text="Percent of budget 1 *\n80 %").level == SURE
    assert check_word("100", [], visible_text="Percent of budget 1 *\n80 %").level == VOID


def test_unknown_evidence_type_is_void(cards):
    verdicts = check_evidence([{"type": "vibes", "ref": "x"}], cards["mikey"], SessionMemory(), [])
    assert verdicts[0].level == VOID


def test_a_quote_must_really_be_on_screen():
    screen = "Atlas monthly   Monthly\nAlerts only  Atlas  80%"
    assert quote_on_screen("atlas monthly monthly", screen)
    assert not quote_on_screen("demo budget $100.00", screen)
    assert not quote_on_screen("", screen)


def test_action_key_ignores_case_and_spacing():
    assert action_key("/billing", " Reports ", "click", None) == action_key("/billing", "reports", "click", "")


def test_the_words_on_the_element_itself_always_count(vocab):
    from sue.evidence import own_words
    v = vocab("mikey")
    hits = v.rewrite("Cost table").hits  # common words in the test list
    own = own_words("Cost table", hits)
    assert own is not None and own.level == SURE
    blank = vocab("blank").rewrite("Cost table")
    assert own_words(blank.text, blank.hits) is None  # fake words: he cannot read the button


def test_a_button_is_read_by_its_main_name():
    from sue.evidence import own_words
    from sue.words import Hit
    hits = [Hit("Alerts only", "Alerts only", "understands", "item", "T28"),
            Hit("services", "services", "everyday", "item", "T12", "services in the general sense")]
    own = own_words("Alerts only (available to all services)", hits)
    assert own.level == SURE and own.ref == "Alerts only"
    faked = [Hit("Alerts only", "Bodeta kuna", "none", "item", "T28")]
    assert own_words("Bodeta kuna (available to all services)", faked) is None
