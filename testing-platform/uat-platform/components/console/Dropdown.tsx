"use client";

import { useEffect, useId, useRef, useState, type ReactNode, type RefObject } from "react";

// Dropdowns render their options in the page instead of using a native
// <select>. A native popup is drawn by the browser outside the page, so a
// screenshot-based agent would never see the options. They look like the
// outlined fields in the reference capture: the label sits on the border.

function useDismiss(open: boolean, root: RefObject<HTMLElement | null>, dismiss: () => void) {
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) dismiss();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") dismiss();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, root, dismiss]);
}

type TriggerProps = {
  label?: string;
  display: string;
  open: boolean;
  disabled?: boolean;
  invalid?: boolean;
  onClick: () => void;
};

function Trigger({ label, display, open, disabled, invalid, onClick }: TriggerProps) {
  const labelId = useId();
  const buttonId = useId();
  return (
    <>
      <button
        id={buttonId}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby={label ? `${labelId} ${buttonId}` : undefined}
        onClick={onClick}
        className={`flex h-11 w-full items-center justify-between gap-2 rounded border bg-white px-3 text-left disabled:text-muted ${
          invalid ? "border-error" : open ? "border-primary" : "border-line hover:border-ink"
        }`}
      >
        <span className="truncate">{display}</span>
        <svg viewBox="0 0 24 24" className="size-5 shrink-0 text-muted" aria-hidden="true">
          <path d="M7 10l5 5 5-5z" fill="currentColor" />
        </svg>
      </button>
      {label && (
        <span
          id={labelId}
          className="pointer-events-none absolute -top-2 left-2.5 bg-white px-1 text-[12px] leading-4 text-muted"
        >
          {label}
        </span>
      )}
    </>
  );
}

type DropdownProps = {
  label?: string;
  display: string;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
  kl?: string; // knowledge item this field shows, for the AI engine (engine-design.md 7)
  children: (close: () => void) => ReactNode;
};

export function Dropdown({ label, display, disabled, invalid, className = "w-72", kl, children }: DropdownProps) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const [close] = useState(() => () => setOpen(false));
  useDismiss(open, root, close);

  return (
    <div ref={root} data-kl={kl} className={`relative ${className}`}>
      <Trigger
        label={label}
        display={display}
        open={open}
        disabled={disabled}
        invalid={invalid}
        onClick={() => setOpen((value) => !value)}
      />
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-full rounded border border-line bg-white py-1 shadow-lg">
          {children(close)}
        </div>
      )}
    </div>
  );
}

type Option<T extends string> = { value: T; label: string; kl?: string };

type SelectProps<T extends string> = {
  label?: string;
  value: T;
  options: readonly Option<T>[];
  onChange: (value: T) => void;
  className?: string;
  kl?: string;
};

export function Select<T extends string>({ label, value, options, onChange, className, kl }: SelectProps<T>) {
  const current = options.find((option) => option.value === value);
  return (
    <Dropdown label={label} display={current?.label ?? ""} className={className} kl={kl}>
      {(close) => (
        <div role="listbox">
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="option"
              data-kl={option.kl}
              aria-selected={option.value === value}
              onClick={() => {
                onChange(option.value);
                close();
              }}
              className={`block w-full px-4 py-2.5 text-left hover:bg-surface ${
                option.value === value ? "bg-selected text-selected-ink" : ""
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}
    </Dropdown>
  );
}

type ChecklistOption = { value: string; label: string; detail?: string };

type ChecklistProps = {
  label: string;
  display: string;
  options: ChecklistOption[];
  selected: string[];
  onApply: (next: string[]) => void;
  className?: string;
  kl?: string;
};

// A checklist that applies on OK, like the capture's Projects picker: Select
// all, one box per option, then Deselect all, Cancel and OK. Closing it any
// other way discards the unapplied ticks.
export function ChecklistDropdown({ label, display, options, selected, onApply, className = "w-full", kl }: ChecklistProps) {
  const [staged, setStaged] = useState<string[] | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const [discard] = useState(() => () => setStaged(null));
  const open = staged !== null;
  useDismiss(open, root, discard);

  const order = options.map((option) => option.value);
  const toggle = (value: string) =>
    setStaged((current) => {
      const next = current ?? [];
      const ticked = next.includes(value) ? next.filter((v) => v !== value) : [...next, value];
      return order.filter((v) => ticked.includes(v));
    });
  const allTicked = open && staged.length === options.length && options.length > 0;

  return (
    <div ref={root} data-kl={kl} className={`relative ${className}`}>
      <Trigger
        label={label}
        display={display}
        open={open}
        onClick={() => setStaged(open ? null : [...selected])}
      />
      {open && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 rounded border border-line bg-white shadow-lg">
          <div role="listbox" aria-multiselectable="true">
            <label className="flex cursor-pointer items-center gap-3 border-b border-line px-4 py-2.5 hover:bg-surface">
              <input
                type="checkbox"
                className="size-4"
                checked={allTicked}
                onChange={() => setStaged(allTicked ? [] : [...order])}
              />
              Select all
            </label>
            {options.map((option) => (
              <label key={option.value} className="flex cursor-pointer items-start gap-3 px-4 py-2 hover:bg-surface">
                <input
                  type="checkbox"
                  className="mt-0.5 size-4"
                  checked={staged.includes(option.value)}
                  onChange={() => toggle(option.value)}
                />
                <span>
                  <span className="block">{option.label}</span>
                  {option.detail && <span className="block text-muted">{option.detail}</span>}
                </span>
              </label>
            ))}
          </div>
          <div className="flex items-center gap-2 border-t border-line px-2 py-2">
            <button
              type="button"
              className="rounded px-3 py-1.5 font-medium text-primary hover:bg-selected disabled:text-muted disabled:hover:bg-transparent"
              disabled={staged.length === 0}
              onClick={() => setStaged([])}
            >
              Deselect all
            </button>
            <span className="flex-1" />
            <button type="button" className="rounded px-3 py-1.5 font-medium text-primary hover:bg-selected" onClick={discard}>
              Cancel
            </button>
            <button
              type="button"
              data-kl="T31" // engine item: a checklist applies only on OK
              className="rounded px-3 py-1.5 font-medium text-primary hover:bg-selected"
              onClick={() => {
                onApply(staged);
                setStaged(null);
              }}
            >
              OK
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
