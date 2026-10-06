"""The choosing rules against the design table (engine-design.md 4.3)."""

from sue.choose import ABANDON, ACT, BACK, LOOK, Policy, decide, score
from sue.evidence import HALF, SURE, VOID, Verdict
from sue.memory import SessionMemory, action_key
from sue.prompt import CHECK, EXPLORE, FIX, RETREAT, TASK

CTX = "/billing|"


def el(id, original, y=100, w=100, h=30, filled=False, harness=False):
    return {"id": id, "original": original, "text": original, "box": {"x": 10, "y": y, "w": w, "h": h},
            "filled": filled, "harness": harness}


def cand(e, level, purpose=TASK, order=0, action="click", value=None):
    c = {"action": action, "element": e["id"] if e else None, "purpose": purpose, "value": value}
    return score(c, e, [Verdict("word", "x", level, "")] if level != VOID else [], CTX, order)


def policy(risk="medium", check="medium"):
    return Policy(risk=risk, check=check, consequential=["Finish", "Save"], advancing=["Next"])


def run(cands, risk="medium", check="medium", whole=False, piece=None, sim=None, helps=(), can_back=False, memory=None):
    piece = piece if piece is not None else [c.element for c in cands if c.element]
    return decide(cands, memory or SessionMemory(), policy(risk, check), context=CTX, whole_screen=whole, piece=piece,
                  sim=sim or (lambda e: 0), help_ids=set(helps), can_back=can_back)


# ---- confident moves --------------------------------------------------------------

def test_known_task_move_is_taken_and_finish_and_next_wait():
    finish, nxt, amount = el("f", "Finish", filled=True), el("n", "Next"), el("a", "Target amount *")
    d = run([cand(finish, SURE, order=0), cand(nxt, SURE, order=1), cand(amount, SURE, order=2, action="type")])
    assert d.kind == ACT and d.chosen.element["id"] == "a" and "wait" in d.rule


def test_model_order_breaks_ties_not_prominence():
    atlas, ok = el("atlas", "Atlas atlas-demo", w=16, h=16), el("ok", "OK", w=60, h=36, filled=True)
    d = run([cand(atlas, SURE, order=0), cand(ok, SURE, order=1)])
    assert d.chosen.element["id"] == "atlas"


def test_careful_checker_fixes_and_looks_before_moving_on():
    nxt, row, labels = el("n", "Next"), el("del", ""), el("l", "Labels")
    cands = [cand(nxt, SURE, order=0), cand(row, SURE, FIX, order=1), cand(labels, HALF, CHECK, order=2)]
    assert run(cands, check="high").chosen.element["id"] == "del"
    # a medium checker fixes too, but does not go looking into what he does not understand
    cands = [cand(nxt, SURE, order=0), cand(row, SURE, FIX, order=1), cand(labels, HALF, CHECK, order=2)]
    d = run(cands, check="medium")
    assert d.chosen.element["id"] == "del" and d.scored[2].dropped.startswith("Not a careful form checker")


def test_a_rough_checker_only_fixes_what_matches_the_task_literally():
    budget, savings = el("b", "Budget type"), el("s", "Savings")
    d = run([cand(savings, SURE, FIX, order=0), cand(budget, SURE, FIX, order=1)], check="low",
            sim=lambda e: 1 if e["id"] == "b" else 0)
    assert d.chosen.element["id"] == "b" and d.scored[0].dropped.startswith("Rough form checker")


def test_the_model_never_decides_to_finish():
    done, nav = el("done", "I'm finished", y=5, filled=True, harness=True), el("r", "Reports")
    d = run([cand(done, SURE), cand(nav, SURE, order=1)])
    assert d.scored[0].dropped.startswith("Code decides when they are done") and d.chosen.element["id"] == "r"


