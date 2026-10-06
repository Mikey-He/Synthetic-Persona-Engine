// Injected into the engine's own browser before every page (engine-design.md 2, 4.1).
// It only changes what the page displays; Version A itself is untouched, and the model
// never reads the DOM. The word rules live in Python; this script just collects text,
// writes back what Python decides, and reads the clickable elements.
(() => {
  if (window.__sue) return;

  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  const CLICKABLE = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary",
    "[role=button]", "[role=link]", "[role=checkbox]", "[role=radio]", "[role=option]",
    "[role=menuitem]", "[role=tab]", "[role=switch]",
  ].join(",");
  let nodes = [];

  function harnessRoot(selector, buttonText) {
    const marked = document.querySelector(selector);
    if (marked) return marked;
    const button = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === buttonText);
    for (let el = button; el && el !== document.body; el = el.parentElement) {
      if (getComputedStyle(el).position === "fixed") return el;
    }
    return null;
  }

  // The text the page itself last wrote into this node. If React has changed the node
  // since we wrote to it, its new value becomes the original.
  function original(node) {
    if (node.__sueApplied === undefined || node.nodeValue !== node.__sueApplied) {
      node.__sueOrig = node.nodeValue;
      node.__sueApplied = undefined;
    }
    return node.__sueOrig;
  }

  function inViewport(rects) {
    for (const r of rects) {
      if (r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth) return true;
    }
    return false;
  }

  function textNodes() {
    const out = [];
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      const parent = n.parentElement;
      if (!parent || SKIP.has(parent.tagName) || !n.nodeValue.trim()) continue;
      out.push(n);
    }
    return out;
  }

  function collect(selector, buttonText) {
    const root = harnessRoot(selector, buttonText);
    nodes = textNodes();
    return nodes.map((n) => {
      const range = document.createRange();
      range.selectNodeContents(n);
      const style = getComputedStyle(n.parentElement);
      const visible = style.visibility !== "hidden" && inViewport(range.getClientRects());
      return { orig: original(n), cur: n.nodeValue, visible, harness: !!(root && root.contains(n)) };
    });
  }

  // values[i] is the text for nodes[i], or null to leave it alone.
  function apply(values) {
    values.forEach((value, i) => {
      const n = nodes[i];
      if (value === null || !n || !n.isConnected) return;
      if (n.nodeValue !== value) n.nodeValue = value;
      n.__sueApplied = value;
    });
  }

  function grayIcons(ids) {
    if (!document.getElementById("sue-style")) {
      const style = document.createElement("style");
      style.id = "sue-style";
      style.textContent =
        "[data-sue-gray]{background:#c8c8c8 !important;border-radius:3px}" +
        "[data-sue-gray] *{visibility:hidden !important}";
      document.head.appendChild(style);
    }
    const wanted = new Set(ids);
    document.querySelectorAll("[data-kl]").forEach((el) => {
      if (wanted.has(el.dataset.kl)) el.setAttribute("data-sue-gray", "");
      else el.removeAttribute("data-sue-gray");
    });
  }

  function originalText(el) {
    const parts = [];
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    for (let n = walker.nextNode(); n; n = walker.nextNode()) {
      if (n.nodeValue.trim()) parts.push(n.__sueOrig !== undefined ? n.__sueOrig : n.nodeValue);
    }
    return parts.join(" ").replace(/\s+/g, " ").trim();
  }

  function clean(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  // The part of the page an element sits in, for the reading order (engine-design.md 4.8):
  // whatever just opened (the parent of an expanded control, or a dialog), else its
  // landmark (main, nav, aside, header, footer).
  const regionIds = new WeakMap();
  let nextRegion = 1;
  function regionId(node) {
    if (!regionIds.has(node)) regionIds.set(node, nextRegion++);
    return regionIds.get(node);
  }
  function popupRoots() {
    const roots = [...document.querySelectorAll('[aria-expanded="true"]')].map((b) => b.parentElement).filter(Boolean);
    document.querySelectorAll("[role=dialog]").forEach((d) => roots.push(d));
    return roots;
  }
  function regionOf(el, roots) {
    let best = null;
    for (const node of roots) {
      if (!node.contains(el)) continue;
      const r = node.getBoundingClientRect();
      if (!best || r.width * r.height < best.area) best = { node, area: r.width * r.height };
    }
    const node = best ? best.node : el.closest("main, nav, aside, header, footer") || document.body;
    const kind = best ? "popup" : node === document.body ? "other" : node.tagName.toLowerCase();
    // What a glance takes in: a whole opened part, else a list, table or group inside the region.
    let group = node;
    if (!best) {
      const g = el.closest("ul, ol, table, fieldset, [role=group], [role=listbox]");
      if (g && node.contains(g) && g !== node) group = g;
    }
    const box = (n) => {
      const r = n.getBoundingClientRect();
      const x = Math.max(0, r.left), y = Math.max(0, r.top);
      return { x: Math.round(x), y: Math.round(y), w: Math.round(Math.min(innerWidth, r.right) - x), h: Math.round(Math.min(innerHeight, r.bottom) - y) };
    };
    return { id: regionId(node), kind, ...box(node), group: { id: regionId(group), ...box(group), heading: headingOf(group, node) } };
  }

  // The label a group carries: a menu group's heading just above its list, a fieldset's
  // legend, a table's caption. Used for "information scent": a heading that matches the task draws
  // a person who does not know where to go into that group (engine-design.md 4.3).
  function headingOf(group, region) {
    if (!group || group === region) return "";
    const by = (group.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map((id) => document.getElementById(id)).filter(Boolean).map(originalText).join(" ").trim();
    if (by) return by;
    const own = group.tagName === "FIELDSET" ? group.querySelector("legend") : group.tagName === "TABLE" ? group.querySelector("caption") : null;
    if (own) return originalText(own);
    const prev = group.previousElementSibling;
    if (prev && !prev.matches(CLICKABLE) && !prev.querySelector(CLICKABLE)) {
      const t = originalText(prev);
      if (t && t.length <= 60) return t;
    }
    return "";
  }

  // Controls drawn invisible until the mouse is over their row (opacity 0), such as a
  // delete icon. A person sees them only when hovering; see reveal().
  function hiddenUntilHover(el) {
    for (let n = el, i = 0; n && i < 3; n = n.parentElement, i++) {
      if (getComputedStyle(n).opacity === "0") return true;
    }
    return false;
  }
  function reveal(indices) {
    document.querySelectorAll("[data-sue-revealed]").forEach((el) => {
      el.style.removeProperty("opacity");
      el.removeAttribute("data-sue-revealed");
    });
    for (const i of indices) {
      const el = document.querySelector(`[data-sue-i="${i}"]`);
      if (!el) continue;
      el.style.setProperty("opacity", "1", "important");
      el.setAttribute("data-sue-revealed", "");
    }
  }

  // Covers everything but the piece he is looking at (null uncovers the page).
  function focus(rect) {
    let hole = document.getElementById("sue-focus");
    if (!rect) {
      if (hole) hole.remove();
      return;
    }
    if (!hole) {
      hole = document.createElement("div");
      hole.id = "sue-focus";
      hole.setAttribute("aria-hidden", "true");
      document.documentElement.appendChild(hole);
    }
    hole.style.cssText =
      `position:fixed;left:${rect.x}px;top:${rect.y}px;width:${rect.w}px;height:${rect.h}px;` +
      "pointer-events:none;z-index:2147483646;border-radius:6px;box-shadow:0 0 0 200vmax rgba(255,255,255,.96)";
  }

  // Clickable elements a person could see in the viewport, with what they show.
  // Hidden accessibility text (aria-label, title) is never read as text: a person does
  // not see it. Only a button with no text at all is named by it, standing for its icon.
  function elements(selector, buttonText) {
    const root = harnessRoot(selector, buttonText);
    const roots = popupRoots();
    const out = [];
    for (const el of document.querySelectorAll(CLICKABLE)) {
      if (el.tagName === "LABEL") continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      const cx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
      const cy = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      const hit = document.elementFromPoint(cx, cy);
      if (!hit || !(hit === el || el.contains(hit) || hit.contains(el))) continue;

      const isField = ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
      const label = isField && el.labels && el.labels[0] ? el.labels[0] : null;
      const kl = el.closest("[data-kl]");
      const text = clean(label ? label.innerText : el.innerText);
      // A button that is only a picture (trash can, cross, question mark): he sees the
      // picture, so it is named by what it shows, its accessible name. Python passes the
      // name through his vocabulary like any word. A grayed icon he does not recognise.
      const icon = !text && !isField && !el.closest("[data-sue-gray]")
        ? clean(el.getAttribute("aria-label") || el.getAttribute("title") || "") : "";
      el.setAttribute("data-sue-i", String(out.length));
      out.push({
        index: out.length,
        hidden: !el.hasAttribute("data-sue-revealed") && hiddenUntilHover(el),
        tag: el.tagName.toLowerCase(),
        role: el.getAttribute("role") || "",
        type: el.getAttribute("type") || "",
        text,
        icon,
        original: label ? originalText(label) : originalText(el),
        value: isField && !["checkbox", "radio"].includes(el.type) ? el.value : null,
        checked: ["checkbox", "radio"].includes(el.type) ? el.checked : el.getAttribute("aria-checked") === "true" ? true : null,
        disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
        expanded: el.hasAttribute("aria-expanded") ? el.getAttribute("aria-expanded") === "true" : null,
        kl: kl ? kl.dataset.kl : null,
        explains: (el.closest("[data-kl-explains]") || {}).dataset?.klExplains || null,
        harness: !!(root && root.contains(el)),
        region: regionOf(el, roots),
        box: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
        font: { size: parseFloat(style.fontSize), weight: style.fontWeight, color: style.color },
        background: style.backgroundColor,
      });
    }
    return out;
  }

  // Help text that is open on screen and says which item it explains (engine-design.md 4.5, 7).
  function openExplanations() {
    return [...document.querySelectorAll("[data-kl-explains]")]
      .filter((el) => inViewport(el.getClientRects()))
      .map((el) => ({ item: el.dataset.klExplains, original: originalText(el) }));
  }

  function scrollState() {
    const el = document.scrollingElement;
    return { y: Math.round(el.scrollTop), max: Math.round(el.scrollHeight - innerHeight) };
  }

  // Every item mark on the page, visible or not, to report items that were never marked.
  function marks() {
    return [...new Set([...document.querySelectorAll("[data-kl]")].map((el) => el.dataset.kl))];
  }

  // Every value on the page: field contents and ticked boxes. Part of the screen state,
  // so an action tried before counts as new once something on the page has changed.
  // What is open on the whole page, scrolled into view or not: the screen state must not
  // change because he scrolled (engine-design.md 4.5).
  function expanded(selector, buttonText) {
    const root = harnessRoot(selector, buttonText);
    return [...document.querySelectorAll('[aria-expanded="true"]')]
      .filter((el) => !(root && root.contains(el)))
      .map((el) => originalText(el) || el.getAttribute("aria-label") || "")
      .filter(Boolean);
  }

  function formState() {
    return [...document.querySelectorAll("input, select, textarea")]
      .map((el) => (el.type === "checkbox" || el.type === "radio" ? (el.checked ? "1" : "0") : el.value))
      .join("\u0001");
  }

  // The platform's event log names a clicked control by its aria-label, else the texts its
  // aria-labelledby points to, else its text. The page shows rewritten text, so for the
  // moment of a click the control gets an aria-label with the original name: the platform
  // then logs what a person would have seen. Invisible, no layout change, removed after.
  const LOGGED = "a[href], button, input, select, textarea, label, summary, [role=button], [role=link], " +
    "[role=option], [role=checkbox], [role=radio], [role=menuitem], [role=tab], [contenteditable=true]";
  function labelForLog(x, y) {
    const hit = document.elementFromPoint(x, y);
    const control = hit && hit.closest(LOGGED);
    if (!control || control.hasAttribute("aria-label")) return null;
    const by = (control.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map((id) => document.getElementById(id)).filter(Boolean).map(originalText).join(" ").trim();
    control.setAttribute("aria-label", by || originalText(control));
    control.setAttribute("data-sue-aria", "");
    return control.getAttribute("aria-label");
  }
  function clearLabelForLog() {
    document.querySelectorAll("[data-sue-aria]").forEach((el) => {
      el.removeAttribute("aria-label");
      el.removeAttribute("data-sue-aria");
    });
  }

  window.__sue = {
    collect, apply, grayIcons, elements, openExplanations, scrollState, marks, formState, expanded, labelForLog,
    clearLabelForLog,
    focus, reveal,
  };
})();
