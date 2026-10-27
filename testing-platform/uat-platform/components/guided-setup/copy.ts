import { budgetAmount, lastMonthSpend } from "@/lib/domain/costs";
import { coversOneProject, emailOptionsEnabled, validateConfig, type ValidationCode } from "@/lib/domain/rules";
import type { BudgetConfig, Fixture, Period, Trigger } from "@/lib/domain/types";
import type { Setting } from "@/lib/events/types";
import { formatMoney } from "@/lib/format";

// Guided setup copy, word for word from docs/prototype-design-a-b.md (Version
// B) where it is written there. Reasons explain a setting, never the task, and
// no option is marked as recommended (guide Part 14.5).

export type ScreenKey = "name" | "projects" | "period" | "amount" | "alerts" | "recipients" | "review";

type Screen = { key: ScreenKey; name: string; question: string; reason: string; setting: Setting | null };

export const SCREENS: Screen[] = [
  {
    key: "name",
    name: "Name",
    question: "What should this budget be called?",
    reason: "A clear name helps you find it later.",
    setting: "name",
  },
  {
    key: "projects",
    name: "Projects",
    question: "Which costs should this budget track?",
    reason: "Costs from projects you leave out will not count toward this budget.",
    setting: "scope",
  },
  {
    key: "period",
    name: "Period",
    question: "How often should the budget start over?",
    reason: "Spending resets to $0 at the start of each period.",
    setting: "period",
  },
  {
    key: "amount",
    name: "Amount",
    question: "How much should this budget allow each period?",
    reason: "Alerts are measured against this amount.",
    setting: "amount",
  },
  {
    key: "alerts",
    name: "Alerts",
    question: "When should alert emails go out?",
    reason: "Each rule sends an email when spending reaches a share of the amount.",
    setting: "alert",
  },
  {
    key: "recipients",
    name: "Recipients",
    question: "Who should get alert emails?",
    reason: "These people get an email whenever an alert rule is reached.",
    setting: "recipients",
  },
  {
    key: "review",
    name: "Review",
    question: "Here is your budget",
    reason: "Check each answer before you create the budget.",
    setting: null,
  },
];

export const PERIOD_CHOICES: { value: Period; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "yearly", label: "Yearly" },
  { value: "custom", label: "Custom dates" },
];

export const TRIGGER_CHOICES: { value: Trigger; label: string }[] = [
  { value: "actual", label: "money already spent" },
  { value: "forecasted", label: "money expected by the end of the period" },
];

// Messages on Continue. The project, amount and recipient texts are in the
// design doc; the name and percent texts follow the advanced form.
export const B_MESSAGES: Record<ValidationCode, string> = {
  name_required: "Enter a budget name.",
  amount_invalid: "Enter an amount greater than $0",
  percent_invalid: "Enter a percent from 1 to 1000.",
  recipient_required: "Choose at least one recipient",
};
export const NO_PROJECT_MESSAGE = "Choose at least one project";

function screenOfField(field: string): ScreenKey {
  if (field === "name") return "name";
  if (field.startsWith("scope")) return "projects";
  if (field.startsWith("amount")) return "amount";
  if (field.startsWith("thresholds")) return "alerts";
  return "recipients";
}

// What Continue checks on a screen: the product validation for that screen's
// fields, plus B's own rule that "Only specific projects" needs a project.
export function screenIssues(key: ScreenKey, config: BudgetConfig): { field: string; message: string }[] {
  const issues = validateConfig(config)
    .filter((issue) => screenOfField(issue.field) === key)
    .map((issue) => ({ field: issue.field, message: B_MESSAGES[issue.code] }));
  if (key === "projects" && !config.scope.allProjects && config.scope.projectIds.length === 0)
    issues.push({ field: "scope.projectIds", message: NO_PROJECT_MESSAGE });
  return issues;
}

// "$500", "$1,000", "$523.40".
export const money = (value: number, currency: string) =>
  formatMoney(value, currency, Number.isInteger(Math.round(value * 100) / 100) ? 0 : 2);

type Data = Pick<
  Fixture,
  "currency" | "today" | "projects" | "monthlyCosts" | "billingAccount" | "billingMembers" | "projectOwners"
>;

const EACH: Record<Period, string> = {
  monthly: "each month",
  quarterly: "each quarter",
  yearly: "each year",
  custom: "for the custom dates",
};

const joinAnd = (items: string[]) =>
  items.length <= 1 ? (items[0] ?? "") : `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;

export function tracksSummary(config: BudgetConfig, data: Data) {
  if (config.scope.allProjects) return `All projects in ${data.billingAccount.name}`;
  const names = data.projects.filter((p) => config.scope.projectIds.includes(p.id)).map((p) => p.name);
  return names.length === 0 ? "No projects chosen" : `Only ${joinAnd(names)}`;
}

export function periodSummary(config: BudgetConfig) {
  switch (config.period) {
    case "monthly":
      return "Every month";
    case "quarterly":
      return "Every quarter";
    case "yearly":
      return "Every year";
    case "custom":
      return `Custom dates, ${config.customRange?.from ?? "no start date"} to ${config.customRange?.to ?? "no end date"}`;
  }
}

export function amountSummary(config: BudgetConfig, data: Data) {
  if (config.amount.type === "last_period")
    return `Match last period's spend (${money(lastMonthSpend(data, config.scope), data.currency)}) ${EACH[config.period]}`;
  const target = config.amount.target;
  return target === undefined || !Number.isFinite(target)
    ? "No amount"
    : `${money(target, data.currency)} ${EACH[config.period]}`;
}

const triggerText = (trigger: Trigger) => TRIGGER_CHOICES.find((c) => c.value === trigger)?.label ?? trigger;

// "Email when money already spent reaches 50% ($500). Also at 80% ($800)."
export function alertsSummary(config: BudgetConfig, data: Data) {
  if (config.thresholds.length === 0) return "No alert rules";
  const base = budgetAmount(data, config);
  const at = (percent: number) =>
    `${percent}%${base !== undefined && Number.isFinite(percent) ? ` (${money((base * percent) / 100, data.currency)})` : ""}`;
  return config.thresholds
    .map((rule, i) => {
      const previous = config.thresholds[i - 1];
      if (!previous) return `Email when ${triggerText(rule.trigger)} reaches ${at(rule.percent)}.`;
      if (previous.trigger === rule.trigger) return `Also at ${at(rule.percent)}.`;
      return `Also when ${triggerText(rule.trigger)} reaches ${at(rule.percent)}.`;
    })
    .join(" ");
}

// "Project owners · Sam Rivera"
export function recipientsSummary(config: BudgetConfig, data: Data) {
  if (!emailOptionsEnabled(config)) return "Alert emails are off";
  const parts: string[] = [];
  if (config.recipients.billingAdminsAndUsers)
    parts.push(`Billing account admins and users · ${data.billingMembers.map((m) => m.name).join(", ")}`);
  if (config.recipients.projectOwners && coversOneProject(config)) {
    const owners = data.projectOwners[config.scope.projectIds[0]] ?? [];
    parts.push(`Project owners · ${owners.map((o) => o.name).join(", ")}`);
  }
  return parts.length === 0 ? "Nobody" : parts.join("; ");
}
