"""One run of a card of format v3: the screen, the model's reading of it, and sue.mind's decision
(engine-design.md 4.10). Writes the same files as sue.run, so the study, the report and the platform
read it the same way. The model reads a screen once: its reply is kept by what it was shown, so another
path or seed over the same screens costs nothing, and all the variation between runs comes from code."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from .attention import chunks
from .choose import is_consequential, is_loop, leads_somewhere, prominence
from .completion import asks_list, asks_message, check_found, check_list, lacking_confirmation, save_refused, stops_after_last_action
from .evidence import VOID, best_level, check_evidence, own_words
from .memory import SessionMemory, typed_value
from .mind import Move, Outlook, appraise, scan, settle
from .model import Model, ModelError, timed
from .persona import Persona, load_card
from .prompt import EXPLORE, MESSAGE_KEY, OUTCOME_KEYS, ReplyError, build_turn, list_key, parse_reply, system as system_text
from .runlog import RunLog
from .screen import RewriteError, Screen, Strip, open_browser
from .similarity import similarity, task_words
from .target import Target
from .task import load_readings
from .variability import make, traits_of
from .viewer import Dashboard, LiveFeed, write_report
from .words import build_vocabulary

PROMPT_VERSION = "engine-p4-v2-en"
NOTE = ("\n\nGive low hope to what is already as the task needs it, and to going over what is plainly done. "
        "Say what the screen means, whatever they did before: what they did is kept elsewhere.")


class Remembered:
    """A model whose reading of a screen is kept on disk, by exactly what it was shown in words."""

    def __init__(self, model: Model, folder: Path):
        self.model, self.folder = model, Path(folder)
        self.model_id = model.model_id
        self.folder.mkdir(parents=True, exist_ok=True)
        self.calls, self.kept = 0, 0

    def propose(self, system: str, turn: str, screenshot: bytes) -> str:
        key = hashlib.sha256("\0".join((self.model_id, system, turn)).encode("utf-8")).hexdigest()
        path = self.folder / f"{key}.json"
        if path.exists():
            self.kept += 1
            return path.read_text(encoding="utf-8")
        text = self.model.propose(system, turn, screenshot)
        self.calls += 1
        json.loads(text)  # only a usable reply is kept
        scratch = path.with_suffix(f".{id(self)}.tmp")
        scratch.write_text(text, encoding="utf-8")
        scratch.replace(path)
        return text


def where(context: str) -> tuple[str, str, str]:
    """The route, the open sections and the page of a screen context, without its digest."""
    parts = (context.split("|") + ["", ""])[:3]
    return parts[0], parts[1], parts[2]


def move_key(context: str, element: dict[str, Any] | None, action: str, value: Any, stamp: str = "") -> tuple:
    """The same move: same place, same control, same thing done to it. Ticking and unticking differ."""
    label = ((element or {}).get("original") or "").strip().lower()
    return (*where(context), label, action, str(value or "").strip().lower(), (element or {}).get("checked"), stamp if action == "scroll" else "")


def looks_after(rng, careful: float, wants_more: bool, limit: int, chance: float) -> int:
    """How many moves they go on looking once it is saved: for as long as patience allows if the
    confirmation they want does not exist, otherwise a run of further looks that careful people prolong."""
    if wants_more:
        return limit
    n = 0
    while n < limit and rng.random() < chance * careful:
        n += 1
    return n


def run_session(card: str, config: dict[str, Any], target: Target, model: Model, *, headed: bool = False,
                watch: bool = False, max_steps: int | None = None, seed: int = 0, live: bool = False) -> dict[str, Any]:
    workflow = config["workflow"]
    persona: Persona = load_card(config["paths"]["personas"], card, workflow.get("file"))
    extras, aim = workflow.get("actions") or [], workflow.get("outcome") or {"kind": "change"}
    created, answer_key, found_key = workflow["created"], list_key(workflow["created"]), OUTCOME_KEYS.get(aim.get("kind"))
    by_list, by_message = asks_list(persona) and not found_key, asks_message(persona) and not found_key
    by_action, wants_more = stops_after_last_action(persona), bool(lacking_confirmation(persona))
    let_go = persona.goal.get("ifConfirmMissing") == "let_go"
    vocab = build_vocabulary(persona, config)
    platform, rules, goal, params = config["platform"], config["run"], config["goal"], config["mind"]
    max_steps = max_steps or rules["max_steps"]
    strip_h = Strip.HEIGHT if target.harness == "strip" else 0
    viewport = (platform["viewport_width"], platform["viewport_height"] - strip_h)
    traits = traits_of(persona.version, persona.tendency, persona.state, persona.perception)
    var = make(traits, config, seed)
    orientation = persona.orientation()
    task_set = task_words(persona.task)
    if hasattr(model, "client"):
        model = Remembered(model, Path(config["paths"]["runs"]) / "readings" / PROMPT_VERSION)

    session = target.start(model_id=model.model_id, prompt_version=PROMPT_VERSION, persona_id=f"{card}-{persona.id}")
    persona = dataclasses.replace(persona, task=target.substitute(persona.task))
    # How this person reads the task where it forks (sue/task.py): drawn per run, like a trait between two levels.
    readings = None
    if params.get("task_readings") and hasattr(model, "model") and hasattr(model.model, "client"):
        readings = load_readings(workflow["file"], persona.task, model.model.client, model.model_id)
    reading_now = readings.draw(var.rng) if readings else {}  # not `chosen`: that is the move picked each step
    started_with = readings.line(reading_now) if readings else None
    rethought: list[dict[str, Any]] = []
    if hasattr(model, "substitute"):
        model.substitute = target.substitute
    final_labels = [target.substitute(x) for x in rules["consequential_labels"]]
    commit = [target.substitute(x) for x in rules.get("commit_labels", final_labels)]
    path_pages = goal.get("path_pages")
    strip = Strip(persona.task, platform["harness_button_text"], platform["viewport_width"]) if strip_h else None
    log = RunLog(config["paths"]["runs"], card)
    started = time.monotonic()
    log.write_json("run.json", {
        "card": card, "persona": persona.name, "session": session.id, "model": model.model_id, "target": target.kind,
        "prompt_version": PROMPT_VERSION, "actions": extras, "outcome": aim, "word_limit": vocab.common.limit,
        "card_version": persona.version, "seed": seed, "traits": traits.as_dict(), "orientation": orientation, "task_reading": started_with,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "config": config,
    })
    system = system_text(config["model"]["max_candidates"], extras) + NOTE
    memory = SessionMemory()  # what they understood during the test
    tried: dict[tuple, int] = {}  # move -> the step it was last done
    cursor: dict[str, int] = {}  # screen part -> the piece they are on
    routes: list[str] = []
    last_keys: list[tuple] = []
    rules_used: Counter[str] = Counter()
    slips: Counter[str] = Counter()
    pending: dict[str, Any] | None = None
    wrong, backs, actions, off_path, step = 0, 0, 0, 0, 0
    around = 0  # moves made outside a form: they learn where things are
    read_before: set[tuple] = set()  # runs of words they have read: only what is new takes time
    saved, confirmed, after_used, after_budget = False, False, 0, 0
    reported: str | None = None
    stop = ("step_limit", f"Reached {max_steps} actions")
    print(f"=== {card} ({persona.name}) session {session.id}, log in {log.dir}\n    {traits.as_dict()}, orientation {orientation:.2f}, seed {seed}")

    with sync_playwright() as pw:
        browser, page = open_browser(pw, config, headless=not headed or watch, strip=strip, state=target.storage_state())
        show = Dashboard(log.dir, pw, page, viewport) if watch else LiveFeed(log.dir, page, viewport) if live else None
        screen = Screen(page, vocab, config, show=show, reveal_hover=traits.check >= 2.5, strip=strip)
        screen.color, screen.download_dir = traits.color, log.dir
        say = show.phase if show else (lambda text: None)
        say("Opening the product")
        target.prepare(page)
        page.goto(session.link)

        def outlook(context: str) -> Outlook:
            daring = max(0.0, (var.score("risk") - 5) / 5) * params["daring_weight"]
            unsure = max(0.0, min(1.0, (1 - orientation) + orientation * daring)) * math.exp(-around / params["orient_span"])
            return Outlook(var.score("risk"), var.score("detailFind"), var.score("detailCheck"), unsure, bool(where(context)[1]), saved, params)

        while actions < max_steps and step < max_steps * 2:
            step += 1
            var.setbacks = wrong + backs
            limit = var.patience_limit()
            if wrong + backs > limit and not saved:
                stop = ("abandoned", f"Out of patience: {wrong} wrong turns and {backs} backs, over their limit of {limit}")
                break
            screen.hide_warnings, screen.learned = not var.notices_warnings(), set(memory.learned)
            step_start = time.monotonic()
            just_committed = bool(pending and pending.get("commit"))
            whole_first = just_committed and (by_list or by_message)
            pool: list[Move] = []
            looks: list[dict[str, Any]] = []
            chosen, rule, obs, record, shot, pieces_seen = None, "", None, {}, "", 0
            ended = False
            while True:  # they read on, piece by piece, until something looks good enough
                state: dict[str, Any] = {}

                def focus(context, elements):
                    parts = chunks(elements, config["attention"]["order"], viewport, by_group=var.score("detailFind") < 7.5)
                    state["total"] = len(parts)
                    if whole_first and not looks:
                        state["total"] = 1
                        return None
                    if not parts:
                        return None
                    i = cursor.get(context, 0) % len(parts)
                    return parts[i]

                try:
                    obs = screen.observe(step, [], focus=focus)
                except RewriteError as error:
                    stop, ended = ("technical_error", str(error)), True
                    break
                if pending:
                    moved, new_page = obs.route != pending["route"], obs.page != pending["page"]
                    if moved or new_page:  # arriving somewhere, they read it from the top, however often they have been
                        cursor.pop(obs.context, None)
                    if new_page and path_pages is not None and obs.page not in path_pages:
                        off_path += 1
                    if moved and obs.route not in goal["path_routes"]:
                        wrong += 1
                    left_form = pending["in_form"] and not where(obs.context)[1]
                    refused = pending["commit"] and save_refused(bool(obs.warnings) and screen.has_control(pending["label"]), obs.warnings)
                    took = True
                    if pending["commit"]:
                        target.note_save(screen.page)
                        wrote = getattr(target, "last_saved", None)  # a web product's storage; None where the product is not watched
                        took = wrote is None or bool(wrote)
                    if left_form or refused:  # a new form is a new form; a refused save has a reason to go over it
                        tried = {k: v for k, v in tried.items() if not k[1]}
                    if pending["commit"] and not refused and took and not saved:
                        saved = True
                        after_budget = 0 if let_go else looks_after(var.rng, var.score("detailCheck") / 10, wants_more, limit, params["look_after"])
                    pending = None
                if not routes or routes[-1] != obs.route:
                    routes.append(obs.route)
                shot = log.screenshot(step, obs.screenshot, f"_look{len(looks)}" if looks else "")
                pieces_seen += 1
                learned_now = [ex["item"] for ex in obs.explanations
                               if all(h.level != "none" for h in vocab.rewrite(ex["original"]).hits) and memory.learn(ex["item"], step)]
                finish_button = next((e for e in obs.elements if e["harness"] and e["original"].strip() == platform["harness_button_text"]), None)
                seen = [e for e in (obs.focus.elements if obs.focus else obs.elements) if not e["harness"]]
                lapse = var.lapse(seen, lambda e: prominence(e, config["prominence"], viewport))
                if lapse:
                    seen = [e for e in seen if e is not lapse]
                    slips["lapses"] += 1
                looking_at = obs.focus.describe() if obs.focus else None
                if readings and not saved:  # the screen shows what an ambiguity turns on: they may think again
                    flipped = readings.rethink(var.rng, obs.product_text, where(obs.context)[1], var.score("detailCheck") / 10, reading_now)
                    if flipped:
                        rethought.append({"step": step, **flipped})
                        print(f"      thinks again about {flipped['about']}: now {flipped['now'][:70]}")
                turn = build_turn(persona, seen, obs.scroll, ask_list=by_list, extras=extras, outcome=aim, history=[], looking_at=looking_at,
                                  created=created, ask_message=by_message, learned=memory.learned, article=workflow.get("article"),
                                  reading=readings.line(reading_now) if readings else None)
                say(f"Step {step}: reading {looking_at or 'the whole screen'}")
                candidates, observations, error, latency, attempts, detail = None, {}, None, None, 0, None
                for attempts in range(1, config["model"]["retries"] + 2):
                    try:
                        text, latency = timed(model, system, turn, obs.screenshot)
                        candidates, observations = parse_reply(text)
                        break
                    except ModelError as e:
                        error, detail = e.label, str(e)[:300]
                        if error == "no_credits":
                            break
                    except (ReplyError, ValueError):
                        error = "invalid_json"
                record = {
                    "step": step, "screenshot": shot, "route": obs.route, "signature": obs.signature, "at": datetime.now().strftime("%H:%M:%S"),
                    "elapsed_s": round(step_start - started, 1), "rewrite_rounds": obs.rewrite_rounds, "gray_icons": obs.gray_icons, "looking_at": looking_at,
                    "focus_rect": obs.focus.rect if obs.focus else None, "model": {"latency_ms": latency, "attempts": attempts, "error": error, "detail": detail if candidates is None else None},
                    "state": {"learned_now": learned_now, "learned": dict(memory.learned), "tried": len(tried), "wrong": wrong, "backs": backs, "saved": saved},
                    "prompt": turn, "looks": looks, "words_seen": len(obs.product_text.split()),
                    "task_reading": readings.line(reading_now) if readings else None,
                }
                words = obs.product_text.split()
                runs_of_words = {tuple(words[i:i + 3]) for i in range(max(0, len(words) - 2))}
                record["words_new"] = len(runs_of_words - read_before)
                read_before |= runs_of_words
                if candidates is None:
                    record.update(rule="The model's reply was unusable and the retries ran out", candidates=[], action=None, step_s=round(time.monotonic() - step_start, 1))
                    log.step(record)
                    stop, ended = ("technical_error", f"The model gave no usable reply {attempts} times in a row ({error}" + (f": {detail}" if detail else "") + ")"), True
                    break

                # Do they see that it is done, in their own way of making sure?
                done_why = None
                if found_key:
                    check = check_found(observations, found_key, obs.hits, obs.product_text, "the answer" if aim["kind"] == "answer" else "the page the task asks for")
                    if check.done:
                        reported, done_why, confirmed, saved = check.quote, check.why, True, True
                elif saved and not confirmed:
                    if by_action or not (by_list or by_message):
                        confirmed, done_why = True, "Done once the last button is clicked" if by_action else "Saved; they have no other way of making sure"
                    elif by_message and whole_first and check_found(observations, MESSAGE_KEY, obs.hits, obs.product_text, "the success message").done:
                        confirmed, done_why = True, "They see the success message"
                    elif by_list and obs.route in goal["list_routes"] and check_list(persona, observations, obs.route, obs.hits, obs.product_text, goal["list_routes"], answer_key).done:
                        confirmed, done_why = True, "The list shows the one just made"
                if saved and finish_button and after_used >= after_budget and (confirmed or after_used >= limit):
                    rule = done_why or ("Looked around after seeing it saved; satisfied" if confirmed else "No confirmation came; treats it as done")
                    say(f"Step {step}: {rule}")
                    note = screen.perform("click", finish_button, None)
                    rules_used[rule] += 1
                    log.step({**record, "candidates": [], "rule": rule, "step_s": 0.0,
                              "action": {"type": "click", "element": finish_button["id"], "text": finish_button["text"], "original": finish_button["original"], "value": None,
                                         "note": note, "misclick": False, "box": finish_button["box"]}})
                    stop, ended = ("completion_declared", rule), True
                    break

                # What can they do here, and how does it look to them?
                o = outlook(obs.context)
                by_id = {e["id"]: e for e in obs.elements}
                ids = {e["id"] for e in seen}
                moves: list[Move] = []
                for c in candidates:
                    e = by_id.get(c.get("element"))
                    text = e["text"] if e and c.get("action") not in ("scroll", "back") else None
                    named = text and " ".join([text, *(e.get("options") or [])])
                    verdicts = check_evidence(c.get("evidence"), persona, memory, obs.hits, obs.visible_text, named or text)
                    if text and not e["harness"]:
                        own = own_words(text, obs.hits, obs.visible_text, memory.learned)
                        if own:
                            verdicts = [*verdicts, own]
                    m = Move(c, e, best_level(verdicts) if verdicts else VOID, move_key(obs.context, e, str(c.get("action")), c.get("value"), obs.scroll_stamp), verdicts,
                             final=is_consequential(e, final_labels), alike=similarity(e, vocab, task_set) if e else 0)
                    if c.get("action") not in ("scroll", "back", "press") and e is None:
                        m.dropped = "Element not on screen"
                    elif e and e["harness"]:
                        m.dropped = "Code decides when they are done; not the model"
                    elif e and e["id"] not in ids:
                        m.dropped = "They have not looked at this element yet"
                    elif c.get("action") == "type" and e and typed_value(e.get("value")) and typed_value(e.get("value")) == typed_value(c.get("value")):
                        m.dropped = "The box already holds this"
                    moves.append(m)
                listed = {c.get("element") for c in candidates}
                for e in seen:  # a link whose words match the task can catch the eye though the model left it out (rule 8)
                    if e["id"] not in listed and leads_somewhere(e):
                        alike = similarity(e, vocab, task_set)
                        if alike:
                            moves.append(Move({"action": "click", "element": e["id"], "purpose": EXPLORE, "evidence": [], "why": "Its words match the task"}, e, VOID,
                                              move_key(obs.context, e, "click", None), [], final=is_consequential(e, final_labels), alike=alike))
                live_moves = [m for m in moves if not m.dropped]
                for m in live_moves:
                    appraise(m, o, tried.get(m.key), step)
                pool += live_moves
                record["candidates"] = [{"element": m.candidate.get("element"), "element_text": (m.element or {}).get("text"), "action": m.action, "value": m.candidate.get("value"),
                                         "purpose": m.purpose, "hope": m.candidate.get("hope"), "why": m.candidate.get("why"), "evidence": [v.__dict__ for v in m.verdicts], "level": m.level,
                                         "dropped": m.dropped, "terms": m.terms, "worth": round(m.value, 2), "chance": round(m.chance, 3)} for m in moves]
                chosen = scan(live_moves, var.rng)
                if chosen:
                    rule = f"Good enough: worth {chosen.value:.1f} against wanting {o.aspiration:.1f}; takes the first such down the page"
                    break
                total = state.get("total", 1)
                if pieces_seen >= total:
                    break
                looks.append({"looking_at": looking_at or "the whole screen", "screenshot": shot, "note": "nothing good enough here; reads on",
                              "candidates": len(candidates), "focus_rect": record.get("focus_rect")})
                cursor[obs.context] = cursor.get(obs.context, 0) + 1

            if ended:
                break
            var.read(pieces_seen)
            if obs.unnoticed:
                slips["unnoticed_warnings"] += 1
            if not chosen:
                # Read everything: the best of what they have in mind, or reading further down, or back.
                o = outlook(obs.context)
                can_scroll = obs.scroll.get("y", 0) < obs.scroll.get("max", 0)
                down = Move({"action": "scroll", "value": "down", "purpose": "advance", "evidence": [], "hope": params["read_on_hope"], "why": "There is more below"}, None, "sure",
                            move_key(obs.context, None, "scroll", "down", obs.scroll_stamp), [])
                if can_scroll and not any(m.action == "scroll" for m in pool):
                    appraise(down, o, tried.get(down.key), step)
                    pool.append(down)
                chosen = settle(pool, o, var.rng)
                rule = f"Read everything; nothing good enough, so takes what looks best to them (worth {chosen.value:.1f})" if chosen else ""
            if not chosen:
                if len(routes) > 1 and "back" not in {k[4] for k in last_keys[-1:]}:
                    chosen = Move({"action": "back", "purpose": "retreat", "evidence": [], "why": "Nothing to do here"}, None, "sure", move_key(obs.context, None, "back", None), [])
                    rule = "Nothing here is worth doing; goes back"
                elif saved:  # it is done and there is nothing more to look at: they are done
                    confirmed, after_budget, after_used = True, 0, 0
                    continue
                else:
                    record.update(action=None, rule="Nothing here is worth doing; gives up", step_s=round(time.monotonic() - step_start, 1), variability=var.take_log())
                    log.step(record)
                    stop = ("abandoned", record["rule"])
                    break

            element, action, value = chosen.element, chosen.action, chosen.candidate.get("value")
            miss = var.miss_offset(element) if action in ("click", "select") else None
            if miss and screen.lands_on_it(element, miss):
                miss = None
            if miss:
                slips["misclicks"] += 1
            rules_used[rule.split(":")[0].split(" (")[0]] += 1
            record["rule"] = rule
            if not miss:
                tried[chosen.key] = step
                last_keys.append(chosen.key[3:6])
            rect = obs.focus.rect if obs.focus else None
            say(f"Step {step}: {rule}; {action}")
            try:
                drop = {e["id"]: e for e in obs.elements}.get(value) if action == "drag" else value
                wheel = ((rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2) if rect else (viewport[0] / 2, viewport[1] / 2)) if action == "scroll" else None
                note, executed, error = screen.perform(action, element, drop, miss=miss, at=wheel), True, None
            except Exception as e:  # noqa: BLE001 - any browser failure ends the run as a technical error
                note, executed, error = f"Failed: {e}", False, "browser_error"
            actions += 1
            around += not where(obs.context)[1]
            if saved:
                after_used += 1
            if action == "back" and len(routes) > 1:
                backs += 1
                routes.pop()
            if action == "scroll":
                cursor[obs.context] = 0
            pending = {"route": obs.route, "page": obs.page, "label": (element or {}).get("original"), "commit": is_consequential(element, commit), "in_form": bool(where(obs.context)[1])}
            record["action"] = {"type": action, "element": (element or {}).get("id"), "text": (element or {}).get("text"), "original": (element or {}).get("original"), "value": value,
                                "note": note, "misclick": bool(miss), "box": (element or {}).get("box"), "aria": (element or {}).get("aria"), "tag": (element or {}).get("tag")}
            record["step_s"] = round(time.monotonic() - step_start, 1)
            record["variability"] = var.take_log()
            log.step(record)
            target.record_step(session.id, {"stepNo": step, "screenshotPath": record["screenshot"], "action": {"action": action, "element": record["action"]["element"], "value": value,
                               "box": (element or {}).get("box"), "rule": rule}, "reason": chosen.candidate.get("why"), "executed": executed, "errorLabel": error, "latencyMs": record["model"]["latency_ms"]})
            print(f"  {step:>3} {action} {str((element or {}).get('text', ''))[:40]!r} hope {chosen.candidate.get('hope')} [{rule[:70]}]" + (f" read {pieces_seen}" if pieces_seen > 1 else ""))
            if not executed:
                stop = ("technical_error", note)
                break
            if is_loop(last_keys, rules["loop_repeats"]):
                stop = ("loop", f"Went round the same actions for {rules['loop_repeats']} moves")
                break

        reason, why = stop
        if reason != "completion_declared":
            reason = target.end(session.id, reason)
        page = screen.page
        result = target.result(session.id, page, {"answer": reported, "downloads": list(screen.downloads)})
        ignored = set(workflow.get("ignored_checks") or [])
        ev = result.get("evaluation") or {}
        if ignored and ev.get("criteria"):
            counted = [v for k, v in ev["criteria"].items() if k not in ignored]
            ev["ignored"], ev["overall"] = sorted(ignored), bool(counted) and all(counted)
        try:
            target.cleanup(page)
            cleanup_error = None
        except Exception as error:  # noqa: BLE001 - the run's result stands
            cleanup_error = str(error)
        shots = sorted(p.name for p in log.dir.glob("step_*.png") if "_look" not in p.name)
        summary = {
            "card": card, "session": session.id, "steps": len(shots), "actions": actions, "wrong": wrong, "backs": backs, "stop": {"reason": reason, "why": why},
            "evaluation": result.get("evaluation"), "saves": result.get("saves"),
            "saved_items": len(result.get("saved") or result.get("budgets") or next((v for v in (result.get("stored") or {}).values() if isinstance(v, list)), [])),
            "off_path_pages": off_path, "stored": result.get("stored"), "last_saved": result.get("last_saved"), "orientation": round(orientation, 2), "draws": var.rng.draws,
            "rules": dict(rules_used), "learned": dict(memory.learned), "missed_defaults": [], "seed": seed, "slips": dict(slips), "reported": reported, "downloads": list(screen.downloads),
            "task_readings": {"start": started_with, "end": readings.line(reading_now) if readings else None, "changes": rethought},
            "cleanup_error": cleanup_error, "unmarked_items": [], "marks": {"not_found": [], "several": [], "loose": [], "by_item": {}}, "target": target.kind,
            "model_calls": getattr(model, "calls", None), "readings_kept": getattr(model, "kept", None), "seconds": round(time.monotonic() - started, 1), "dir": str(log.dir),
            "files": [{"path": "report.html", "what": "The whole run as a report"}, {"path": "steps.jsonl", "what": "The full record, one line per step"},
                      {"path": "summary.json", "what": "The result"}, {"path": "run.json", "what": "The card, its traits, the model and the config"}],
        }
        log.write_json("summary.json", summary)
        log.close()
        report = write_report(log.dir)
        ev = summary["evaluation"] or {}
        print(f"\n=== Finished: {reason} ({why}); {actions} actions, {summary['seconds']} s, model calls {summary['model_calls']}, kept {summary['readings_kept']}")
        print(f"Grading: {'pass' if ev.get('overall') else 'fail'}  {ev.get('criteria')}")
        if show:
            show.finish()
            if watch:
                print("\nClose the watch window to end. To see it again later, open report.html above.")
            show.wait_until_closed()
            show.close()
        browser.close()
    summary["report"] = str(report)
    return summary
