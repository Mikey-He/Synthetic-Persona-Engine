import type { ValidationCode } from "@/lib/domain/rules";
import type { AmountType, BudgetConfig, BudgetKind, Period, Project, Trigger } from "@/lib/domain/types";

// Version A copy, taken from the reference capture of 2026-09-30 where it
// shows the text. Version B has its own wording for the same settings.

export const SECTION_NAMES = { 1: "Define", 2: "Scope", 3: "Amount", 4: "Actions" } as const;

export const PERIOD_OPTIONS: { value: Period; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
  { value: "custom", label: "Custom range" },
];

// kl: the knowledge item an option shows, for the AI engine (engine-design.md 7).
export const TRIGGER_OPTIONS: { value: Trigger; label: string; kl?: string }[] = [
  { value: "actual", label: "Actual", kl: "T37" },
  { value: "forecasted", label: "Forecasted", kl: "T20" },
];

export const AMOUNT_TYPE_OPTIONS: { value: AmountType; label: string; kl?: string }[] = [
  { value: "specified", label: "Specified amount", kl: "T16" },
  { value: "last_period", label: "Last month's spend", kl: "T17" },
];

export const SAVINGS_OPTIONS = [
  { value: "savings_programs", label: "Savings programs" },
  { value: "other_savings", label: "Other savings" },
];

export const periodLabel = (period: Period) =>
  PERIOD_OPTIONS.find((option) => option.value === period)?.label ?? period;

export const triggerLabel = (trigger: Trigger) =>
  TRIGGER_OPTIONS.find((option) => option.value === trigger)?.label ?? trigger;

export const amountTypeLabel = (type: AmountType) =>
  AMOUNT_TYPE_OPTIONS.find((option) => option.value === type)?.label ?? type;

// The closed Projects dropdown: "All projects (2)" while none is checked, as in
// the capture, otherwise the chosen names.
export function projectsLabel(scope: BudgetConfig["scope"], projects: Project[]) {
  if (scope.allProjects) return `All projects (${projects.length})`;
  return projects
    .filter((project) => scope.projectIds.includes(project.id))
    .map((project) => project.name)
    .join(", ");
}

export const servicesLabel = (selected: string[], all: string[]) =>
  selected.length === 0 ? `All services (${all.length})` : selected.join(", ");

// Budgets list, "Applies to".
export const appliesTo = (scope: BudgetConfig["scope"], projects: Project[]) =>
  scope.allProjects ? "This billing account" : projectsLabel(scope, projects);

// Budgets list, "Trigger alerts at": "50%, 90%, and 100%".
export function alertsAt(thresholds: BudgetConfig["thresholds"]) {
  const percents = thresholds.map((t) => `${t.percent}%`);
  if (percents.length <= 1) return percents[0] ?? "—";
  if (percents.length === 2) return percents.join(" and ");
  return `${percents.slice(0, -1).join(", ")}, and ${percents.at(-1)}`;
}

// Budgets list, "Budget type". TODO: the capture only shows an alerts-only
// budget there ("Alerts only" is assumed); a budget saved without a kind shows
// its amount type instead.
export const kindLabel = (kind: BudgetKind) => (kind === "spend_cap" ? "Spend cap" : "Alerts only");

export const labelOptionText = (value: string) => value.replace(":", ": ");

// TODO: provisional until the reference capture shows each message. The capture
// shows the name error starting "A budget n", cut off by a tooltip.
export const VALIDATION_MESSAGES: Record<ValidationCode, string> = {
  name_required: "Enter a budget name.",
  amount_invalid: "Enter an amount greater than $0.",
  recipient_required: "Select at least one way to send alerts.",
  percent_invalid: "Enter a percent from 1 to 1000.",
};
