from sue.persona import EVERYDAY, KNOW, NONE, OTHER
from sue.words import fake


def test_fake_matches_the_workbench_export(cards):
    # Every word the blank card cannot read was faked by the workbench; the engine
    # must produce the very same fake word, or the screen and the card disagree.
    words = [w for w in cards["blank"].words if w.level == NONE]
    assert words
    for w in words:
        assert fake(w.original) == w.shown, w.original


def test_fake_keeps_length_case_and_separators():
    out = fake("Pub/Sub topic")
    assert len(out) == len("Pub/Sub topic")
    assert out[3] == "/" and out[7] == " "
    assert out[0].isupper() and out[4].isupper() and out[8].islower()
    assert fake("Budgets") == fake("Budgets")


def test_blank_card_fakes_items_and_offlist_words_but_not_data_or_harness(vocab):
    r = vocab("blank").rewrite("Budgets & caps for Atlas, then I'm finished")
    assert "Budgets & caps" not in r.text
    assert "Atlas" in r.text and "I'm finished" in r.text
    assert "for" not in r.text.split()  # off-list words are faked too on the blank card


def test_full_card_shows_everything_as_is(vocab):
    text = "Anomalies, FinOps hub and Budgets & caps"
    r = vocab("full").rewrite(text)
    assert r.text == text
    assert all(h.level == KNOW for h in r.hits)


def test_offlist_rule_keeps_common_words_and_fakes_the_rest(vocab):
    r = vocab("mikey").rewrite("Cost table")
    assert r.text == "Cost table"
    assert {h.level for h in r.hits} == {KNOW}  # off-list words have no special meaning: everyday meaning is the meaning
    r = vocab("mikey").rewrite("Anomalies")
    assert r.text == fake("Anomalies") and r.hits[0].level == NONE
    r = vocab("mikey").rewrite("FinOps hub")  # FinOps is forced fake; hub is not in the small list
    assert "FinOps" not in r.text and "hub" not in r.text


def test_plural_and_ing_forms_count_as_common(vocab):
    r = vocab("mikey").rewrite("Reports Pricing")
    assert r.text == "Reports Pricing"


def test_item_words_follow_the_card_and_take_the_case_on_screen(vocab):
    # Threshold is an item; on screen it appears in lower case.
    blank = vocab("blank").rewrite("Set alert threshold rules")
    expected = fake("Threshold").lower()
    assert expected in blank.text
    mikey = vocab("mikey").rewrite("Set alert threshold rules")
    assert "threshold" in mikey.text


def test_other_reading_keeps_the_text_and_carries_the_gloss(vocab):
    r = vocab("mikey").rewrite("Read-only for project users (single-project budgets only)")
    assert r.text.startswith("Read-only for project users")
    item = next(h for h in r.hits if h.source == "item")
    assert item.item_id == "T32" and item.level == OTHER
    assert "project users" in item.gloss


def test_longer_item_wins_over_a_shorter_one_inside_it(vocab):
    # "Billing account" is its own item; "Billing" inside it must not be matched separately.
    r = vocab("blank").rewrite("Billing account")
    ids = [h.item_id for h in r.hits if h.source == "item"]
    assert ids == ["T07"]


def test_word_limit_uses_the_test_result_before_the_english_level(config, cards):
    from dataclasses import replace

    from sue.words import common_word_limit

    mikey = cards["mikey"]
    assert common_word_limit(replace(mikey, vocab_size=None), config) == config["words"]["top_n"][mikey.english]
    assert common_word_limit(replace(mikey, vocab_size=17500), config) == 17500


def test_mikey_card_uses_his_tested_vocabulary_and_logs_ranks(config, cards):
    from sue.words import build_vocabulary

    v = build_vocabulary(cards["mikey"], config)
    assert v.common.limit == cards["mikey"].vocab_size == 28889
    hit = v.rewrite("Cancel").hits[0]
    assert hit.shown == "Cancel" and hit.level == KNOW  # was faked under the old 5000 limit
    deselect = v.rewrite("Deselect all").hits[0]
    assert deselect.shown == "Deselect" and deselect.level == KNOW  # rank 87,203, but an interface word
    assert hit.rank is not None and hit.rank < v.common.limit


def test_interface_words_are_known_except_on_the_blank_card(config, cards):
    from sue.words import build_vocabulary

    assert build_vocabulary(cards["blank"], config).rewrite("Deselect all").text != "Deselect all"


def test_emails_are_data(vocab):
    r = vocab("blank").rewrite("atlas-owner@example.test")
    assert r.text == "atlas-owner@example.test"
