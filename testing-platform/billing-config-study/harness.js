/* The study page's harness, loaded first in the prototype's <head> (app/index.html).
   Inside the study page (index.html opens the prototype with ?s=<session>) it
   - starts each participant from an empty product: what an earlier participant saved in this browser is cleared;
   - logs what the person does with the event names of the testing platform's versions A and B
     (testing-platform/uat-platform/docs/build-plan.md, Event types): pages, form sections, settings reached
     and returned to, clicks, field changes with the old and new value, validation messages, saves and
     reopened budgets; plus storage_written (what the product saved) and notice_shown (a pop-up message);
   - hands the events and what the product has saved (its localStorage) to the study page every second,
     and once more when the task bar's "I'm finished" asks for it.
   Opened on its own, without a study page around it, it does nothing and the prototype works as the original. */
(function () {
  "use strict";
  var session = new URLSearchParams(location.search).get("s");
  if (!session || window.parent === window) return;
  var OURS = /^uat:/;  // the harness's and the study page's own keys, never part of the product

  try {
    if (localStorage.getItem("uat:study-session") !== session) {
      Object.keys(localStorage).forEach(function (k) { if (!OURS.test(k)) localStorage.removeItem(k); });
      localStorage.setItem("uat:study-session", session);
    }
  } catch { /* storage blocked: the prototype starts as it would anyway */ }

  var queue = [], stopped = false, sentProduct = null;

  function product() {
    var out = {};
    try {
      Object.keys(localStorage).forEach(function (k) {
        if (OURS.test(k)) return;
        var v = localStorage.getItem(k);
        try { out[k] = JSON.parse(v); } catch { out[k] = v; }
      });
    } catch { /* ignore */ }
    return out;
  }

  function log(type, target, payload) {
    if (stopped) return;
    queue.push({ clientTs: new Date().toISOString(), type: type, target: target == null ? null : String(target).slice(0, 500), payload: payload == null ? null : payload });
  }

  // To the study page, which numbers the events and keeps them for the participant's file.
  function send(always) {
    var now = product(), text = JSON.stringify(now);
    if (!always && !queue.length && text === sentProduct) return;
    var message = { type: "uat:events", session: session, events: queue.splice(0) };
    if (always || text !== sentProduct) { message.product = now; sentProduct = text; }
    parent.postMessage(message, location.origin);
  }
  var timer = setInterval(send, 1000);
  addEventListener("pagehide", function () { if (!stopped) send(); });

  try {
    if (!sessionStorage.getItem("uat:started:" + session)) {
      sessionStorage.setItem("uat:started:" + session, "1");
      log("session_started", null, { viewport: { width: innerWidth, height: innerHeight }, zoom: devicePixelRatio, userAgent: navigator.userAgent });
    }
  } catch { /* ignore */ }

  // ---- what the person does ----

  var route = null, screen = null;
  function where() { return location.hash || "#"; }
  function pageViewed() {
    var r = where();
    if (r === route) return;
    log("page_viewed", r, { route: r, referrer: route });
    route = r;
  }
  addEventListener("hashchange", pageViewed);
  addEventListener("popstate", pageViewed);
  var push = history.pushState;
  history.pushState = function () { var out = push.apply(this, arguments); pageViewed(); return out; };

  function text(el) { return ((el && (el.innerText || el.textContent)) || "").trim().replace(/\s+/g, " "); }
  // What a person reads on a control: its aria-label, else its visible text.
  function labelOf(el) { return (el.getAttribute("aria-label") || text(el) || el.getAttribute("title") || "").slice(0, 80); }
  // A field's name: its label, else its placeholder, else its aria-label (as the engine names fields).
  function fieldName(el) {
    var label = el.id && document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    label = label || el.closest("label");
    var own = label ? text(label) : "";
    return (own || el.getAttribute("placeholder") || el.getAttribute("aria-label") || el.name || el.type || "field").slice(0, 80);
  }
  function kl(el) { var t = el.closest("[data-kl]"); return t ? t.getAttribute("data-kl") : null; }

  var INTERACTIVE = "a[href], button, input, select, textarea, label, summary, [role=button], [role=link], [role=option], [role=checkbox], [role=radio], [role=menuitem], [role=tab], [contenteditable=true], [data-page], [data-action], [data-step]";
  var CONTROL = "a[href], button, [role=button], [role=link], [role=option], [role=menuitem], [role=tab], [data-page], [data-action], [data-step]";
  document.addEventListener("click", function (event) {
    var t = event.target instanceof Element ? event.target : null;
    if (!t || !t.closest(INTERACTIVE)) {
      log("click_no_effect", null, { x: event.clientX, y: event.clientY, route: route, screen: screen });
      return;
    }
    var c = t.closest(CONTROL);
    if (c) {
      var label = labelOf(c);
      log("control_clicked", label, { label: label, kl: kl(c), route: route, screen: screen, x: event.clientX, y: event.clientY });
      if (c.matches("[data-finish]")) saveClicked();
    }
  }, true);

  // The prototype keeps its form in global variables of app.js (draft, errors, editing), read as they are.
  function app(name) { try { return JSON.parse(JSON.stringify(Function("return typeof " + name + " === 'undefined' ? null : " + name)())); } catch { return null; } }
  var saving = null;
  function saveClicked() {
    var draft = app("draft");
    log("save_clicked", "FINISH", { draft: draft, editing: app("editing"), screen: screen });
    log("save_attempted", "FINISH", { editing: app("editing") });
    saving = setTimeout(function () {  // nothing saved: the form shows what is wrong
      saving = null;
      log("save_failed", "FINISH", { errors: app("errors"), screen: screen });
    }, 400);
  }

  function valueOf(el) {
    if (el.type === "checkbox" || el.type === "radio") return el.checked;
    if (el.tagName === "SELECT") return el.options[el.selectedIndex] ? text(el.options[el.selectedIndex]) : el.value;
    return el.value;
  }
  var typing = new Map();  // a text field's last change, logged when the person pauses
  var before = new WeakMap();  // a field's value when the person last left it, the old value of the next change
  function changed(el) {
    var name = fieldName(el), now = valueOf(el), old = before.has(el) ? before.get(el) : el.defaultValue;
    if (el.type === "checkbox" || el.type === "radio") old = !now;
    before.set(el, now);
    log("field_changed", name, { field: name, from: old === undefined ? null : old, value: now, kl: kl(el), route: route, screen: screen });
  }
  document.addEventListener("focusin", function (event) {
    var el = event.target;
    if ((el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement) && !before.has(el)) before.set(el, valueOf(el));
  }, true);
  document.addEventListener("input", function (event) {
    var el = event.target;
    if (!(el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement) || el.type === "checkbox" || el.type === "radio") return;
    clearTimeout(typing.get(el));
    typing.set(el, setTimeout(function () { typing.delete(el); changed(el); }, 800));
  }, true);
  document.addEventListener("change", function (event) {
    var el = event.target;
    if (!(el instanceof HTMLInputElement || el instanceof HTMLSelectElement || el instanceof HTMLTextAreaElement)) return;
    if (typing.has(el)) { clearTimeout(typing.get(el)); typing.delete(el); }
    changed(el);
  }, true);

  var scrollTimer = null;
  document.addEventListener("scroll", function (event) {
    if (scrollTimer) return;
    var el = event.target === document ? document.scrollingElement : event.target;
    scrollTimer = setTimeout(function () {
      scrollTimer = null;
      log("scroll", null, { scrollY: Math.round(el.scrollTop || 0), route: route, screen: screen });
      settings();  // scrolling brings settings into view or out of it
    }, 500);
  }, true);
  var resizeTimer = null;
  addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () { log("viewport_changed", null, { width: innerWidth, height: innerHeight }); }, 300);
  });

  // What the product saves, as it saves it.
  var setItem = Storage.prototype.setItem;
  Storage.prototype.setItem = function (key, value) {
    var out = setItem.apply(this, arguments);
    if (this === localStorage && !OURS.test(key)) {
      var parsed; try { parsed = JSON.parse(value); } catch { parsed = value; }
      log("storage_written", key, { key: key, value: parsed, route: route, screen: screen });
      if (saving && key === "mpsBudgets") {
        clearTimeout(saving); saving = null;
        var id = app("editing"), list = Array.isArray(parsed) ? parsed : [];
        var saved = id ? list.filter(function (b) { return b.id === id; })[0] : list[list.length - 1];
        log("save_succeeded", saved ? saved.name : null, { budgetId: saved ? saved.id : null, budget: saved || null });
      }
    }
    return out;
  };

  // The screen on view: the page title and, in the step-by-step form, the open step. Messages that pop up
  // (a toast) are logged with their text. Both are read from the page as the person sees it.
  // The settings the task asks for, as versions A and B name them, found by their labels on screen.
  var SETTINGS = [["name", /^(Name\b|Budget name)/], ["period", /^Time range$/], ["scope", /^(Projects|Services)$/], ["amount", /^(Budget type|Target amount)$/],
                  ["alert", /^(Percent of budget|Trigger on)$/], ["recipients", /^Email alerts to /]];
  function onScreen(el) { var r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight; }
  function settingValue(label) {
    if (label.tagName !== "LABEL") return label.value;  // a field named by its own aria-label or placeholder
    var c = label.querySelector("input") || (label.closest(".field") || label.parentElement).querySelector("input, select, textarea, button[data-drop]");
    if (!c) return null;
    if (c.type === "checkbox") return c.checked;
    return c.tagName === "BUTTON" ? text(c) : c.value;
  }
  var reached = {}, visible = {}, left = {}, returnable = {}, shownErrors = [];
  function settings() {
    // a setting's label, or a field without one that names itself (the budget name: aria-label, placeholder)
    var labels = Array.prototype.slice.call(document.querySelectorAll("label, input[aria-label], input[placeholder]"));
    var nameOf = function (l) { return l.tagName === "LABEL" ? text(l) : (l.getAttribute("aria-label") || l.getAttribute("placeholder") || ""); };
    SETTINGS.forEach(function (s) {
      var label = labels.filter(function (l) { return s[1].test(nameOf(l)) && onScreen(l); })[0], key = s[0];
      if (label && !visible[key]) {
        Object.keys(left).forEach(function (o) { if (o !== key) returnable[o] = true; });
        if (!reached[key]) { reached[key] = true; log("setting_reached", key, { setting: key, value: settingValue(label), screen: screen }); }
        else if (returnable[key]) log("setting_returned", key, { setting: key, route: route, screen: screen });
        delete left[key]; delete returnable[key];
      }
      if (!label && visible[key]) { left[key] = true; delete returnable[key]; }
      visible[key] = !!label;
    });
    var errors = Array.prototype.slice.call(document.querySelectorAll(".error, [id^=rule-error]")).filter(onScreen).map(function (e) {
      var field = e.closest(".field"), l = field && field.querySelector("label");
      return { field: l ? text(l) : null, message: text(e).replace(/^⊗\s*/, "") };
    }).filter(function (e) { return e.message; });
    errors.forEach(function (e) {
      if (!shownErrors.some(function (x) { return x.field === e.field && x.message === e.message; })) log("validation_shown", e.field, e);
    });
    shownErrors = errors;
  }
  function look() {
    var title = text(document.getElementById("pageTitle")), open = text(document.querySelector(".step.open .stepname"));
    var now = open ? title + " / " + open : title;
    if (now && now !== screen) {
      log("screen_viewed", now, { screen: now, from: screen, route: route });
      if (/^Edit Budget/.test(title) && !/^Edit Budget/.test(screen || "")) log("budget_reopened", app("editing"), { budgetId: app("editing") });
      screen = now;
    }
    settings();
    var toast = document.getElementById("toast");
    var shown = toast && toast.style.display !== "none" ? text(toast) : "";
    if (shown && shown !== look.toast) log("notice_shown", shown, { kind: "toast", text: shown, route: route, screen: screen });
    look.toast = shown;
  }
  var pending = false;
  new MutationObserver(function () {
    if (pending) return;
    pending = true;
    requestAnimationFrame(function () { pending = false; look(); });
  }).observe(document.documentElement, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["style", "class"] });

  document.addEventListener("DOMContentLoaded", function () { pageViewed(); look(); });

  // ---- the end: the task bar's "I'm finished" ----
  addEventListener("message", function (event) {
    if (event.origin !== location.origin || !event.data || event.data.type !== "uat:finish") return;
    log("completion_declared", "I'm finished", null);
    log("session_ended", null, { terminationReason: "completion_declared" });
    send(true);
    stopped = true;
    clearInterval(timer);
    parent.postMessage({ type: "uat:finished", session: session }, location.origin);
  });
})();
