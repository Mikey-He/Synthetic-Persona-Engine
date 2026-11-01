"""Steps 5 and 6: drop candidates, then pick one (engine-design.md 4.3).

What decides, in order:
1. Drop what he cannot or would not do: elements he has not looked at, the test's own
   I'm finished, consequential actions without enough understanding (risk), looking
   into unclear things when he is not a careful checker (detail when checking), links
   that already led him off the route, and actions already tried on this same screen.
2. What he would do right here, in the piece he is looking at: a task move or a fix he
   understands (half-understood is enough for high risk), a look into something unclear
   for a careful checker, closing what he just opened. The model's listing order
   decides among them, except that consequential actions (Finish, Cancel) and, for
   checkers, moving on (Next) wait until the rest is done.
3. Nothing to do right here: his risk tolerance decides, from the design table. high goes
   where he understands, then clicks the most alike right away (computed by code, sim).
   medium looks for help, reads on, and only after the whole screen goes elsewhere or clicks
   the half-understood, the most alike, or the most prominent. low reads on and then
   goes another way he understands, goes back, or gives up. Going back is the last
   thing anyone does: a page with only a Back link left on it is read to the end first."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from .evidence import HALF, SURE, VOID, Verdict, best_level
from .memory import SessionMemory, action_key, typed_value
from .prompt import CHECK, EXPLORE, FIX, RETREAT, TASK

NO_ELEMENT_ACTIONS = {"scroll", "back", "press"}

ACT, LOOK, BACK, ABANDON = "act", "look", "back", "abandon"

# An error event the study wants to see (engine-design.md 3.2, 5): a rough checker does
# what the task tells him and does not notice a default he was not asked to change.
MISSED_DEFAULT = "Missed default: a rough form checker does not notice a default they were not asked to change"


@dataclass
class Scored:
    candidate: dict[str, Any]
    element: dict[str, Any] | None
    verdicts: list[Verdict]
    level: str
    key: tuple
    order: int = 0  # place in the model's list
    dropped: str | None = None  # why it was removed, or None
    undo: bool = False  # puts back something he tried himself on this part of the page

    @property
    def purpose(self) -> str:
        return self.candidate.get("purpose") or TASK


@dataclass
class Decision:
    kind: str  # act / look / back / abandon
    chosen: Scored | None
    rule: str
    scored: list[Scored] = field(default_factory=list)


@dataclass
class Policy:
    """The person's tendencies as the choosing rules use them (engine-design.md 3.2)."""

    risk: str = "medium"
    check: str = "medium"  # detail when checking a form (D2, D3)
    consequential: list[str] = field(default_factory=list)  # Finish, Save, Cancel
    advancing: list[str] = field(default_factory=list)  # Next: moves on from a section
    weights: dict[str, float] = field(default_factory=lambda: {"area": 1.0, "top": 0.5, "filled": 2.0})
    viewport: tuple[int, int] = (1440, 900)
    # How they choose among what they would do (2026-11-01). None: the model's order, as a v2 card
    # always ran. Else how flat the draw is; rng draws it; memory_span and now make memory fade.
    spread: float | None = None
    rng: Any = None
    memory_span: float | None = None
    now: int = 0
    warned: bool = False  # the page shows them a warning they noticed: it is the reason to change something
    about_as_good: float = 3.0  # in a form, moves within this much hope of the best are taken in reading order
    change_floor: float = 5.0  # outside a form, less hope than this is not worth changing a value for


def prominence(element: dict[str, Any] | None, weights: dict[str, float], viewport: tuple[int, int]) -> float:
    """"Most prominent", computed by code: larger, higher up, and a filled primary button."""
    if not element:
        return 0.0
    w, h = viewport
    box = element["box"]
    area = (box["w"] * box["h"]) / (w * h)
    top = 1 - min(max(box["y"], 0), h) / h
    return weights["area"] * area * 100 + weights["top"] * top + (weights["filled"] if element.get("filled") else 0.0)


def is_consequential(element: dict[str, Any] | None, labels: list[str]) -> bool:
    if not element:
        return False
    text = (element.get("original") or element.get("text") or "").strip().lower()
    return text in {label.lower() for label in labels}


