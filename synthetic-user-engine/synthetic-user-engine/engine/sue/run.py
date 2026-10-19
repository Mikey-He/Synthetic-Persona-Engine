"""One run (engine-design.md 4, 8): one persona card, one Version A session.

Each step: he looks at the screen piece by piece (4.8) until there is something he would
do; code checks the model's candidates against his card and his tendencies (4.3) and
acts; session memory, patience (4.5) and the completion check (4.6) decide when he stops.
Perception (blur, misclicks, timing) comes in phase 3.

    python -m sue.run --card full --watch     # one window: his screen live on the left, the log on the right
    python -m sue.run --card blank            # no window, same files
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from datetime import datetime
from typing import Any

from playwright.sync_api import sync_playwright

from .attention import Attention
from .choose import ABANDON, ACT, BACK, LOOK, MISSED_DEFAULT, Decision, Policy, decide, is_consequential, is_toggle, score
from .completion import asks_list, check_list, missing_confirmation, review_link, stops_after_last_action, ways_text
from .config import load_config, load_env, platform_url, require_env
from .evidence import check_evidence, own_words
from .memory import SessionMemory
from .model import GeminiModel, Model, ModelError, timed
from .persona import ICON, KNOW, NONE, WORD, Persona, load_card
from .platform import ResearchConsole
from .prompt import CHECK, FIX, PROMPT_VERSION, SYSTEM, TASK, ReplyError, build_turn, parse_reply
from .runlog import RunLog
from .screen import RewriteError, Screen, open_browser
from .similarity import similarity, task_values, task_words
from .viewer import Dashboard, write_report
from .words import Vocabulary, build_vocabulary


def gray_icon_ids(persona: Persona, memory: SessionMemory) -> list[str]:
    """Icons he does not recognise are covered with a gray block (engine-design.md 4.1)."""
    return [i.id for i in persona.items.values() if i.kind == ICON and i.result == NONE and not memory.knows(i.id)]


def understood(vocab: Vocabulary, text: str) -> bool:
    """He understands a piece of help text when none of its words is a fake word to him."""
    return all(h.level != NONE for h in vocab.rewrite(text).hits)


def memory_known(persona: Persona, item_id: str) -> bool:
    """He knows the item from his card (understands) before the test starts."""
    item = persona.item(item_id)
    return bool(item and item.result == KNOW)


def scented(piece, vocab: Vocabulary, task: set[str]) -> bool:
    """The piece is a menu group whose heading, as he reads it, shares a word with the task."""
    if not piece or not piece.elements or piece.kind != "nav":
        return False
    heading = ((piece.elements[0].get("region") or {}).get("group") or {}).get("heading") or ""
    return bool(heading) and similarity({"original": heading, "harness": False}, vocab, task) > 0


def level_of(persona: Persona, *names: str) -> str:
    """The first tendency level the card has among names, else medium."""
    for name in names:
        value = persona.tendency.get(name)
        if isinstance(value, dict) and value.get("level"):
            return value["level"]
    return "medium"


def did(action: str, element: dict[str, Any] | None, value: Any) -> str:
    """What he did, in the words he saw, for the history the model gets."""
    text = (element or {}).get("text") or "an icon"
    return {
        "click": f'clicked "{text}"',
        "select": f'clicked "{text}"',
        "open_help": f'opened "{text}" to read the help',
        "type": f'typed {value} into "{text}"',
        "scroll": "scrolled up" if str(value).lower() == "up" else "scrolled down",
        "back": "went back to the previous page",
    }.get(action, action)


def scored_raw(candidates: list[dict[str, Any]], obs) -> list:
    """The model's candidates as they were, for the log, when code acted without them."""
    by_id = {e["id"]: e for e in obs.elements}
    return [score(c, by_id.get(c.get("element")), [], obs.signature, order=i) for i, c in enumerate(candidates)]


def _candidate_rows(scored) -> list[dict[str, Any]]:
    return [
        {
            "element": s.candidate.get("element"),
            "element_text": (s.element or {}).get("text"),
            "action": s.candidate.get("action"),
            "value": s.candidate.get("value"),
            "purpose": s.purpose,
            "why": s.candidate.get("why"),
            "evidence": [v.__dict__ for v in s.verdicts],
            "level": s.level,
            "dropped": s.dropped,
        }
        for s in scored
    ]