def test_tried_on_this_screen_is_dropped_and_retried_only_as_last_resort():
    a, b = el("a", "Reports"), el("b", "Cost table")
    memory = SessionMemory()
    memory.record(action_key(CTX, "Reports", "click", None), 1)
    d = run([cand(a, SURE, order=0), cand(b, SURE, order=1)], memory=memory)
    assert d.chosen.element["id"] == "b" and d.scored[0].dropped == "Already tried on this screen"
    memory.record(action_key(CTX, "Cost table", "click", None), 2)
    d = run([cand(a, SURE), cand(b, SURE, order=1)], memory=memory, whole=True, piece=[])
    assert d.kind == ACT and d.rule.startswith("Everything has been tried")


# ---- risk, when nothing in the piece is understood -----------------------------------

COST, REPORTS, BUDGETS = el("c", "Cost table", y=200), el("r", "Reports", y=170), el("b", "Budgets & caps", y=400)
ALIKE = {"c": 1, "b": 2}


def test_high_risk_clicks_the_most_alike_right_away():
    # The model listed Reports as a place to look; code finds Cost table more alike to the task.
    d = run([cand(REPORTS, SURE, EXPLORE)], risk="high", piece=[REPORTS, COST], sim=lambda e: ALIKE.get(e["id"], 0))
    assert d.kind == ACT and d.chosen.element["id"] == "c" and "clicks the most alike" in d.rule


def test_high_risk_clicks_half_understood_and_dares_a_half_understood_finish():
    finish = el("f", "Finish", filled=True)
    d = run([cand(finish, HALF)], risk="high")
    assert d.kind == ACT and d.chosen.element["id"] == "f"
    d = run([cand(finish, HALF)], risk="medium", whole=True)
    assert d.scored[0].dropped.startswith("Consequential action")


def test_medium_risk_looks_for_help_then_reads_on_then_clicks_the_most_alike():
    help_icon = el("h", "")
    d = run([cand(REPORTS, SURE, EXPLORE)], risk="medium", piece=[REPORTS, help_icon], helps=["h"])
    assert d.kind == ACT and d.chosen.candidate["action"] == "open_help"
    d = run([cand(REPORTS, SURE, EXPLORE)], risk="medium", piece=[REPORTS, COST], sim=lambda e: ALIKE.get(e["id"], 0))
    assert d.kind == LOOK  # not the whole screen yet: reads on
    d = run([cand(REPORTS, SURE, EXPLORE)], risk="medium", whole=True, piece=[REPORTS, COST], sim=lambda e: ALIKE.get(e["id"], 0))
    assert d.kind == ACT and d.chosen.element["id"] == "c" and "most alike" in d.rule


def test_nothing_alike_anywhere_falls_back_to_the_most_prominent():
    big = el("big", "Zivagu", w=400, h=60, filled=True)
    d = run([], risk="medium", whole=True, piece=[REPORTS, big])
    assert d.kind == ACT and d.chosen.element["id"] == "big" and "most prominent" in d.rule


def test_low_risk_reads_on_then_goes_back_or_gives_up():
    assert run([cand(REPORTS, HALF)], risk="low").kind == LOOK
    assert run([cand(REPORTS, HALF)], risk="low", whole=True, can_back=True).kind == BACK
    assert run([cand(REPORTS, HALF)], risk="low", whole=True).kind == ABANDON


def test_an_element_he_has_not_looked_at_stays_dropped():
    s = cand(BUDGETS, SURE)
    s.dropped = "They have not looked at this element yet (it is elsewhere)"
    d = run([s], risk="medium", piece=[REPORTS])
    assert d.kind == LOOK and d.scored[0].dropped.startswith("They have not looked")


# ---- 2026-10-04, after Mikey's run that toggled Atlas back and forth and pressed Cancel --------

def test_the_model_order_decides_not_its_purpose_label():
    # In the open Projects list, OK came first; unticking Atlas again was labelled a fix.
    ok, atlas = el("ok", "OK"), el("atlas", "Atlas atlas-demo")
    d = run([cand(ok, SURE, TASK, order=0), cand(atlas, SURE, FIX, order=1)], check="high")
    assert d.chosen.element["id"] == "ok"