def leads_somewhere(element: dict[str, Any]) -> bool:
    """Links, buttons and dropdowns: what code may click on its own as "the most alike".
    Never a form value (checkbox, radio, option, text field): changing his answers is
    not a way of looking around."""
    tag, role, typ = element.get("tag", ""), element.get("role", ""), element.get("type", "")
    if tag in ("input", "select", "textarea") or role in ("checkbox", "radio", "option", "switch"):
        return False
    return typ not in ("checkbox", "radio")


def is_toggle(element: dict[str, Any] | None) -> bool:
    """A checkbox or switch: clicking it again undoes the click."""
    if not element:
        return False
    return element.get("type") == "checkbox" or element.get("role") in ("checkbox", "switch")


# One look before the final button, for someone who reads what is around them: real P002 and P006
# opened Preview. Once per form, and only a labelled button (2026-10-31).
ONE_LOOK = "Everything else is done; takes one look at a button they can read"
NOT_CAREFUL = "Not a careful form checker; does not look into unclear things"


def removes_default(element: dict[str, Any] | None, memory: SessionMemory, place: str | None) -> bool:
    """Unticking a box that was ticked when he got there, or deleting a row that was there:
    taking away a default. Something he ticked himself is not a default."""
    if not element:
        return False
    mine = place is not None and memory.has_touched(place, element.get("original"))
    if is_toggle(element) and element.get("checked") and not mine:
        return True
    # A row in the open form; a budget he saved, on the list, was never a default.
    in_form = place is None or bool((place.split("|") + [""])[1])
    return in_form and bool(re.match(r"(delete|remove)\b", (element.get("original") or "").strip(), re.I))


def hope_of(s: "Scored") -> float:
    """How hopeful the move looks to this person; a move the model gave no hope for counts as even."""
    return float(s.candidate.get("hope") if isinstance(s.candidate.get("hope"), (int, float)) else 5)


def draw(moves: list["Scored"], spread: float, rng) -> "Scored":
    """One move, with a chance that grows with how hopeful it looks to this person (a soft choice, as in
    SNIF-ACT). A small spread all but always takes the best; a large one makes several likely."""
    top = max(hope_of(s) for s in moves)
    weights = [math.exp((hope_of(s) - top) / spread) for s in moves]
    return rng.choices(moves, weights=weights)[0]


def next_in_form(moves: list["Scored"], about_as_good: float) -> "Scored":
    """In a form people go down the page: of the moves that look about as good, the first in reading
    order. All six people filled Scope top down; the hope of each field is only the model's guess."""
    top = max(hope_of(s) for s in moves)

    def place(s: "Scored") -> tuple[float, float]:
        box = (s.element or {}).get("box")
        return (box["y"], box["x"]) if box else (math.inf, math.inf)

    return min((s for s in moves if hope_of(s) >= top - about_as_good), key=place)


def is_loop(moves: list[tuple], repeats: int) -> bool:
    """The last moves go round: the same one, or a round of two or three, over at least repeats moves.
    Compared without the screen, since each round changes what is on it (2026-10-31)."""
    if len(moves) < repeats:
        return False
    last = moves[-repeats:]
    return any(all(last[i] == last[i - period] for i in range(period, repeats)) for period in (1, 2, 3))


def list_is_open(elements: list[dict[str, Any]]) -> bool:
    """A list to choose from is open, not just a section of the form: it holds what he ticks until he confirms it."""
    return any(e.get("expanded") is True and e.get("dropdown") for e in elements)


def in_popup(element: dict[str, Any] | None) -> bool:
    return bool(element) and (element.get("region") or {}).get("kind") == "popup"


