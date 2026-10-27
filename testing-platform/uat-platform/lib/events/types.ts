import type { BudgetConfig } from "@/lib/domain/types";

// Event names match the Event types table in docs/build-plan.md exactly.
// Analysis code matches on them, so never rename one.
export const EVENT_TYPES = [
  "session_started",
  "page_viewed",
  "step_entered",
  "screen_viewed",
  "setting_reached",
  "field_changed",
  "setting_returned",
  "option_cleared_by_scope",
  "review_edit",
  "control_clicked",
  "click_no_effect",
  "scroll",
  "validation_shown",
  "save_clicked",
  "save_attempted",
  "save_succeeded",
  "save_failed",
  "budget_reopened",
  "completion_declared",
  "session_ended",
  "viewport_changed",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

// screen_viewed and review_edit belong to version B.
export const VERSION_A_EVENT_TYPES = EVENT_TYPES.filter(
  (type) => type !== "screen_viewed" && type !== "review_edit",
);

export type ClientEvent = {
  seq: number;
  clientTs: string; // ISO time on the participant's machine
  type: EventType;
  target: string | null;
  payload: unknown;
};

// Friction is compared by setting, not by page (guide Part 9).
export const SETTINGS = ["name", "scope", "period", "amount", "alert", "recipients"] as const;
export type Setting = (typeof SETTINGS)[number];

// The setting a config field belongs to. Unscored fields (filters, savings,
// read-only) belong to none, but their changes are still logged.
export function settingOfField(path: string): Setting | null {
  if (path === "name") return "name";
  if (path === "scope.allProjects" || path === "scope.projectIds") return "scope";
  if (path === "period" || path.startsWith("customRange")) return "period";
  if (path.startsWith("amount")) return "amount";
  if (path.startsWith("thresholds")) return "alert";
  if (path.startsWith("recipients")) return "recipients";
  return null;
}

// The current value of a setting, recorded when the setting is first reached.
export function settingValue(config: BudgetConfig, setting: Setting): unknown {
  switch (setting) {
    case "name":
      return config.name;
    case "scope":
      return { allProjects: config.scope.allProjects, projectIds: config.scope.projectIds };
    case "period":
      return { period: config.period, customRange: config.customRange ?? null };
    case "amount":
      return config.amount;
    case "alert":
      return config.thresholds;
    case "recipients":
      return config.recipients;
  }
}
