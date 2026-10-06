from sue.completion import Check, review_link

ROW = {"id": "el_9", "text": "Atlas monthly", "kl": "T43"}
CREATE = {"id": "el_4", "text": "+ Create new", "kl": "T10"}


def test_a_careful_checker_opens_the_row_he_just_saw():
    check = Check(True, True, "in the list", True, "Atlas monthly  Monthly  Alerts only  Atlas  80%")
    assert review_link(check, [CREATE, ROW], ["T43"], lambda i: True) is ROW


def test_no_review_without_knowing_how_or_without_the_row():
    check = Check(True, True, "in the list", True, "Atlas monthly  Monthly")
    assert review_link(check, [ROW], ["T43"], lambda i: False) is None
    other = Check(True, True, "in the list", True, "Beacon quarterly")
    assert review_link(other, [ROW], ["T43"], lambda i: True) is None
    assert review_link(Check(True, False, "not on the list page"), [ROW], ["T43"], lambda i: True) is None