def score(candidate: dict[str, Any], element: dict[str, Any] | None, verdicts: list[Verdict], context: str,
          order: int = 0, place: str | None = None) -> Scored:
    """context is the screen state as session memory sees it: the route, the open
    sections and every value on the page, so the same action counts as tried only on
    the same screen. Fixing a field and pressing Finish again is a new try.

    place is the route and open sections without the values. Looking into something
    unclear is remembered for the whole form, the route without its query (2026-10-04):
    once he has looked, neither changing a field nor opening another section makes him
    look again. Keyed by place, the English-prompt runs of Mikey's card clicked Define,
    Scope and Amount back and forth for some twenty steps, which he never did.

    Buttons in the frame around every page (menu, header) are remembered by where they
    are, not by page."""
    label = element.get("original") if element else None
    if label and candidate.get("purpose") == CHECK and element.get("expanded") is not None:
        label = " ".join(label.split()[:2])  # a section header goes on with its summary once closed: still the same one
    ctx = context
    if place is not None and candidate.get("purpose") == CHECK:
        parts = place.split("|")  # the route, the open sections and, in a product routed by fragment, the page
        ctx = parts[0].split("?")[0] + (f"#{parts[2]}" if len(parts) > 2 else "")
    chrome = (element or {}).get("region", {}).get("kind") if element else None
    if chrome in ("nav", "header", "aside") and element.get("tag") != "a":
        # A control in the frame around every page (the account switcher) is the same
        # control on every page: tried on one page, tried on all. Links are not: going to
        # Budgets & caps again after a detour is a new move.
        ctx = f"{chrome}|{element.get('expanded')}"
    key = action_key(ctx, label, str(candidate.get("action", "")), candidate.get("value"))
    return Scored(candidate, element, verdicts, best_level(verdicts) if verdicts else VOID, key, order)


