import { getPath, sameValue, setPath } from "./configPath";
import type { BudgetConfig } from "./types";

// Product rules shared by version A and, later, version B. They decide what
// the product allows. Task accuracy is judged separately by the evaluator,
// so every valid configuration saves, even one that fails the task.

export const coversOneProject = (c: BudgetConfig) =>
  !c.scope.allProjects && c.scope.projectIds.length === 1;

// The project owners option is always shown, but it works only when the budget
// covers exactly one project ("limited to budgets configured to monitor a
// single project" in the reference capture).
export const projectOwnersAvailable = coversOneProject;

// Removing every threshold rule disables the email settings.
export const emailOptionsEnabled = (c: BudgetConfig) => c.thresholds.length > 0;

export type FieldChange = { path: string; oldValue: unknown; newValue: unknown };
export type ClearedOption = { option: "recipients.projectOwners"; value: true };
export type ConfigUpdate = {
  config: BudgetConfig;
  changes: FieldChange[];
  cleared: ClearedOption[];
};

// Sets one or more fields, then applies the product rules. Returns every value
// that changed and every option a scope change cleared, so callers can log both.
export function updateConfig(
  config: BudgetConfig,
  updates: Array<[path: string, value: unknown]>,
): ConfigUpdate {
  let next = config;
  const changes: FieldChange[] = [];
  for (const [path, value] of updates) {
    const oldValue = getPath(next, path);
    if (sameValue(oldValue, value)) continue;
    next = setPath(next, path, value);
    changes.push({ path, oldValue, newValue: value });
  }

  const cleared: ClearedOption[] = [];
  // A checked project owners option is cleared, and turns unavailable, when the
  // scope no longer covers exactly one project.
  if (next.recipients.projectOwners && !coversOneProject(next)) {
    next = setPath(next, "recipients.projectOwners", false);
    cleared.push({ option: "recipients.projectOwners", value: true });
  }
  return { config: next, changes, cleared };
}

// "1000", " 80 " and "12.5" parse. "", "abc" and "1,000" do not.
export function parseNumber(text: string): number | undefined {
  const trimmed = text.trim();
  return /^-?(\d+(\.\d*)?|\.\d+)$/.test(trimmed) ? Number(trimmed) : undefined;
}

export type ValidationCode =
  | "name_required"
  | "amount_invalid"
  | "percent_invalid"
  | "recipient_required";

export type ValidationIssue = { field: string; code: ValidationCode };

const isPositive = (n: number | undefined) => typeof n === "number" && Number.isFinite(n) && n > 0;
const isPercent = (n: number) => Number.isFinite(n) && n >= 1 && n <= 1000;

// Product validation only, in page order. It never rejects a configuration for
// differing from the task answer. No project checked means every project, as in
// the reference capture, so an empty project list is not an error.
export function validateConfig(c: BudgetConfig): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  if (c.name.trim() === "") issues.push({ field: "name", code: "name_required" });
  if (c.amount.type === "specified" && !isPositive(c.amount.target))
    issues.push({ field: "amount.target", code: "amount_invalid" });
  c.thresholds.forEach((t, i) => {
    if (!isPercent(t.percent)) issues.push({ field: `thresholds.${i}.percent`, code: "percent_invalid" });
  });
  const { recipients } = c;
  const anyEmail =
    recipients.billingAdminsAndUsers || (recipients.projectOwners && coversOneProject(c));
  if (emailOptionsEnabled(c) && !anyEmail && !recipients.monitoring.linked)
    issues.push({ field: "recipients", code: "recipient_required" });
  return issues;
}