def test_high_risk_does_a_half_understood_setting_before_next():
    alerts, nxt = el("a", "Alerts only (available to all services)"), el("n", "Next")
    d = run([cand(nxt, SURE, order=0), cand(alerts, HALF, FIX, order=1)], risk="high", check="high")
    assert d.chosen.element["id"] == "a" and d.rule.startswith("Only half-understood evidence")
    # a medium-risk person does not: Next is all he is sure of
    d = run([cand(nxt, SURE, order=0), cand(alerts, HALF, FIX, order=1)], risk="medium", check="high")
    assert d.chosen.element["id"] == "n"


def test_cancel_waits_like_finish():
    finish, cancel = el("f", "Finish", filled=True), el("c", "Cancel")
    d = run([cand(finish, SURE, order=0), cand(cancel, SURE, RETREAT, order=1)], risk="high", check="high")
    assert d.chosen.element["id"] == "f"


def test_a_page_with_only_back_on_it_is_read_to_the_end_first():
    back = el("back", "Back")
    for risk in ("high", "medium"):
        assert run([cand(back, SURE, RETREAT)], risk=risk, piece=[back]).kind == LOOK
    d = run([cand(back, SURE, RETREAT)], risk="medium", whole=True, piece=[back])
    assert d.kind == ACT and d.chosen.element["id"] == "back"


def test_closing_what_he_opened_is_done_right_away():
    close = el("x", "Close")
    close["region"] = {"kind": "popup"}
    d = run([cand(close, SURE, RETREAT)], risk="medium", piece=[close])
    assert d.kind == ACT and d.rule.startswith("Done looking")


def test_a_menu_item_that_led_off_the_route_is_not_clicked_again():
    memory = SessionMemory()
    memory.dead_end("Cost table", "/stub/cost-table")
    d = run([cand(COST, HALF, EXPLORE)], risk="high", piece=[COST, BUDGETS], sim=lambda e: ALIKE.get(e["id"], 0), memory=memory)
    assert d.scored[0].dropped.startswith("Last time it led off the route") and d.chosen.element["id"] == "b"


def test_code_never_ticks_a_box_as_its_own_most_alike_pick():
    box = dict(el("owners", "Email alerts to project owners"), tag="input", type="checkbox")
    d = run([], risk="high", piece=[box], sim=lambda e: 3)
    assert d.kind == LOOK


def test_somewhere_he_understands_ranks_below_what_is_most_alike():
    d = run([cand(REPORTS, SURE, EXPLORE)], risk="high", piece=[REPORTS], sim=lambda e: 0)
    assert d.chosen.element["id"] == "r" and d.rule.startswith("Nothing to do here")


def test_reviewing_what_he_saved_he_fixes_and_saves_but_tries_nothing_new():
    save, labels, reports = el("s", "Save", filled=True), el("l", "Labels"), el("r", "Reports")
    cands = [cand(labels, HALF, CHECK, order=0), cand(reports, SURE, EXPLORE, order=1), cand(save, SURE, order=2)]
    d = decide(cands, SessionMemory(), policy("high", "high"), context=CTX, whole_screen=False, piece=[save, labels, reports],
               reviewing=True)
    assert d.chosen.element["id"] == "s" and d.scored[0].dropped.startswith("Reviewing after saving")


def test_a_look_into_something_unclear_is_remembered_across_changed_values():
    labels = el("l", "Labels")
    c = {"action": "click", "element": "l", "purpose": CHECK}
    first = score(c, labels, [], "/create|scope|digest1", place="/create|scope")
    later = score(c, labels, [], "/create|actions|digest2", place="/create|actions")  # another section, same form
    assert first.key == later.key
    fix = {"action": "click", "element": "l", "purpose": FIX}
    assert score(fix, labels, [], "/create|scope|digest1", place="/create|scope").key != \
        score(fix, labels, [], "/create|scope|digest2", place="/create|scope").key