def decide(
    scored: list[Scored],
    memory: SessionMemory,
    policy: Policy,
    *,
    context: str = "",
    whole_screen: bool = True,
    piece: list[dict[str, Any]] | None = None,
    sim: Callable[[dict[str, Any]], int] | None = None,
    help_ids: set[str] | None = None,
    can_back: bool = False,
    reviewing: bool = False,
    place: str | None = None,
    page: str | None = None,
    scent: bool = False,
    confirming: bool = False,
    task_values: set[str] | None = None,
) -> Decision:
    """piece: the elements he is looking at (the whole screen when whole_screen).
    sim(element): how alike the element is to the task, computed by code.
    help_ids: elements in the piece that are help icons he recognises.
    reviewing: he has saved and opened the saved one again to check it. He checks the
    values and fixes what is wrong, but no longer tries things out or looks elsewhere.
    place: the route and open sections. Something he tried out here (a look into an
    unclear checkbox) he may put back without understanding it: he remembers doing it.
    page: the route without its query. A checkbox he is not sure about and has already
    clicked twice on this form he leaves as it is.
    scent: the piece is a menu group whose heading matches the task, and he does not know
    where the entry is. With nothing to do here he opens its items one by one, top down.
    confirming: he has saved, and the confirmation he waits for does not exist in the
    product. He looks around the menus for it and changes nothing."""
    piece = piece or []
    sim = sim or (lambda e: 0)
    in_form = bool((place or "").split("|")[1:2] and place.split("|")[1])  # a section of the page is open
    help_ids = help_ids or set()
    cons = lambda s: is_consequential(s.element, policy.consequential)  # noqa: E731
    # Moving on: Next, or scrolling on past what he is looking at.
    adv = lambda s: is_consequential(s.element, policy.advancing) or s.candidate.get("action") == "scroll"  # noqa: E731
    alike = lambda s: sim(s.element) if s.element else 0  # noqa: E731
    dead = lambda e: bool(e) and memory.is_dead_end(e.get("original"))  # noqa: E731
    dares = (SURE, HALF) if policy.risk == "high" else (SURE,)
    # A dropdown he can read, not yet open: opening one changes nothing, so anyone may look (2026-10-31).
    # Not a section that folds: real people opened those at most once in a session.
    opens = lambda s: s.level == SURE and (s.element or {}).get("expanded") is False and bool((s.element or {}).get("dropdown"))  # noqa: E731
    # Typing a number the task names (1,000, 80) matches the task literally (2026-10-04).
    from .similarity import number
    names_value = lambda s: s.candidate.get("value") is not None and number(s.candidate.get("value")) in (task_values or set())  # noqa: E731
    # Typing the value the task names into a box he half understands (2026-10-08): the task
    # gives the value and the label's everyday meaning fits, so he types it. Before this, a
    # sure Next always beat it and the shared L1 card never filled in the amount.
    fills_named = lambda s: s.candidate.get("action") == "type" and s.level == HALF and names_value(s)  # noqa: E731

    # 1. Drop what he cannot or would not do.
    for s in scored:
        if s.dropped:  # already dropped by the caller, e.g. an element he has not looked at yet
            continue
        action = s.candidate.get("action")
        if s.element is None and action not in NO_ELEMENT_ACTIONS:
            s.dropped = "Element not on screen"
        elif (s.element or {}).get("harness"):
            s.dropped = "Code decides when they are done, by how they confirm; not the model"
        elif cons(s) and s.level not in dares:
            s.dropped = "Consequential action they are not sure of; not clicked"
        elif s.purpose == CHECK and policy.check != "high" and not opens(s):
            s.dropped = NOT_CAREFUL
        elif (s.purpose == CHECK and action == "click" and s.element
              and ((s.element.get("tag") in ("input", "textarea") and not is_toggle(s.element)) or s.element.get("expanded") is True)):
            s.dropped = "Clicking into it shows nothing new"
        elif (s.purpose == CHECK and page is not None and is_toggle(s.element)
              and memory.flipped(page, s.element.get("original")) >= 1):
            s.dropped = "Already set this box; flipping it to look would undo it"
        elif (page is not None and is_toggle(s.element) and memory.is_settled(page, s.element.get("original"), s.element.get("checked"))
              and not (s.purpose == FIX and memory.flipped(page, s.element.get("original")) < 3)):
            # No real person undid a box they had set without meaning to: the model only says "toggle it"
            # (2026-10-31). Saying it is wrong is another matter: people do correct their own slip (2026-11-01).
            s.dropped = "Set this box on purpose; leaves it"
        elif s.purpose == CHECK and action in ("choose", "type") and s.level not in dares:
            s.dropped = "Would change a value they are not sure of, only to look"
        elif policy.spread is not None and not in_form and action in ("choose", "type") and hope_of(s) < policy.change_floor:
            # Looking around is not filling things in: a run renamed the account and saved it, at hope 4.
            s.dropped = "Came to look; does not change anything on so little hope"
        elif (policy.check == "low" and s.candidate.get("action") == "click"
              and s.purpose in (TASK, FIX) and removes_default(s.element, memory, place)):
            s.dropped = MISSED_DEFAULT
        elif (s.purpose == FIX and policy.check == "low" and alike(s) == 0 and not names_value(s)
              and s.element is not None and not policy.warned
              and not (s.candidate.get("action") == "type" and not ((s.element or {}).get("value") or "").strip())):
            # (typing into an empty box is filling it in, not changing a default)
            s.dropped = "Rough form checker: changes only what literally matches the task"
        elif dead(s.element):
            s.dropped = "Last time it led off the route; remembered as a dead end"
        elif reviewing and s.purpose in (CHECK, EXPLORE):
            s.dropped = "Reviewing after saving: checks the values, tries nothing new"
        elif confirming and (s.purpose in (TASK, FIX, CHECK) or cons(s)):
            s.dropped = "Already saved and looking for a confirmation; changes no settings"
        elif (page is not None and is_toggle(s.element) and s.level != SURE
              and memory.flipped(page, s.element.get("original")) >= 2):
            s.dropped = "Unsure of this checkbox and already flipped it back and forth; leaves it"
    untried = [s for s in scored if s.dropped is None]
    retry = list(untried)
    for s in untried:
        if s.candidate.get("action") == "type" and s.element and page is not None:
            # What decides is what the box holds: a new empty form is filled in again, however alike
            # the screen, and a value he typed and replaced is not typed back (2026-10-31).
            holding, value = typed_value(s.element.get("value")), s.candidate.get("value")
            if not holding:
                continue
            if holding == typed_value(value):
                s.dropped = "The box already holds this"
            elif in_form and memory.has_typed(page, s.element.get("original"), value):  # a search box is searched again
                s.dropped = "Already typed this here and changed it"
            continue
        # Fading is about where he has been. In a form what he has done stays done, or the rest of it,
        # which the final button waits for, would never be over.
        if memory.still_remembers(s.key, policy.now, None if in_form else policy.memory_span, policy.rng):
            s.dropped = "Already tried on this screen"
    alive = [s for s in untried if s.dropped is None]
    for s in alive:
        if place is not None and s.purpose == FIX and s.element and s.candidate.get("action") == "click":
            s.undo = memory.has_touched(place, s.element.get("original"))

    def pick(s: Scored, rule: str) -> Decision:
        return Decision(ACT, s, rule, scored)

    # 2. What he would do right here.
    here = [s for s in alive
            if (s.purpose in (TASK, FIX) and (s.level in dares or s.undo or fills_named(s)))
            or (s.purpose == CHECK and (policy.check == "high" or opens(s)))
            or (s.purpose == RETREAT and s.level == SURE and in_popup(s.element))
            # Choosing by hope: where to go is what he is unsure of, so outside a form going to look elsewhere
            # competes with the task. In a form he works through it; he leaves only when nothing is left.
            or (policy.spread is not None and not in_form and s.purpose == EXPLORE and s.level in dares)]
    if here and policy.check == "medium" and page is not None and page not in memory.peeked and all(cons(s) for s in here):
        looks = [s for s in scored if s.dropped == NOT_CAREFUL and s.level == SURE and s.candidate.get("action") == "click"
                 and s.element and not s.element.get("icon") and s.element.get("expanded") is None
                 and leads_somewhere(s.element) and not memory.was_tried(s.key)]
        if looks:
            looks[0].dropped = None
            return pick(looks[0], ONE_LOOK)
    if here:
        careful = policy.check in ("medium", "high")

        def order(s: Scored) -> tuple:
            sure_move = s.purpose in (TASK, FIX) and s.level == SURE
            return (cons(s), careful and adv(s), s.purpose == RETREAT, not sure_move, s.order)

        here.sort(key=order)
        best = here[0]
        if policy.spread is not None and policy.rng is not None:
            # Still in turn: the final buttons last, a careful person's Next after the rest, closing after moving.
            turn = lambda s: order(s)[:3]  # noqa: E731
            in_turn = [s for s in here if turn(s) == turn(here[0])]
            best = next_in_form(in_turn, policy.about_as_good) if in_form else draw(in_turn, policy.spread, policy.rng)
            here.remove(best)
            here.insert(0, best)
        if best.purpose == CHECK:
            rule = "Careful form checker: opens what is unclear to look" if policy.check == "high" else "Opens a dropdown they can read, to look"
        elif best.undo and best.level not in dares:
            rule = "Puts back what they just tried (remembers touching it; no need to understand it)"
        elif best.purpose == EXPLORE:
            rule = "Not sure this is the way; tries somewhere else that looks promising"
        elif best.purpose == RETREAT:
            rule = "Done looking; closes what they just opened"
        elif fills_named(best) and best.level not in dares:
            rule = "Half-understood box, but the task names the value; types it"
        elif best.level != SURE:
            rule = "Only half-understood evidence; high risk tolerance clicks anyway"
        else:
            rule = "Understood evidence; changes it to what the task asks" if best.purpose == FIX else "Understood evidence; clicks"
        if len(here) > 1:
            waits = [w for w, test in (("consequential actions", cons), ("Next", adv)) if any(test(s) for s in here[1:])]
            rule += " (" + (" and ".join(waits) + " wait; " if waits else "") + "otherwise the model's order)"
        return pick(best, rule)

    # A menu group that smells of the task, and he does not know where the entry is:
    # he opens its items in reading order (engine-design.md 4.3, Joy and Mikey both did).
    if scent:
        pool = [e for e in piece if leads_somewhere(e) and not e.get("harness") and not dead(e)
                and not is_consequential(e, policy.consequential)
                and not memory.was_tried(score({"action": "click"}, e, [], context).key)]
        if pool:
            e = min(pool, key=lambda e: (e["box"]["y"], e["box"]["x"]))
            s = score({"action": "click", "element": e["id"], "purpose": EXPLORE,
                       "why": "This menu group's heading matches the task; opening its items one by one",
                       "evidence": []}, e, [], context, order=1000)
            scored.append(s)
            return pick(s, "Does not know where the entry is; opens the menu group that matches the task, item by item")

    # 3. Nothing to do right here: his risk tolerance decides.
    go = [s for s in alive if s.purpose == EXPLORE and s.level in dares]  # somewhere else he understands
    half = [s for s in alive if s.level == HALF and s.purpose in (TASK, FIX)]
    tried_here = {s.key for s in scored}
    own = []  # code's own picks: the links and buttons in the piece most alike to the task
    roam = lambda e: not confirming or (e.get("region") or {}).get("kind") in ("nav", "header", "aside")  # noqa: E731
    for e in [] if reviewing else [e for e in piece if roam(e)]:
        if e.get("harness") or is_consequential(e, policy.consequential) or not leads_somewhere(e) or dead(e):
            continue
        # Code's guess never re-follows a link he already clicked on this part of the page
        # (2026-10-04): after saving, "+ Create new" is alike to the task but already done.
        # The model's own candidates are not limited by this.
        if place is not None and memory.has_touched(place, e.get("original")):
            continue
        s = score({"action": "click", "element": e["id"], "purpose": EXPLORE, "why": "Code's pick: most alike to the task", "evidence": []},
                  e, [], context, order=1000)
        if alike(s) > 0 and s.key not in tried_here and not memory.was_tried(s.key):
            own.append(s)
            scored.append(s)
    likely = [s for s in alive if s.purpose in (TASK, FIX, EXPLORE) and alike(s) > 0 and s not in go] + own
    # Where to look elsewhere: what is most alike to the task first (code, by the words),
    # then what he understands, then the model's order.
    elsewhere = sorted(go + likely, key=lambda s: (-alike(s), s.level not in dares, s.order))
    # Going somewhere with nothing to go on: which one is code's call, by prominence, never
    # the model's order (it would bring in what the model knows about such pages).
    explore = sorted([s for s in alive if s.purpose == EXPLORE and s not in go],
                     key=lambda s: -prominence(s.element, policy.weights, policy.viewport))
    retreat = [s for s in alive if s.purpose == RETREAT and s.level == SURE]
    helps = [] if policy.risk == "high" else [
        e for e in piece if e["id"] in help_ids and not memory.was_tried(score({"action": "open_help"}, e, [], context).key)
    ]

    def help_decision() -> Decision:
        e = helps[0]
        s = score({"action": "open_help", "element": e["id"], "purpose": CHECK, "why": "Not sure; looks for help first", "evidence": []},
                  e, [], context, order=1000)
        scored.append(s)
        return pick(s, "Not sure; looks for help first")

    def most_prominent() -> Decision | None:
        pool = [e for e in piece if not e.get("harness") and not is_consequential(e, policy.consequential)
                and leads_somewhere(e) and not dead(e) and roam(e)]
        # Remembered the way score() remembers it, or a button in the frame is picked again and again.
        pool = [e for e in pool if not memory.was_tried(score({"action": "click"}, e, [], context).key)
                and not (place is not None and memory.has_touched(place, e.get("original")))]
        if not pool:
            return None
        e = max(pool, key=lambda e: prominence(e, policy.weights, policy.viewport))
        s = score({"action": "click", "element": e["id"], "purpose": EXPLORE, "why": "Nothing matches; the most prominent", "evidence": []},
                  e, [], context, order=1000)
        scored.append(s)
        return pick(s, "Nothing matches; picks the most prominent")

    def go_elsewhere(understood: str, alike_rule: str) -> Decision:
        s = elsewhere[0]
        return pick(s, alike_rule if alike(s) > 0 else understood)

    def back_out() -> Decision | None:
        return pick(retreat[0], "Read the whole screen and has nothing else to do; goes back") if retreat else None

    def last_resort() -> Decision:
        if retry:
            return Decision(ACT, retry[0], "Everything has been tried; tries again", scored)
        return Decision(ABANDON, None, "Read the whole screen; nothing to choose", scored)

    if policy.risk == "high":
        if elsewhere:
            return go_elsewhere("Nothing to do here; goes elsewhere they understand",
                                "Not sure; high risk tolerance clicks the most alike and comes back if wrong")
        if explore:
            return pick(explore[0], "Not sure; high risk tolerance clicks in to see and comes back if wrong")
        if not whole_screen:
            return Decision(LOOK, None, "Nothing to do in this piece", scored)
        return back_out() or most_prominent() or last_resort()

    if helps:
        return help_decision()
    if not whole_screen:
        return Decision(LOOK, None, "Nothing they are sure of in this piece; reads on", scored)

    if policy.risk == "medium":
        if half:
            return pick(half[0], "No help found; clicks the half-understood")
        if elsewhere:
            return go_elsewhere("Read the whole screen; goes elsewhere they understand", "No help found; clicks the most alike")
        if explore:
            return pick(explore[0], "No help found; clicks in to see")
        return back_out() or most_prominent() or last_resort()

    # low: does not click what he is unsure of; goes another way he understands, or back.
    if go:
        return pick(go[0], "Read the whole screen; takes another way they understand")
    if retreat:
        return pick(retreat[0], "Does not click what they are unsure of; goes back to try another way")
    if can_back:
        return Decision(BACK, None, "Does not click what they are unsure of; goes back to try another way", scored)
    return Decision(ABANDON, None, "Does not click what they are unsure of and has no other way; gives up", scored)
