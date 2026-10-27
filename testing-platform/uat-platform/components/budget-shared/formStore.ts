import type { ValidationIssue } from "@/lib/domain/rules";
import type { BudgetConfig } from "@/lib/domain/types";

export type SectionNumber = 1 | 2 | 3 | 4;
export type FormMode = "create" | "edit";

export type FormState = {
  config: BudgetConfig;
  // Raw text of the number fields, so "1000." or "abc" stays on screen as typed.
  targetText: string;
  percentTexts: string[];
  // Create shows one step at a time; Edit opens every section at once.
  open: SectionNumber[];
  // Steps passed with Next, or checked by Finish. They show a check mark.
  visited: SectionNumber[];
  // Issues reported by the last Finish. One stays visible until it is fixed.
  reported: ValidationIssue[];
};

export type TextPatch = Partial<Pick<FormState, "targetText" | "percentTexts">>;

export type Change = (updates: Array<[path: string, value: unknown]>, patch?: TextPatch) => void;

const numberText = (value: number | undefined) =>
  value === undefined || Number.isNaN(value) ? "" : String(value);

export function initialFormState(config: BudgetConfig, mode: FormMode): FormState {
  return {
    config,
    targetText: numberText(config.amount.target),
    percentTexts: config.thresholds.map((threshold) => numberText(threshold.percent)),
    open: mode === "edit" ? [1, 2, 3, 4] : [1],
    visited: [],
    reported: [],
  };
}

// A tiny external store. Updates are synchronous, so an event handler can read
// the old value, apply a change and log both in one step.
export function createFormStore(initial: FormState) {
  let state = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => state,
    set(next: FormState) {
      state = next;
      listeners.forEach((listener) => listener());
    },
    subscribe(listener: () => void) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}

export type FormStore = ReturnType<typeof createFormStore>;

export const sectionOf = (field: string): SectionNumber =>
  field === "name" ? 1 : field.startsWith("scope") ? 2 : field.startsWith("amount") ? 3 : 4;
