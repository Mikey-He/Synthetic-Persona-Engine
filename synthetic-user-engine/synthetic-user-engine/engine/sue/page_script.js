// Injected into the engine's own browser before every page (engine-design.md 2, 4.1).
// It only changes what the page displays; Version A itself is untouched, and the model
// never reads the DOM. The word rules live in Python; this script just collects text,
// writes back what Python decides, and reads the clickable elements.
(() => {
  if (window.__sue) return;

  // ---- Shadow DOM (engine-design.md 6.3) ---------------------------------------------------
  // Web components keep their text and controls in shadow roots, which document-wide queries
  // do not reach. Every query here goes through the document and every shadow root. A closed
  // shadow root is opened as it is created (this script runs before the page's own), so the
  // engine reads it like any other; the page behaves the same.
  const attach = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (init) {
    return attach.call(this, Object.assign({}, init, { mode: "open" }));
  };
  function roots() {
    const out = [document];
    const walk = (root) => {
      for (const el of root.querySelectorAll("*")) {
        if (el.shadowRoot) {
          out.push(el.shadowRoot);
          walk(el.shadowRoot);
        }
      }
    };
    walk(document);
    return out;
  }
  function queryAll(selector) {
    const rs = roots();
    return rs.length === 1 ? [...document.querySelectorAll(selector)] : rs.flatMap((r) => [...r.querySelectorAll(selector)]);
  }
  // Text nodes in document order, going into each shadow root where its host is.
  function* walkText(node) {
    if (node.nodeType === 3) {
      yield node;
      return;
    }
    if (node.shadowRoot) yield* walkText(node.shadowRoot);
    for (let c = node.firstChild; c; c = c.nextSibling) yield* walkText(c);
  }
  function parentOf(el) {
    return el.parentElement || (el.parentNode && el.parentNode.host) || null;
  }
  function closestDeep(el, selector) {
    for (let n = el; n; ) {
      const hit = n.closest ? n.closest(selector) : null;
      if (hit) return hit;
      const root = n.getRootNode ? n.getRootNode() : null;
      n = root && root.host ? root.host : null;
    }
    return null;
  }
  function containsDeep(a, b) {
    for (let n = b; n; n = n.parentNode || (n.host || null)) {
      if (n === a) return true;
    }
    return false;
  }
  function deepFromPoint(x, y) {
    let el = document.elementFromPoint(x, y);
    while (el && el.shadowRoot) {
      const inner = el.shadowRoot.elementFromPoint(x, y);
      if (!inner || inner === el) break;
      el = inner;
    }
    return el;
  }
  function byId(el, id) {
    const root = el.getRootNode ? el.getRootNode() : document;
    return (root.getElementById ? root.getElementById(id) : null) || document.getElementById(id);
  }

  const SKIP = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE"]);
  const CLICKABLE = [
    "a[href]", "button", "input:not([type=hidden])", "select", "textarea", "summary",
    "[role=button]", "[role=link]", "[role=checkbox]", "[role=radio]", "[role=option]",
    "[role=menuitem]", "[role=tab]", "[role=switch]",
  ].join(",");
  let nodes = [];

  function harnessRoot(selector, buttonText) {
    const marked = queryAll(selector)[0];
    if (marked) return marked;
    const button = queryAll("button").find((b) => b.textContent.trim() === buttonText);
    for (let el = button; el && el !== document.body; el = parentOf(el)) {
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

  function textParent(n) {
    return n.parentElement || (n.parentNode && n.parentNode.host) || null;
  }
  function textNodes() {
    const out = [];
    if (!document.body) return out;
    for (const n of walkText(document.body)) {
      const parent = textParent(n);
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
      const style = getComputedStyle(textParent(n));
      const visible = style.visibility !== "hidden" && inViewport(range.getClientRects());
      return { orig: original(n), cur: n.nodeValue, visible, harness: !!(root && containsDeep(root, n)), size: parseFloat(style.fontSize) || 0 };
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

  const GRAY_CSS = "[data-sue-gray]{background:#c8c8c8 !important;border-radius:3px}" +
    "[data-sue-gray] *{visibility:hidden !important}";
  function grayIcons(ids) {
    for (const root of roots()) {  // a shadow root does not see the document's styles
      const host = root === document ? document.head : root;
      if (!host || (root === document ? document.getElementById("sue-style") : root.querySelector("style[data-sue-style]"))) continue;
      const style = document.createElement("style");
      if (root === document) style.id = "sue-style";
      else style.setAttribute("data-sue-style", "");
      style.textContent = GRAY_CSS;
      host.appendChild(style);
    }
    const wanted = new Set(ids);
    queryAll("[data-kl]").forEach((el) => {
      if (wanted.has(el.dataset.kl)) el.setAttribute("data-sue-gray", "");
      else el.removeAttribute("data-sue-gray");
    });
  }

  function originalText(el) {
    const parts = [];
    for (const n of walkText(el)) {
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
    const out = queryAll('[aria-expanded="true"]').map((b) => parentOf(b)).filter(Boolean);
    queryAll("[role=dialog]").forEach((d) => out.push(d));
    return out;
  }
  function regionOf(el, popups) {
    let best = null;
    for (const node of popups) {
      if (!containsDeep(node, el)) continue;
      const r = node.getBoundingClientRect();
      if (!best || r.width * r.height < best.area) best = { node, area: r.width * r.height };
    }
    const node = best ? best.node : closestDeep(el, "main, nav, aside, header, footer") || document.body;
    const kind = best ? "popup" : node === document.body ? "other" : node.tagName.toLowerCase();
    // What a glance takes in: a whole opened part, else a list, table or group inside the region.
    let group = node;
    if (!best) {
      const g = closestDeep(el, "ul, ol, table, fieldset, [role=group], [role=listbox]");
      if (g && containsDeep(node, g) && g !== node) group = g;
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
      .map((id) => byId(group, id)).filter(Boolean).map(originalText).join(" ").trim();
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
    for (let n = el, i = 0; n && i < 3; n = parentOf(n), i++) {
      if (getComputedStyle(n).opacity === "0") return true;
    }
    return false;
  }
  function reveal(indices) {
    queryAll("[data-sue-revealed]").forEach((el) => {
      el.style.removeProperty("opacity");
      el.removeAttribute("data-sue-revealed");
    });
    for (const i of indices) {
      const el = queryAll(`[data-sue-i="${i}"]`)[0];
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
    const popups = popupRoots();
    const out = [];
    for (const el of queryAll(CLICKABLE + ",label")) {
      // A label is read with its field, unless the field cannot be seen (a file upload drawn as a
      // button): then the label is what a person clicks.
      if (el.tagName === "LABEL" && !(el.control && (el.control.type === "file" || !shown(el.control)))) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      if (r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight || r.left >= innerWidth) continue;
      const style = getComputedStyle(el);
      if (style.visibility === "hidden" || style.display === "none") continue;
      const cx = Math.min(Math.max(r.left + r.width / 2, 0), innerWidth - 1);
      const cy = Math.min(Math.max(r.top + r.height / 2, 0), innerHeight - 1);
      const hit = deepFromPoint(cx, cy);
      if (!hit || !(hit === el || containsDeep(el, hit) || containsDeep(hit, el))) continue;

      const isField = ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
      const label = isField && el.labels && el.labels[0] ? el.labels[0] : null;
      const kl = closestDeep(el, "[data-kl]");
      // A field is named by its label; a label with no text (hidden, or only styling) names nothing,
      // and then he goes by what he sees in the box (its placeholder), else its accessible name.
      const text = isField ? fieldName(el) : clean(el.innerText);
      // A button that is only a picture (trash can, cross, question mark): he sees the
      // picture, so it is named by what it shows, its accessible name. Python passes the
      // name through his vocabulary like any word. A grayed icon he does not recognise.
      const icon = !text && !isField && !closestDeep(el, "[data-sue-gray]")
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
        original: isField ? fieldName(el, true) : originalText(el),
        value: isField && !["checkbox", "radio"].includes(el.type) ? el.value : null,
        checked: ["checkbox", "radio"].includes(el.type) ? el.checked : el.getAttribute("aria-checked") === "true" ? true : null,
        disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
        expanded: el.hasAttribute("aria-expanded") ? el.getAttribute("aria-expanded") === "true" : null,
        kl: kl ? kl.dataset.kl : null,
        explains: (closestDeep(el, "[data-kl-explains]") || {}).dataset?.klExplains || null,
        harness: !!(root && containsDeep(root, el)),
        region: regionOf(el, popups),
        // A native dropdown opens outside the page, where no screenshot sees it: its options are listed.
        options: el.tagName === "SELECT" ? [...el.options].map((o) => o.text) : undefined,
        selected: el.tagName === "SELECT" && el.selectedIndex >= 0 ? el.options[el.selectedIndex].text : undefined,
        box: { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) },
        font: { size: parseFloat(style.fontSize), weight: style.fontWeight, color: style.color },
        background: style.backgroundColor,
      });
    }
    return out;
  }

  // Help text that is open on screen and says which item it explains (engine-design.md 4.5, 7).
  function openExplanations() {
    return queryAll("[data-kl-explains]")
      .filter((el) => inViewport(el.getClientRects()))
      .map((el) => ({ item: el.dataset.klExplains, original: originalText(el) }));
  }

  // The page's scroll, or, when the page itself does not scroll, the biggest panel in view that
  // does (an app that scrolls inside a container): cx, cy is where the wheel has to be.
  function scroller() {
    let best = null;
    for (const el of queryAll("*")) {
      if (el.scrollHeight <= el.clientHeight + 4) continue;
      const oy = getComputedStyle(el).overflowY;
      if (oy !== "auto" && oy !== "scroll" && oy !== "overlay") continue;
      const r = el.getBoundingClientRect();
      const w = Math.min(r.right, innerWidth) - Math.max(r.left, 0), h = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
      if (w <= 0 || h <= 0) continue;
      if (!best || w * h > best.area) best = { el, area: w * h, cx: Math.max(r.left, 0) + w / 2, cy: Math.max(r.top, 0) + h / 2 };
    }
    return best && best.area > innerWidth * innerHeight * 0.25 ? best : null;
  }
  function scrollState() {
    const el = document.scrollingElement;
    const max = Math.round(el.scrollHeight - innerHeight);
    if (max > 0) return { y: Math.round(el.scrollTop), max };
    const inner = scroller();
    if (!inner) return { y: Math.round(el.scrollTop), max };
    return { y: Math.round(inner.el.scrollTop), max: Math.round(inner.el.scrollHeight - inner.el.clientHeight),
             cx: Math.round(inner.cx), cy: Math.round(inner.cy) };
  }

  // Every item mark on the page, visible or not, to report items that were never marked.
  function marks() {
    return [...new Set(queryAll("[data-kl]").map((el) => el.dataset.kl))];
  }

  // Every value on the page: field contents and ticked boxes. Part of the screen state,
  // so an action tried before counts as new once something on the page has changed.
  // What is open on the whole page, scrolled into view or not: the screen state must not
  // change because he scrolled (engine-design.md 4.5).
  function expanded(selector, buttonText) {
    const root = harnessRoot(selector, buttonText);
    return queryAll('[aria-expanded="true"]')
      .filter((el) => !(root && containsDeep(root, el)))
      .map((el) => originalText(el) || el.getAttribute("aria-label") || "")
      .filter(Boolean);
  }

  function formState() {
    return queryAll("input, select, textarea")
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
    const hit = deepFromPoint(x, y);
    const control = hit && closestDeep(hit, LOGGED);
    if (!control || control.hasAttribute("aria-label")) return null;
    const by = (control.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map((id) => byId(control, id)).filter(Boolean).map(originalText).join(" ").trim();
    control.setAttribute("aria-label", by || originalText(control));
    control.setAttribute("data-sue-aria", "");
    return control.getAttribute("aria-label");
  }
  function clearLabelForLog() {
    queryAll("[data-sue-aria]").forEach((el) => {
      el.removeAttribute("aria-label");
      el.removeAttribute("data-sue-aria");
    });
  }

  // Warning and error text he did not notice this step (engine-design.md 4.9): hidden for the
  // screenshot. A warning is text in an alert, in an element styled as an error or warning, or
  // in a strong red. Labels and controls are never hidden, even when styled as errors (an
  // invalid field's label turns red), and neither is anything that holds a control.
  function isWarning(n) {
    if (n.matches("[role=alert], [aria-live=assertive]")) return true;
    const cls = (n.getAttribute("class") || "").toLowerCase();
    if (/(^|[\s:_-])(error|warning|alert|danger|invalid)([\s_-]|$)/.test(cls)) return true;
    const rgb = (getComputedStyle(n).color.match(/\d+/g) || []).map(Number);
    return rgb.length >= 3 && rgb[0] >= 170 && rgb[1] <= 100 && rgb[2] <= 100;
  }
  function warningRoot(el) {
    for (let n = el, i = 0; n && n !== document.body && i < 3; n = parentOf(n), i++) {
      if (n.tagName === "LABEL" || n.matches(CLICKABLE) || n.querySelector(CLICKABLE)) return null;
      if (isWarning(n)) return n;
    }
    return null;
  }
  function hideWarnings(on) {
    queryAll("[data-sue-unnoticed]").forEach((el) => {
      el.style.removeProperty("visibility");
      el.removeAttribute("data-sue-unnoticed");
    });
    if (!on) return [];
    const hidden = [];
    for (const n of textNodes()) {
      const el = textParent(n);
      if (!el || closestDeep(el, "label") || closestDeep(el, CLICKABLE)) continue;
      const w = warningRoot(el);
      if (!w || w.hasAttribute("data-sue-unnoticed")) continue;
      w.style.setProperty("visibility", "hidden", "important");
      w.setAttribute("data-sue-unnoticed", "");
      hidden.push(originalText(w));
    }
    return hidden;
  }

  // ---- item marks from the flow's locators (engine-design.md 6.3) ----------------------
  // A product that is not our platform carries no data-kl marks. The flow says how to find
  // each item's control (locate) and the help text that explains it (explainedBy); the marks
  // are put on before every look, and taken off again, so a page that re-renders is marked
  // afresh. Marks the product carries itself are never touched.
  // Controls: everything clickable, plus pictures with a name that hold no control (an info
  // icon). A container with a name (a nav labelled Main) is not a control: its links are.
  const ICONISH = "[aria-label],[title],img[alt],[role=img]";
  function norm(t) {
    return (t || "").replace(/\s+/g, " ").trim().toLowerCase().replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, "");
  }
  function roleOf(el) {
    const role = el.getAttribute("role");
    if (role) return role;
    const tag = el.tagName;
    if (tag === "A") return el.hasAttribute("href") ? "link" : "";
    if (tag === "BUTTON" || tag === "SUMMARY") return "button";
    if (tag === "SELECT") return "combobox";
    if (tag === "TEXTAREA") return "textbox";
    if (tag === "IMG") return "img";
    if (tag === "INPUT") {
      const t = (el.getAttribute("type") || "text").toLowerCase();
      if (t === "checkbox" || t === "radio") return t;
      if (["button", "submit", "reset"].includes(t)) return "button";
      return "textbox";
    }
    return "";
  }
  function labelOf(el) {
    const by = (el.getAttribute("aria-labelledby") || "").split(/\s+/).filter(Boolean)
      .map((id) => byId(el, id)).filter(Boolean).map(originalText).join(" ").trim();
    return clean(el.getAttribute("aria-label") || by || el.getAttribute("title") || el.getAttribute("alt") || "");
  }
  // A field's name as a person reads it: its label's text; when the label is empty, the placeholder
  // shown in the box; else its accessible name. The recorder and the engine name it the same way.
  function fieldName(el, original) {
    const read = (x) => clean(original ? originalText(x) : x.innerText);
    const fromLabel = el.labels && el.labels[0] ? read(el.labels[0]) : "";
    if (fromLabel) return fromLabel;
    if (["button", "submit", "reset"].includes(el.type)) return clean(el.value);
    return clean(el.getAttribute("placeholder") || el.getAttribute("aria-label") || "");
  }
  function textOf(el) {
    const isField = ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName);
    return isField ? fieldName(el, true) : originalText(el);
  }
  function shown(el) {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return false;
    const style = getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none";
  }
  function regionKind(el) {
    if (closestDeep(el, "[role=dialog], dialog")) return "dialog";
    const lm = closestDeep(el, "main, nav, aside, header, footer");
    return lm ? lm.tagName.toLowerCase() : "other";
  }
  function groupOf(el) {
    return (regionOf(el, popupRoots()).group || {}).heading || "";
  }
  function same(have, want, how) {
    const h = norm(have), w = norm(want);
    if (!w) return false;
    if (how === "contains") return h.includes(w);
    if (how === "starts") return h.startsWith(w);
    return h === w;
  }
  function fits(el, loc, how) {
    if (loc.role && roleOf(el) !== loc.role) return false;
    if (loc.text && !same(textOf(el), loc.text, how)) return false;
    if (loc.label && !same(labelOf(el), loc.label, how)) return false;
    if (loc.region && regionKind(el) !== loc.region) return false;
    if (loc.group && !same(groupOf(el), loc.group, "exact")) return false;
    return true;
  }
  function outermost(found) {
    return found.filter((el) => !found.some((o) => o !== el && containsDeep(o, el)));
  }
  function deepest(found) {
    return found.filter((el) => !found.some((o) => o !== el && containsDeep(el, o)));
  }
  function controlsIn() {
    const clickable = outermost(queryAll(CLICKABLE).filter(shown));
    const icons = queryAll(ICONISH).filter((el) => shown(el) && !el.matches(CLICKABLE)
      && !el.querySelector(CLICKABLE) && !closestDeep(el, CLICKABLE) && !SKIP.has(el.tagName));
    return [...clickable, ...icons].sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1));
  }
  function pick(found, loc) {
    return loc.nth != null ? [found[loc.nth]].filter(Boolean) : found;
  }
  function locate(loc) {
    if (loc.kind === "explains") {
      let pool;
      try {
        pool = loc.selector ? queryAll(loc.selector) : queryAll("body *").concat(roots().slice(1).flatMap((r) => [...r.querySelectorAll("*")]));
      } catch (e) {
        return { found: [], how: "bad selector" };
      }
      const want = norm(loc.text);
      return { found: deepest(pool.filter((el) => !SKIP.has(el.tagName) && shown(el) && norm(originalText(el)).includes(want))), how: "contains" };
    }
    let pool;
    try {
      pool = loc.selector ? queryAll(loc.selector).filter(shown) : controlsIn();
    } catch (e) {
      return { found: [], how: "bad selector" };
    }
    const how = loc.match || "exact";
    const found = outermost(pool.filter((el) => fits(el, loc, how)));
    if (!found.length && how === "exact" && (loc.text || loc.label)) {
      // Not word for word: a looser match, only when it finds one control (Send must not mark
      // Send invite), and reported as such so the flow can be fixed.
      const loose = outermost(pool.filter((el) => fits(el, loc, "contains")));
      if (loose.length === 1 || (loose.length && loc.nth != null)) return { found: pick(loose, loc), how: "contains" };
    }
    return { found: pick(found, loc), how };
  }
  function onRoute(routes, route) {
    if (!routes || !routes.length) return true;
    const path = route.split("?")[0];
    return routes.some((r) => r === route || r === path || (r.endsWith("*") && route.startsWith(r.slice(0, -1))));
  }
  function mark(locs, route) {
    queryAll("[data-sue-kl]").forEach((el) => {
      el.removeAttribute("data-kl");
      el.removeAttribute("data-sue-kl");
    });
    queryAll("[data-sue-explains]").forEach((el) => {
      el.removeAttribute("data-kl-explains");
      el.removeAttribute("data-sue-explains");
    });
    const report = {};
    for (const loc of locs || []) {
      if (!onRoute(loc.routes, route)) continue;
      const { found, how } = locate(loc);
      const key = loc.kind === "explains" ? loc.item + ":explains" : loc.item;
      report[key] = { n: found.length, how };
      for (const el of found) {
        if (loc.kind === "explains") {
          if (el.hasAttribute("data-kl-explains")) continue;
          el.setAttribute("data-kl-explains", loc.item);
          el.setAttribute("data-sue-explains", "");
        } else {
          if (el.hasAttribute("data-kl")) continue;
          el.setAttribute("data-kl", loc.item);
          el.setAttribute("data-sue-kl", "");
        }
      }
    }
    return report;
  }

  // What one control is, as a locator can name it: for the recorder and the mark check.
  function describe(el) {
    const r = el.getBoundingClientRect();
    const field = ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
    return {
      tag: el.tagName.toLowerCase(), role: roleOf(el), type: (el.getAttribute("type") || "").toLowerCase(),
      text: textOf(el), label: labelOf(el), region: regionKind(el), group: groupOf(el),
      kl: (closestDeep(el, "[data-kl]") || {}).dataset?.kl || null,
      box: { x: Math.round(r.left + scrollX), y: Math.round(r.top + scrollY), w: Math.round(r.width), h: Math.round(r.height) },
      checked: ["checkbox", "radio"].includes(el.type) ? el.checked : null,
      value: field && !["checkbox", "radio", "password"].includes(el.type) ? el.value : null,
    };
  }
  function controlOf(node) {
    const el = node && node.nodeType === 1 ? node : node && node.parentElement;
    if (!el) return null;
    const clickable = closestDeep(el, CLICKABLE);
    if (clickable) return clickable;
    const icon = closestDeep(el, ICONISH);
    return icon && !icon.querySelector(CLICKABLE) ? icon : null;
  }
  // Every control on the whole page, scrolled into view or not.
  function inventory() {
    return controlsIn().map(describe);
  }

  // The page has stopped changing: nothing in it changed for quietMs, or maxMs has passed.
  // A page that polls never goes network-idle, but its DOM settles.
  function quiet(quietMs, maxMs) {
    return new Promise((resolve) => {
      let timer = setTimeout(done, quietMs);
      const stop = setTimeout(done, maxMs);
      const obs = new MutationObserver(() => { clearTimeout(timer); timer = setTimeout(done, quietMs); });
      obs.observe(document, { subtree: true, childList: true, characterData: true, attributes: true });
      function done() { obs.disconnect(); clearTimeout(timer); clearTimeout(stop); resolve(true); }
    });
  }

  // The one control a scripted step names (set-up and clean-up steps, sue/target.py): marked so
  // that the engine's browser can act on it. Returns how many controls the locator found.
  function target(loc) {
    queryAll("[data-sue-target]").forEach((el) => el.removeAttribute("data-sue-target"));
    const { found } = locate(Object.assign({ kind: "control" }, loc));
    if (found[0]) found[0].setAttribute("data-sue-target", "");
    return found.length;
  }

  // The control at a place in the inventory, marked the same way (steps written by the researcher, sue/written.py).
  function targetAt(i) {
    queryAll("[data-sue-target]").forEach((el) => el.removeAttribute("data-sue-target"));
    const el = controlsIn()[i];
    if (el) el.setAttribute("data-sue-target", "");
    return !!el;
  }

  // What this page is made of, for the capability check when a task is recorded.
  function probe() {
    const rs = roots();
    const canvases = queryAll("canvas").map((c) => {
      const r = c.getBoundingClientRect();
      return Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0)) * Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
    });
    const text = document.body ? document.body.innerText || "" : "";
    const letters = (text.match(/[\p{L}]/gu) || []).length;
    const cjk = (text.match(/[\u3400-\u9fff]/g) || []).length;
    const frames = [...document.querySelectorAll("iframe")].map((f) => f.src || "");
    return {
      shadowRoots: rs.length - 1,
      iframes: frames.length,
      captcha: frames.some((src) => /recaptcha|hcaptcha|turnstile|captcha/i.test(src)),
      canvasShare: Math.round((Math.max(0, ...canvases) / (innerWidth * innerHeight)) * 100) / 100,
      nativeSelects: queryAll("select").length,
      fileInputs: queryAll("input[type=file]").length,
      cjkShare: letters ? Math.round((cjk / letters) * 100) / 100 : 0,
      innerScroll: !!(document.scrollingElement.scrollHeight <= innerHeight && scroller()),
    };
  }

  window.__sue = {
    collect, apply, grayIcons, elements, openExplanations, scrollState, marks, formState, expanded, labelForLog,
    clearLabelForLog,
    focus, reveal, hideWarnings,
    mark, describe, controlOf, inventory, norm, quiet, target, targetAt, probe,
  };
})();
