"""Chinese on screen: segmenting, fake Chinese words, and the Chinese level on the card."""

from dataclasses import replace

import pytest

from sue.evidence import HALF, SURE, VOID, check_word
from sue.persona import KNOW, NONE, OTHER, Word
from sue.words import CJK_CHAR, CommonWords, Vocabulary, build_vocabulary, fake, segment, tokens, unreadable_text

from conftest import COMMON

# A small fixed Chinese list, so the tests do not depend on wordfreq's ranking.
COMMON_ZH = CommonWords.from_words({"请", "输入", "项目", "名称", "然后"})
UI_ZH = ["确定", "取消", "下一步"]


def _vocab(config, persona, card_type, words=()):
    return Vocabulary(
        replace(persona, card_type=card_type, words=tuple(words)),
        COMMON,
        data_terms=config["words"]["data_terms"],
        harness_terms=[config["platform"]["harness_button_text"]],
        force_fake=config["words"]["force_fake"],
        ui_words=UI_ZH,
        common_zh=COMMON_ZH,
    )


def test_fake_chinese_is_deterministic_same_length_and_never_itself():
    for word in ["预算", "预算提醒", "设置", "账单账户", "确", "𠀀预算"]:
        out = fake(word)
        assert out == fake(word)
        assert len(out) == len(word)
        for a, b in zip(word, out):
            if CJK_CHAR.match(a):
                assert CJK_CHAR.match(b) and b != a
            else:
                assert a == b  # characters outside the two blocks stay as they are
    assert fake("预算") != fake("提醒")


def test_fake_keeps_punctuation_digits_and_english_output():
    out = fake("预算：12 个")
    assert out[2:6] == "：12 " and out[0] != "预"
    # Text without Chinese comes out exactly as before (values taken before Chinese support).
    assert fake("Pub/Sub topic") == "Nim/Gif nebud"
    assert fake("Budgets & caps") == "Gemadus & nepu"
    assert fake("Read-only (x) 12.5% É café") == "Zipu-suru (b) 12.5% É naké"


def test_tokens_split_mixed_english_and_chinese():
    assert tokens("设置预算提醒 for Cost table") == ["设置", "预算", "提醒", "for", "Cost", "table"]
    assert tokens("I'm 好") == ["I'm", "好"]
    assert "".join(segment("请输入项目名称")) == "请输入项目名称"


def test_unreadable_text_fakes_chinese_and_keeps_english_as_before():
    assert unreadable_text("Budget 12") == fake("Budget") + " ##"
    out = unreadable_text("预算 12")
    assert out[2:] == " ##" and not set(out[:2]) & set("预算")


def test_blank_card_fakes_every_chinese_word(config, cards):
    text = "请输入项目名称 Cost table 确定"
    r = _vocab(config, cards["mikey"], "blank").rewrite(text)
    assert len(r.text) == len(text)
    assert not any(ch in r.text for ch in "请输入项目名称确定")
    assert "Cost" not in r.text
    zh = [h for h in r.hits if CJK_CHAR.search(h.original)]
    assert zh and all(h.level == NONE and h.shown == fake(h.original) and h.source == "offlist" for h in zh)


def test_full_card_keeps_every_chinese_word(config, cards):
    text = "请输入项目名称，然后点击下一步。Anomalies 罕见词"
    r = _vocab(config, cards["mikey"], "full").rewrite(text)
    assert r.text == text
    assert all(h.level == KNOW for h in r.hits)


def test_normal_card_keeps_common_chinese_words_and_fakes_the_rest(config, cards):
    r = _vocab(config, cards["mikey"], "normal").rewrite("请输入项目名称，然后点击 Cost table")
    assert r.text.startswith("请输入项目名称，然后")
    assert "点击" not in r.text and r.text.endswith("Cost table")
    click = next(h for h in r.hits if h.original == "点击")
    assert click.level == NONE and click.shown == fake("点击") and click.source == "offlist"
    known = next(h for h in r.hits if h.original == "项目")
    assert known.level == KNOW and known.shown == "项目"


def test_chinese_interface_words_are_known_except_on_the_blank_card(config, cards):
    # 下一步 is cut into 下 + 一步 by the tokenizer; as an interface word it is found whole.
    r = _vocab(config, cards["mikey"], "normal").rewrite("点击下一步")
    assert r.text.endswith("下一步")
    assert any(h.original == "下一步" and h.level == KNOW for h in r.hits)
    assert "下一步" not in _vocab(config, cards["mikey"], "blank").rewrite("点击下一步").text


def test_chinese_item_words_match_inside_text_without_spaces(config, cards):
    item = Word("Z01", "预算", fake("预算"), NONE, "")
    other = Word("Z02", "账单账户", "账单账户", OTHER, "a bank account")
    v = _vocab(config, cards["mikey"], "normal", [item, other])
    r = v.rewrite("请输入预算金额并选择账单账户")
    assert fake("预算") in r.text and "账单账户" in r.text
    hits = {h.item_id: h for h in r.hits if h.source == "item"}
    assert hits["Z01"].original == "预算" and hits["Z01"].level == NONE
    assert hits["Z02"].level == OTHER and hits["Z02"].gloss == "a bank account"
    # The rest of the run around the items is still cut into words and judged.
    assert "金额" not in r.text  # not on the small list


def test_build_vocabulary_reads_the_chinese_level(config, cards):
    mikey = cards["mikey"]
    assert mikey.chinese == "native"  # no Chinese level on the card
    native = build_vocabulary(mikey, config)
    assert native.common_zh.limit == config["words"]["top_n_zh"]["native"]
    assert native.rewrite("请输入项目名称").text == "请输入项目名称"
    nobody = build_vocabulary(replace(mikey, chinese="none"), config)
    assert nobody.common_zh.limit == 0
    out = nobody.rewrite("请输入项目名称，然后点击确定").text
    assert out.endswith("确定")  # an interface word
    assert not any(ch in out[:-2] for ch in "请输入项目名称然后点击")


@pytest.mark.parametrize("card_type", ["normal", "blank"])
def test_evidence_checks_a_chinese_ref(config, cards, card_type):
    v = _vocab(config, cards["mikey"], card_type)
    screen = v.rewrite("项目名称 点击")
    shown_label = screen.text.split()[0]
    verdict = check_word(shown_label, screen.hits, screen.text)
    assert verdict.level == (SURE if card_type == "normal" else VOID)
    if card_type == "normal":
        # A ref mixing a known word and a fake one counts at its weakest word: void.
        assert check_word(screen.text, screen.hits, screen.text).level == VOID
        assert check_word("名称", screen.hits, screen.text, on_element=shown_label).level == SURE
        assert check_word("名称", screen.hits, screen.text, on_element=screen.text.split()[1]).level == VOID


def test_evidence_counts_a_chinese_item_with_another_reading_as_half(config, cards):
    other = Word("Z02", "账单账户", "账单账户", OTHER, "a bank account")
    v = _vocab(config, cards["mikey"], "normal", [other])
    screen = v.rewrite("账单账户")
    assert check_word("账单账户", screen.hits, screen.text).level == HALF


def test_english_evidence_is_unchanged(vocab):
    screen = vocab("mikey").rewrite("Cost table")
    assert check_word("Cost table", screen.hits, screen.text).level == SURE
    assert check_word("Cost", screen.hits, screen.text, on_element="Cost table").level == SURE
    assert check_word("Cost", screen.hits, screen.text, on_element="table").level == VOID
