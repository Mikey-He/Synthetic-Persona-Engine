"use client";

import { usePathname } from "next/navigation";
import {
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useState,
  type ReactNode,
} from "react";
import { EventLogger } from "./logger";

const LoggerContext = createContext<EventLogger | null>(null);

// Null outside a live session, so callers write logger?.log(...).
export const useLogger = () => useContext(LoggerContext);

// Anything a person can operate. A click inside none of these had no effect.
const INTERACTIVE =
  "a[href], button, input, select, textarea, label, summary, [role=button], [role=link], [role=option], [role=checkbox], [role=radio], [role=menuitem], [role=tab], [contenteditable=true]";
// Buttons and links, logged as control_clicked. Fields log field_changed instead.
const CONTROL = "a[href], button, [role=button], [role=link], [role=option], [role=menuitem], [role=tab]";

// Roughly what a person reads on the control: its aria-label, the labels it
// points to (a dropdown reads "Projects All projects"), or its visible text.
function labelOf(element: Element) {
  const labelledBy = element
    .getAttribute("aria-labelledby")
    ?.split(" ")
    .map((id) => document.getElementById(id)?.innerText ?? "")
    .join(" ");
  const text =
    element.getAttribute("aria-label") ||
    labelledBy ||
    (element instanceof HTMLElement ? element.innerText : element.textContent) ||
    "";
  return text.trim().replace(/\s+/g, " ").slice(0, 80);
}

type Props = {
  token: string;
  lastSeq: number;
  started: boolean;
  active: boolean; // false once the session has ended
  children: ReactNode;
};

export function EventLoggerProvider({ token, lastSeq, started, active, children }: Props) {
  const [logger] = useState(() => (active ? new EventLogger(token, lastSeq) : null));
  const pathname = usePathname();
  const route = pathname.slice(`/s/${token}`.length) || "/";

  // Layout effects run before any page's own effects, so session_started and
  // page_viewed come first in the log for the page they describe.
  useLayoutEffect(() => {
    if (!logger) return;
    logger.start();
    if (!started && logger.firstTime("session", "started")) {
      logger.log("session_started", null, {
        viewport: { width: window.innerWidth, height: window.innerHeight },
        zoom: window.devicePixelRatio,
        userAgent: navigator.userAgent,
      });
    }
    return () => logger.dispose();
  }, [logger, started]);

  useLayoutEffect(() => {
    logger?.pageViewed(route);
  }, [logger, route]);

  useEffect(() => {
    if (!logger) return;

    const onClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target : null;
      if (!target?.closest(INTERACTIVE)) {
        logger.log("click_no_effect", null, { x: event.clientX, y: event.clientY, route: logger.route });
        return;
      }
      const control = target.closest(CONTROL);
      if (control) {
        const label = labelOf(control);
        logger.log("control_clicked", label, {
          label,
          href: control.getAttribute("href"),
          route: logger.route,
        });
      }
    };

    // At most one scroll event per 500 ms, carrying the latest position.
    let scrollTimer: ReturnType<typeof setTimeout> | null = null;
    const onScroll = () => {
      if (scrollTimer !== null) return;
      scrollTimer = setTimeout(() => {
        scrollTimer = null;
        logger.log("scroll", null, { scrollY: Math.round(window.scrollY), route: logger.route });
      }, 500);
    };

    let resizeTimer: ReturnType<typeof setTimeout> | null = null;
    const onResize = () => {
      if (resizeTimer !== null) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(
        () => logger.log("viewport_changed", null, { width: window.innerWidth, height: window.innerHeight }),
        300,
      );
    };

    document.addEventListener("click", onClick, true);
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("click", onClick, true);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onResize);
      if (scrollTimer !== null) clearTimeout(scrollTimer);
      if (resizeTimer !== null) clearTimeout(resizeTimer);
    };
  }, [logger]);

  return <LoggerContext.Provider value={logger}>{children}</LoggerContext.Provider>;
}