def test_with_nothing_to_go_on_code_picks_by_prominence_not_model_order():
    small, big = el("s", "Zupo", w=60, h=20), el("b", "Kavuto", w=300, h=48, filled=True)
    d = run([cand(small, VOID, EXPLORE, order=0), cand(big, VOID, EXPLORE, order=1)], risk="medium", whole=True,
            piece=[small, big])
    assert d.chosen.element["id"] == "b"


def test_a_switcher_in_the_page_frame_tried_once_is_tried_on_every_page():
    switch = dict(el("acct", "Northstar Research"), tag="button", expanded=False, region={"kind": "nav"})
    c = {"action": "click", "element": "acct", "purpose": EXPLORE}
    assert score(c, switch, [], "/billing||aaa").key == score(c, switch, [], "/stub/reports||bbb").key
    link = dict(el("b", "Budgets & caps"), tag="a", region={"kind": "nav"})
    c = {"action": "click", "element": "b", "purpose": TASK}
    assert score(c, link, [], "/billing||aaa").key != score(c, link, [], "/stub/reports||bbb").key


def test_he_can_put_back_what_he_tried_without_understanding_it():
    tag = el("t", "nap: prod")
    memory = SessionMemory()
    memory.touch("/create|scope", "nap: prod")  # he ticked it to see
    d = decide([cand(tag, VOID, FIX)], memory, policy("medium", "high"), context=CTX, whole_screen=False, piece=[tag],
               place="/create|scope")
    assert d.kind == ACT and d.rule.startswith("Puts back what they just tried")
    # something he never touched still needs understanding
    d = decide([cand(tag, VOID, FIX)], SessionMemory(), policy("medium", "high"), context=CTX, whole_screen=False, piece=[tag],
               place="/create|scope")
    assert d.kind == LOOK


def test_a_checker_scrolls_on_only_after_the_visible_part():
    labels = el("l", "Labels")
    d = run([cand(None, SURE, TASK, order=0, action="scroll", value="down"), cand(labels, HALF, CHECK, order=1)],
            check="high", piece=[labels])
    assert d.chosen.element["id"] == "l"


def test_an_unsure_checkbox_flipped_twice_is_left_alone():
    box = dict(el("ro", "Read-only for project users"), tag="input", type="checkbox")
    memory = SessionMemory()
    memory.flip("/create", "Read-only for project users")
    memory.flip("/create", "Read-only for project users")
    d = decide([cand(box, HALF, TASK)], memory, policy("high", "high"), context=CTX, whole_screen=False, piece=[box],
               page="/create")
    assert d.scored[0].dropped.startswith("Unsure of this checkbox")
    # one he understands is not limited
    d = decide([cand(box, SURE, TASK)], memory, policy("high", "high"), context=CTX, whole_screen=False, piece=[box],
               page="/create")
    assert d.kind == ACT


# ---- 2026-10-04, after Joy: menu groups that match the task, and looking for a confirmation ----

def test_lost_he_opens_a_matching_menu_group_top_down():
    nav = {"kind": "nav"}
    reports, table = dict(el("r", "Reports", y=170), tag="a", region=nav), dict(el("c", "Cost table", y=200), tag="a", region=nav)
    d = decide([], SessionMemory(), policy("medium"), context=CTX, whole_screen=False, piece=[table, reports], scent=True)
    assert d.kind == ACT and d.chosen.element["id"] == "r" and d.rule.startswith("Does not know where the entry is")
    memory = SessionMemory()
    memory.dead_end("Reports", "/stub/reports")
    d = decide([], memory, policy("medium"), context=CTX, whole_screen=False, piece=[table, reports], scent=True)
    assert d.chosen.element["id"] == "c"
    # without the scent a medium-risk person reads on
    assert decide([], SessionMemory(), policy("medium"), context=CTX, whole_screen=False, piece=[table, reports]).kind == LOOK