def run(card: str, config: dict[str, Any], console: ResearchConsole, model: Model, *, headed: bool = False,
        watch: bool = False, max_steps: int | None = None) -> dict[str, Any]:
    persona = load_card(config["paths"]["personas"], card)
    vocab = build_vocabulary(persona, config)
    platform, rules, goal = config["platform"], config["run"], config["goal"]
    max_steps = max_steps or rules["max_steps"]
    viewport = (platform["viewport_width"], platform["viewport_height"])

    # His tendencies, as the rules use them (engine-design.md 3.2).
    policy = Policy(
        risk=level_of(persona, "risk"),
        check=level_of(persona, "detailCheck", "detail"),
        consequential=rules["consequential_labels"],
        advancing=goal["advancing_labels"],
        weights=config["prominence"],
        viewport=viewport,
    )
    find = level_of(persona, "detailFind", "detail")
    patience = level_of(persona, "patience")
    patience_limit = config["patience"]["limit"].get(patience, 6)
    attention = Attention(config["attention"]["order"], viewport, by_group=find != "high")
    task_set = task_words(persona.task)
    task_nums = task_values(persona.task)
    help_items = set(goal["help_items"])
    # A careful checker who confirms by the list or detail page opens the saved one and
    # checks it once before he is done (engine-design.md 4.6).
    reviews = policy.check == "high" and asks_list(persona)
    # Not knowing where the entry is (the entry items are not understood), a person who dares to
    # click opens a menu group whose heading matches the task item by item (4.3).
    entry_items = goal.get("entry_items", [])
    lost = policy.risk != "low" and bool(entry_items) and not any(
        memory_known(persona, i) for i in entry_items)
    # Saved, but the confirmation he waits for is not in the product (4.6).
    missed = missing_confirmation(persona)
    let_go = persona.goal.get("ifConfirmMissing") == "let_go"

    session = console.create_session(
        model_id=model.model_id, prompt_version=PROMPT_VERSION, persona_id=f"{card}-{persona.id}", variant=platform["variant"]
    )
    log = RunLog(config["paths"]["runs"], card)
    started = time.monotonic()
    log.write_json("run.json", {
        "card": card, "persona": persona.name, "session": session.id, "model": model.model_id,
        "prompt_version": PROMPT_VERSION, "word_limit": vocab.common.limit,
        "tendency": {"risk": policy.risk, "detail_find": find, "detail_check": policy.check,
                     "patience": patience, "patience_limit": patience_limit},
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "config": config,
    })
    system = SYSTEM.format(max_candidates=config["model"]["max_candidates"])
    history_n = config["model"]["history_steps"]
    memory = SessionMemory()
    rules_used: Counter[str] = Counter()
    missed_defaults: list[dict[str, Any]] = []  # error events: defaults he did not notice (3.2, 5)
    seen_items: set[str] = set()
    marks: set[str] = set()
    last_keys: list[tuple] = []
    history: list[str] = []
    routes: list[str] = []  # pages he has been on, to know whether going back is possible
    wrong, backs = 0, 0  # patience: wrong pages and going back (engine-design.md 4.5)
    pending: dict[str, str] | None = None  # the last action, waiting to see what it changed
    actions = 0
    declare_now = False
    reviewing, reviewed = False, False
    revert: str | None = None  # a checkbox he ticked only to see what it does, to put back
    confirming, confirm_budget, confirm_used = False, 0, 0  # looking around for a confirmation that never comes
    stop: tuple[str, str] = ("step_limit", f"Reached {max_steps} actions")
    print(f"=== {card} ({persona.name}) session {session.id}, log in {log.dir}")
    print(f"    risk {policy.risk}, detail when finding {find}, detail when checking {policy.check}, "
          f"patience {patience} (limit {patience_limit})")

    with sync_playwright() as pw:
        # In watch mode the engine's own browser has no window: the dashboard streams it.
        browser, page = open_browser(pw, config, headless=not headed or watch)
        show = Dashboard(log.dir, pw, page, viewport) if watch else None
        screen = Screen(page, vocab, config, show=show, reveal_hover=policy.check in ("medium", "high"))
        say = show.phase if show else (lambda text: None)
        say("Opening the platform")
        page.goto(session.link)

        def post(step: int, shot: str, action: dict[str, Any], reason: str | None, executed: bool,
                 error: str | None, latency: int | None) -> None:
            console.record_step(session.id, {"stepNo": step, "screenshotPath": shot, "action": action, "reason": reason,
                                             "executed": executed, "errorLabel": error, "latencyMs": latency})

        def finish(step: int, obs, shot: str, button: dict[str, Any], rule: str, extra: dict[str, Any]) -> tuple[str, str]:
            """Code clicks I'm finished for him: the test ends the way it does for a person."""
            say(f"Step {step}: {rule}")
            note = screen.perform("click", button, None)
            rules_used[rule] += 1
            log.step({
                "step": step, "screenshot": shot, "route": obs.route, "signature": obs.signature,
                "at": datetime.now().strftime("%H:%M:%S"), "elapsed_s": round(time.monotonic() - started, 1),
                "rewrite_rounds": obs.rewrite_rounds, "gray_icons": obs.gray_icons,
                "state": {"learned_now": [], "learned": dict(memory.learned), "tried": len(memory.tried),
                          "wrong": wrong, "backs": backs},
                "candidates": [], "rule": rule,
                "action": {"type": "click", "element": button["id"], "text": button["text"], "original": button["original"],
                           "value": None, "note": note, "misclick": False, "box": button["box"]},
                "step_s": 0.0, **extra,
            })
            post(step, shot, {"action": "click", "element": button["id"], "box": button["box"], "rule": rule}, rule, True,
                 None, (extra.get("model") or {}).get("latency_ms"))
            print(f"  {step:>3} {obs.route}  click \"I'm finished\"  [{rule}]")
            return ("completion_declared", rule)

        step = 0
        while True:
            step += 1
            if actions >= max_steps or step > max_steps * 2:
                break
            if wrong + backs > patience_limit and not confirming:
                stop = ("abandoned", f"Out of patience: {wrong} wrong turns and {backs} backs, over their limit of {patience_limit}")
                break
            step_start = time.monotonic()
            looks: list[dict[str, Any]] = []
            first = True
            while True:  # he looks around the screen until there is something he would do
                say(f"Step {step}: reading the screen, swapping words they cannot read, covering what they have not looked at")
                try:
                    # Back on the list after a save, someone who confirms by the list looks at the
                    # whole list first, not piece by piece (2026-10-04).
                    saved_back = first and bool(pending and pending.get("consequential")) and asks_list(persona)
                    focus = ((lambda ctx, els: None if ctx.split("|")[0] in goal["list_routes"] else attention.focus(ctx, els))
                             if saved_back else attention.focus)
                    obs = screen.observe(step, gray_icon_ids(persona, memory), focus=focus)
                except RewriteError as error:
                    stop = ("technical_error", str(error))
                    break
                if first:
                    first = False
                    if pending:
                        moved_page = obs.route != pending["route"]
                        if moved_page and obs.route not in goal["path_routes"]:
                            wrong += 1
                            memory.dead_end(pending["label"], obs.route)
                        if pending.get("consequential") and missed and not confirming and obs.route in goal["list_routes"]:
                            # Saved and back on the list, and none of his confirmations exists here.
                            confirming, confirm_used = True, 0
                            confirm_budget = 0 if let_go else patience_limit
                            history.append("Saved and back on the list. The confirmation they wait for ("
                                           + ways_text(missed) + ") did not appear")
                        outcome = (f"the page changed to {obs.route}" + (" (off the route)" if obs.route not in goal["path_routes"] else "")
                                   if moved_page else "something on the page changed" if obs.signature != pending["signature"]
                                   else "nothing on the page changed")
                        history.append(f"{pending['did']} → {outcome}")
                        pending = None
                    if not routes or routes[-1] != obs.route:
                        routes.append(obs.route)
                shot = log.screenshot(step, obs.screenshot, f"_look{len(looks)}" if looks else "")
                marks |= set(page.evaluate("() => window.__sue.marks()"))
                for e in obs.elements:  # only clickable elements need a mark, not running text
                    if not e["harness"]:
                        seen_items |= {h.item_id for h in vocab.rewrite(e["original"]).hits if h.item_id}
                learned_now = [ex["item"] for ex in obs.explanations
                               if understood(vocab, ex["original"]) and memory.learn(ex["item"], step)]

                finish_button = next((e for e in obs.elements if e["harness"]
                                      and e["original"].strip() == platform["harness_button_text"]), None)
                if declare_now and finish_button:
                    # He stops right after the final consequential action (done once the last button is clicked).
                    stop = finish(step, obs, shot, finish_button, "Done once the last button is clicked; declares finished", {})
                    break

                if confirming and confirm_used >= confirm_budget and finish_button:
                    why = ("The confirmation did not come; they said they would let it go, so it counts as done" if let_go else
                           f"The confirmation they wait for ({ways_text(missed)}) is not in the product; "
                           f"looked for {confirm_used} steps without finding it, so treats it as done")
                    stop = finish(step, obs, shot, finish_button, why, {})
                    break

                if revert:
                    # He ticked a checkbox to see what it does; having seen, he puts it back.
                    target = next((e for e in obs.elements if not e["harness"] and is_toggle(e)
                                   and (e.get("original") or "").strip().lower() == revert), None)
                    revert = None
                    if target:
                        s = score({"action": "click", "element": target["id"], "purpose": FIX,
                                   "why": "Clicked it only to see what it does; putting it back", "evidence": []},
                                  target, [], obs.signature)
                        decision = Decision(ACT, s, "Tried it out; puts it back as it was", [s])
                        record = {
                            "step": step, "screenshot": shot, "route": obs.route, "signature": obs.signature,
                            "at": datetime.now().strftime("%H:%M:%S"), "elapsed_s": round(step_start - started, 1),
                            "rewrite_rounds": obs.rewrite_rounds, "gray_icons": obs.gray_icons,
                            "looking_at": obs.focus.describe() if obs.focus else None,
                            "focus_rect": obs.focus.rect if obs.focus else None,
                            "model": {"latency_ms": None, "attempts": 0, "error": None},
                            "state": {"learned_now": learned_now, "learned": dict(memory.learned), "tried": len(memory.tried),
                                      "wrong": wrong, "backs": backs},
                            "prompt": None, "looks": looks, "candidates": _candidate_rows([s]), "rule": decision.rule,
                            "completion": None,
                        }
                        break

                seen = obs.seen
                looking_at = obs.focus.describe() if obs.focus else None
                situation = ("They have saved, but the confirmation they wait for (" + ways_text(missed)
                             + ") has not appeared; they look around the page for it" if confirming else None)
                turn = build_turn(persona, seen, obs.scroll, ask_list=asks_list(persona),
                                  history=history[-history_n:], looking_at=looking_at, situation=situation)
                say(f"Step {step}: waiting for the model's candidates (looking at {looking_at or 'the whole screen'})")
                candidates, observations, error, latency, attempts = None, {}, None, None, 0
                detail = None  # the API's own message, so a credit or quota stop is not read as a timeout
                for attempts in range(1, config["model"]["retries"] + 2):
                    try:
                        text, latency = timed(model, system, turn, obs.screenshot)
                        candidates, observations = parse_reply(text)
                        break
                    except ModelError as e:
                        error, detail = e.label, str(e)[:300]
                    except ReplyError:
                        error = "invalid_json"
                record: dict[str, Any] = {
                    "step": step, "screenshot": shot, "route": obs.route, "signature": obs.signature,
                    "at": datetime.now().strftime("%H:%M:%S"), "elapsed_s": round(step_start - started, 1),
                    "rewrite_rounds": obs.rewrite_rounds, "gray_icons": obs.gray_icons,
                    "looking_at": looking_at, "focus_rect": obs.focus.rect if obs.focus else None,
                    "model": {"latency_ms": latency, "attempts": attempts, "error": error, "detail": detail if candidates is None else None},
                    "state": {"learned_now": learned_now, "learned": dict(memory.learned), "tried": len(memory.tried),
                              "wrong": wrong, "backs": backs},
                    "prompt": turn, "looks": looks,
                }
                if candidates is None:
                    record.update(rule="The model's reply was unusable and the retries ran out", candidates=[], action=None,
                                  step_s=round(time.monotonic() - step_start, 1))
                    log.step(record)
                    post(step, shot, {"action": "none"}, None, False, error, latency)
                    stop = ("technical_error", f"The model gave no usable reply {attempts} times in a row ({error}" + (f": {detail}" if detail else "") + ")")
                    break

                # Step 9 first: does what he sees confirm he is done, by his own way of confirming?
                check = check_list(persona, observations, obs.route, obs.hits, obs.visible_text, goal["list_routes"])
                completion = {"asked": check.asked, "answer": check.answer, "quote": check.quote, "done": check.done,
                              "why": check.why}
                knows = lambda i: memory.knows(i) or bool(persona.item(i) and persona.item(i).result == KNOW)  # noqa: E731
                link = review_link(check, obs.elements, goal["review_items"], knows) if reviews and not reviewed else None
                if link:
                    reviewing, reviewed = True, True
                    s = score({"action": "click", "element": link["id"], "purpose": TASK,
                               "why": "Saved; opens the one just made to check it field by field", "evidence": []},
                              link, [], obs.signature, order=0)
                    decision = Decision(ACT, s, "Careful form checker: it is in the list; opens it to check once more", [s])
                    record.update(candidates=_candidate_rows(scored_raw(candidates, obs)), rule=decision.rule,
                                  completion=completion)
                    break
                if check.done and finish_button:
                    stop = finish(step, obs, shot, finish_button, f"Confirmed done: {check.why}", {
                        "model": {"latency_ms": latency, "attempts": attempts, "error": None},
                        "prompt": turn, "completion": completion, "looking_at": looking_at, "looks": looks,
                        "candidates": _candidate_rows(scored_raw(candidates, obs)),
                    })
                    break

                say(f"Step {step}: code checks the evidence and picks by their tendencies")
                by_id = {e["id"]: e for e in obs.elements}
                seen_ids = {e["id"] for e in seen}
                scored = []
                for i, c in enumerate(candidates):
                    element = by_id.get(c.get("element"))
                    on_element = element["text"] if element and c.get("action") not in ("scroll", "back") else None
                    verdicts = check_evidence(c.get("evidence"), persona, memory, obs.hits, obs.visible_text, on_element)
                    if on_element and not element["harness"]:
                        own = own_words(on_element, obs.hits, obs.visible_text)
                        if own and not any(v.ref == own.ref and v.level == own.level for v in verdicts):
                            verdicts.append(own)
                    s = score(c, element, verdicts, obs.signature, order=i, place=obs.context)
                    if element and element["id"] not in seen_ids and not element["harness"]:
                        s.dropped = "They have not looked at this element yet (it is elsewhere)"
                    scored.append(s)
                known_help = {i for i in help_items if memory.knows(i) or (persona.item(i) and persona.item(i).result == KNOW)}
                decision = decide(
                    scored, memory, policy, context=obs.signature, whole_screen=obs.focus is None, piece=seen,
                    sim=lambda e: similarity(e, vocab, task_set), task_values=task_nums,
                    help_ids={e["id"] for e in seen if e.get("kl") in known_help},
                    can_back=len(routes) > 1,
                    reviewing=reviewing, place=obs.context, page=obs.route.split("?")[0],
                    scent=lost and not confirming and scented(obs.focus, vocab, task_set),
                    confirming=confirming,
                )
                record.update(candidates=_candidate_rows(scored), rule=decision.rule, completion=completion)
                for s in scored:
                    if s.dropped == MISSED_DEFAULT and s.element and not any(
                            m["original"] == s.element.get("original") for m in missed_defaults):
                        missed_defaults.append({"step": step, "route": obs.route, "text": s.element.get("text"),
                                                "original": s.element.get("original"), "why": s.candidate.get("why")})

                if decision.kind != LOOK:
                    break
                can_scroll = obs.scroll.get("y", 0) < obs.scroll.get("max", 0)
                moved = attention.advance(obs.context, obs.elements, can_scroll)
                if moved is None:
                    break
                what, note = moved
                if what == "scroll":
                    decision.kind, decision.rule = "scroll", f"Nothing to do in {looking_at or 'this piece'}; {note}"
                    record["rule"] = decision.rule
                    break
                looks.append({"looking_at": looking_at or "the whole screen", "screenshot": shot, "note": note,
                              "candidates": len(candidates), "focus_rect": record.get("focus_rect")})
                history.append(f"looked at {looking_at or 'the whole screen'}; nothing to do there")
                if len(looks) > 30:
                    break

            if stop[0] in ("technical_error", "completion_declared"):
                break
            if decision.kind == LOOK:  # looked everywhere he could; nothing left to look at
                decision.kind, decision.rule = ABANDON, "Looked everywhere; nothing to do"
            rules_used[decision.rule] += 1

            if decision.kind == ABANDON:
                record.update(action=None, step_s=round(time.monotonic() - step_start, 1))
                log.step(record)
                stop = ("abandoned", decision.rule)
                print(f"  {step:>3} {obs.route}  {decision.rule}; stops")
                break

            if decision.kind == "scroll":
                action, element, value, why = "scroll", None, "down", decision.rule
            elif decision.kind == BACK:
                action, element, value, why = "back", None, None, decision.rule
            else:
                chosen = decision.chosen
                element, action, value = chosen.element, chosen.candidate["action"], chosen.candidate.get("value")
                why = chosen.candidate.get("why")
                memory.record(chosen.key, step)
                if element and action == "click":
                    memory.touch(obs.context, element.get("original"))
                    if is_toggle(element):
                        memory.flip(obs.route.split("?")[0], element.get("original"))
                        # Put back only a box he had not touched before: a second click is itself the putting back.
                        if chosen.purpose == CHECK and memory.flipped(obs.route.split("?")[0], element.get("original")) == 1:
                            revert = (element.get("original") or "").strip().lower()
                last_keys.append(chosen.key)
            target = f' "{(element or {}).get("text", "")[:40]}"' if element else ""
            say(f"Step {step}: {decision.rule}; {action}{target}")
            try:
                note = screen.perform(action, element, value)
                executed, error = True, None
            except Exception as e:  # noqa: BLE001 - any browser failure ends the run as a technical error
                note, executed, error = f"Failed: {e}", False, "browser_error"
            actions += 1
            if action == "back" or (element and (element.get("original") or "").strip().lower() == "back"):
                backs += 1
                if len(routes) > 1:
                    routes.pop()
            pending = {"did": did(action, element, value), "route": obs.route, "signature": obs.signature,
                       "label": (element or {}).get("original"),
                       "consequential": is_consequential(element, rules["consequential_labels"])}
            if confirming:
                confirm_used += 1
            record["action"] = {
                "type": action, "element": (element or {}).get("id"), "text": (element or {}).get("text"),
                "original": (element or {}).get("original"), "value": value, "note": note, "misclick": False,
                "box": (element or {}).get("box"),
            }
            record["step_s"] = round(time.monotonic() - step_start, 1)
            log.step(record)
            post(step, record["screenshot"], {"action": action, "element": record["action"]["element"], "value": value,
                                              "box": (element or {}).get("box"), "rule": decision.rule},
                 why, executed, error, record["model"]["latency_ms"])
            seen_note = f" (looked at {len(looks)} piece{'s' if len(looks) > 1 else ''} first)" if looks else ""
            print(f"  {step:>3} {obs.route}  {action} {(element or {}).get('text', '')[:40]!r}  [{decision.rule}]{seen_note}"
                  + (f" learned {record['state']['learned_now']}" if record["state"]["learned_now"] else ""))

            if not executed:
                stop = ("technical_error", note)
                break
            declare_now = stops_after_last_action(persona) and is_consequential(element, rules["consequential_labels"])
            repeats = rules["loop_repeats"]
            if len(last_keys) >= repeats and len(set(last_keys[-repeats:])) == 1:
                stop = ("loop", f"Chose the same action {repeats} times in a row")
                break

        reason, why = stop
        if reason != "completion_declared":
            reason = console.end(session.id, reason)
        result = console.result(session.id)
        word_items = {i.id for i in persona.items.values() if i.kind in (WORD, ICON)}
        shots = sorted(p.name for p in log.dir.glob("step_*.png") if "_look" not in p.name)
        summary = {
            "card": card,
            "session": session.id,
            "steps": len(shots),
            "actions": actions,
            "wrong": wrong,
            "backs": backs,
            "stop": {"reason": reason, "why": why},
            "evaluation": result.get("evaluation"),
            "saves": result.get("saves"),
            "budgets": len(result.get("budgets") or []),
            "rules": dict(rules_used),
            "learned": dict(memory.learned),
            "missed_defaults": missed_defaults,
            # words and icons on clickable elements that carried no data-kl mark: fix the platform marks
            "unmarked_items": sorted((seen_items & word_items) - marks),
            "seconds": round(time.monotonic() - started, 1),
            "dir": str(log.dir),
            "files": [
                {"path": "report.html", "what": "The whole run as a report; open it in a browser. Same as the watch window"},
                {"path": "steps.jsonl", "what": "The full record, one line per step"},
                {"path": "summary.json", "what": "The result: why it stopped, the platform's grading, how often each rule fired"},
                {"path": "run.json", "what": "The card, their tendencies, the model, the prompt version and the whole config"},
                {"path": f"{shots[0]} to {shots[-1]}" if shots else "step_*.png",
                 "what": "What they saw at each step (words swapped, icons grayed, unread parts covered; "
                         "_look files are the pieces looked at first within a step)"},
            ],
        }
        log.write_json("summary.json", summary)
        log.close()
        report = write_report(log.dir)

        ev = summary["evaluation"] or {}
        print(f"\n=== Finished: {reason} ({why}); {actions} actions, {wrong} wrong turns, {backs} backs, {summary['seconds']} s")
        print(f"Platform grading: {'pass' if ev.get('overall') else 'fail'}  {ev.get('criteria')}")
        print(f"Rules used: {summary['rules']}")
        if missed_defaults:
            print("Missed defaults: " + "; ".join(f"step {m['step']} {m['original']}" for m in missed_defaults))
        if summary["unmarked_items"]:
            print(f"Items seen on screen that the platform did not mark: {summary['unmarked_items']}")
        print(f"Files are in {log.dir}")
        for f in summary["files"]:
            print(f"  {f['path']:<24} {f['what']}")
        if show:
            show.finish()
            print("\nClose the watch window to end. To see it again later, open report.html above.")
            show.wait_until_closed()
            show.close()
        browser.close()
    summary["report"] = str(report)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run of the synthetic user engine")
    parser.add_argument("--card", default="full", help="blank / full, or a card file name in data/personas (mikey, joy, ...)")
    parser.add_argument("--watch", action="store_true", help="one window: his screen live on the left, the log on the right")
    parser.add_argument("--headed", action="store_true", help="show the engine's browser only")
    parser.add_argument("--max-steps", type=int, help="most actions before stopping (looking around is not counted)")
    parser.add_argument("--viewport", help="window size, e.g. 1920x955; default from config.toml")
    parser.add_argument("--like-session", help="the person's session id: use the window size their session was taken in")
    args = parser.parse_args(argv)

    config = load_config()
    load_env()
    console = ResearchConsole(platform_url(config), require_env("ADMIN_PASSWORD"))
    # Each person takes the test in his own browser window; the engine looks through a
    # window of the same size (engine-design.md 7.5). The card is not touched.
    size = args.viewport
    if args.like_session:
        from .compare import window
        seen = window(console.events(args.like_session).get(args.like_session, []))
        if not seen or not seen.get("viewport"):
            print(f"Session {args.like_session} has no window size recorded", file=sys.stderr)
            return 1
        size = f"{seen['viewport']['width']}x{seen['viewport']['height']}"
        print(f"Running at the window of session {args.like_session}: {size}")
    if size:
        w, h = (int(x) for x in size.lower().split("x"))
        config["platform"]["viewport_width"], config["platform"]["viewport_height"] = w, h
    m = config["model"]
    model = GeminiModel(require_env("GEMINI_API_KEY"), m["id"], m["temperature"], m["timeout_s"])
    run(args.card, config, console, model, headed=args.headed, watch=args.watch, max_steps=args.max_steps)
    return 0


if __name__ == "__main__":
    sys.exit(main())
