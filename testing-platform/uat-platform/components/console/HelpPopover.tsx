"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

// The (?) next to a setting. Clicking it opens a small panel with a close
// button, as in the reference capture. kl marks the icon and explains marks the
// item its text explains, for the AI engine (engine-design.md 7); neither is visible.
export function HelpPopover({ children, kl, explains }: { children: ReactNode; kl?: string; explains?: string }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  return (
    <span ref={root} className="relative inline-flex align-middle">
      {/* TODO: the icon has no visible text; its aria-label is not written in the docs. */}
      <button
        type="button"
        data-kl={kl}
        aria-label="Help"
        aria-expanded={open}
        onClick={(event) => {
          event.preventDefault(); // inside a <label>, do not toggle the field
          setOpen((value) => !value);
        }}
        className="flex size-5 items-center justify-center rounded-full text-muted hover:text-ink"
      >
        <svg viewBox="0 0 24 24" className="size-[18px]" aria-hidden="true">
          <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
          <path
            d="M9.8 9.6a2.3 2.3 0 1 1 3.4 2c-.7.4-1.2.9-1.2 1.7v.4"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
          />
          <circle cx="12" cy="16.9" r="1.1" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <span
          role="dialog"
          data-kl-explains={explains}
          className="absolute left-0 top-6 z-40 block w-80 rounded bg-ink px-4 py-3 pr-9 text-[13px] font-normal leading-5 text-white shadow-lg"
        >
          {children}
          <button
            type="button"
            aria-label="Close"
            onClick={(event) => {
              event.preventDefault();
              setOpen(false);
            }}
            className="absolute right-2 top-2 flex size-6 items-center justify-center rounded text-white/80 hover:text-white"
          >
            <svg viewBox="0 0 24 24" className="size-4" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </span>
      )}
    </span>
  );
}
