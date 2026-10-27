"use client";

import { useState, type ReactNode } from "react";

export function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-1 text-[12px] leading-4 text-error">{message}</p>;
}

type OutlinedInputProps = {
  id: string;
  label: string;
  value: string;
  onChange?: (value: string) => void;
  prefix?: string;
  suffix?: string;
  disabled?: boolean;
  invalid?: boolean;
  inputMode?: "decimal" | "text";
  // The label rests inside the empty field and moves onto the border on focus,
  // like the Name field in the reference capture. Others keep it on the border.
  floating?: boolean;
  className?: string;
  onFocus?: () => void;
  onBlur?: () => void;
  kl?: string; // knowledge item this field shows, for the AI engine (engine-design.md 7)
};

export function OutlinedInput({
  id,
  label,
  value,
  onChange,
  prefix,
  suffix,
  disabled,
  invalid,
  inputMode,
  floating,
  className = "",
  onFocus,
  onBlur,
  kl,
}: OutlinedInputProps) {
  const [focused, setFocused] = useState(false);
  const resting = floating && !focused && value === "";
  return (
    <div
      data-kl={kl}
      className={`relative flex h-11 items-center rounded border bg-white ${
        invalid ? "border-error" : focused ? "border-primary" : "border-line hover:border-ink"
      } ${disabled ? "bg-surface" : ""} ${className}`}
    >
      {prefix && <span className={`pl-3 ${disabled ? "text-muted" : ""}`}>{prefix}</span>}
      <input
        id={id}
        type="text"
        inputMode={inputMode}
        value={value}
        disabled={disabled}
        readOnly={!onChange}
        onChange={(event) => onChange?.(event.target.value)}
        onFocus={() => {
          setFocused(true);
          onFocus?.();
        }}
        onBlur={() => {
          setFocused(false);
          onBlur?.();
        }}
        className={`h-full min-w-0 flex-1 bg-transparent outline-none ${prefix ? "pl-1" : "pl-3"} ${
          suffix ? "pr-1" : "pr-3"
        } disabled:text-muted`}
      />
      {suffix && <span className="pr-3 text-muted">{suffix}</span>}
      <label
        htmlFor={id}
        className={`pointer-events-none absolute left-2.5 bg-white px-1 transition-all ${
          resting ? "top-1/2 -translate-y-1/2 text-muted" : "-top-2 text-[12px] leading-4"
        } ${invalid ? "text-error" : focused ? "text-primary" : "text-muted"} ${disabled ? "bg-surface" : ""}`}
      >
        {label}
      </label>
    </div>
  );
}

type CheckboxProps = {
  label: ReactNode;
  checked: boolean;
  disabled?: boolean;
  onChange?: (checked: boolean) => void;
  help?: ReactNode; // a (?) popover after the label
  description?: ReactNode; // a line of explanation under the label
  kl?: string; // knowledge item this option shows, for the AI engine (engine-design.md 7)
};

export function Checkbox({ label, checked, disabled, onChange, help, description, kl }: CheckboxProps) {
  return (
    <div className="py-1.5" data-kl={kl}>
      <div className="flex items-center gap-3">
        <label className={`flex items-center gap-3 ${disabled ? "text-muted" : "cursor-pointer"}`}>
          <input
            type="checkbox"
            className="size-4"
            checked={checked}
            disabled={disabled}
            readOnly={!onChange}
            // No handler when read-only, so a server-rendered view can use it too.
            onChange={onChange ? (event) => onChange(event.target.checked) : undefined}
          />
          {label}
        </label>
        {help}
      </div>
      {description && <p className="ml-7 text-[12px] leading-4 text-muted">{description}</p>}
    </div>
  );
}

export function PreviewTag() {
  return (
    <span className="rounded border border-line bg-surface px-1.5 text-[12px] leading-5 text-muted">
      Preview
    </span>
  );
}