def test_saved_and_waiting_for_a_confirmation_he_changes_nothing():
    create, save = el("n", "+ Create new"), el("s", "Save", filled=True)
    menu = dict(el("a", "Anomalies", y=400), tag="a", region={"kind": "nav"})
    d = decide([cand(create, SURE, TASK), cand(save, SURE, TASK, order=1)], SessionMemory(), policy("medium"), context=CTX,
               whole_screen=True, piece=[create, save, menu], confirming=True, sim=lambda e: 1)
    assert d.scored[0].dropped.startswith("Already saved") and d.scored[1].dropped.startswith("Already saved")
    assert d.kind == ACT and d.chosen.element["id"] == "a"  # looks around the menus, never the form


# ---- 2026-10-04, after Aryan: a rough checker misses defaults he was not asked to change ----

def test_a_rough_checker_misses_a_default_tick_but_sets_what_the_task_asks():
    admins = dict(el("a", "Email alerts to billing admins and users"), tag="input", type="checkbox", checked=True)
    owners = dict(el("o", "Email alerts to project owners"), tag="input", type="checkbox", checked=False)
    cands = [cand(admins, SURE, FIX, order=0), cand(owners, SURE, TASK, order=1)]
    d = decide(cands, SessionMemory(), policy("medium", "low"), context=CTX, whole_screen=False, piece=[admins, owners],
               place="/create|actions", sim=lambda e: 1)
    assert d.scored[0].dropped.startswith("Missed default") and d.chosen.element["id"] == "o"
    # a medium checker notices it
    cands = [cand(admins, SURE, FIX, order=0), cand(owners, SURE, TASK, order=1)]
    d = decide(cands, SessionMemory(), policy("medium", "medium"), context=CTX, whole_screen=False, piece=[admins, owners],
               place="/create|actions", sim=lambda e: 1)
    assert d.chosen.element["id"] == "a"


def test_a_box_he_ticked_himself_is_not_a_default():
    box = dict(el("b", "Read-only for project users"), tag="input", type="checkbox", checked=True)
    memory = SessionMemory()
    memory.touch("/create|scope", "Read-only for project users")
    d = decide([cand(box, SURE, FIX)], memory, policy("medium", "low"), context=CTX, whole_screen=False, piece=[box],
               place="/create|scope", sim=lambda e: 1)
    assert d.kind == ACT


def test_a_rough_checker_still_types_the_amount_the_task_names():
    amount = el("t", "Target amount *")
    c = cand(amount, SURE, FIX, action="type", value="1000")
    d = decide([c], SessionMemory(), policy("medium", "low"), context=CTX, whole_screen=False, piece=[amount],
               sim=lambda e: 0, task_values={"1000", "80"})
    assert d.kind == ACT and d.chosen.element["id"] == "t"


def test_a_rough_checker_fills_an_empty_required_box():
    name = dict(el("n", "Name *"), tag="input", value="")
    d = decide([cand(name, SURE, FIX, action="type", value="Atlas")], SessionMemory(), policy("medium", "low"), context=CTX,
               whole_screen=False, piece=[name], sim=lambda e: 0, task_values={"1000"})
    assert d.kind == ACT and d.chosen.element["id"] == "n"


def test_code_does_not_refollow_a_link_already_clicked_here():
    # Mikey's card, English prompt: after Finish, back on the list, code's "most alike"
    # clicked + Create new again; he had already created the budget from there.
    create = el("c", "+ Create new")
    memory = SessionMemory()
    memory.touch("/billing/budgets|", "+ Create new")
    d = decide([], memory, policy("high"), context=CTX, whole_screen=False, piece=[create],
               sim=lambda e: 2, place="/billing/budgets|")
    assert d.kind == LOOK
    d = decide([], SessionMemory(), policy("high"), context=CTX, whole_screen=False, piece=[create],
               sim=lambda e: 2, place="/billing/budgets|")
    assert d.kind == ACT and d.chosen.element["id"] == "c"
