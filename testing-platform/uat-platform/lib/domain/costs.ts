import type { BudgetConfig, Fixture } from "./types";

// Every cost a participant sees comes from fixture.monthlyCosts, and "this
// month" is the month of fixture.today, never the real clock.

export type CostData = Pick<Fixture, "today" | "projects" | "monthlyCosts">;

export function currentMonth(data: Pick<Fixture, "today">) {
  return data.today.slice(0, 7);
}

// "2026-01" -> "2025-12". String arithmetic, so no clock or time zone is involved.
export function previousMonth(month: string) {
  const [year, m] = month.split("-").map(Number);
  return m === 1 ? `${year - 1}-12` : `${year}-${String(m - 1).padStart(2, "0")}`;
}

export function costMonths(data: Pick<Fixture, "monthlyCosts">) {
  const months = new Set<string>();
  for (const costs of Object.values(data.monthlyCosts)) {
    for (const cost of costs) months.add(cost.month);
  }
  return [...months].sort();
}

export function projectCost(data: Pick<Fixture, "monthlyCosts">, projectId: string, month: string) {
  return data.monthlyCosts[projectId]?.find((cost) => cost.month === month)?.usd ?? 0;
}

export function totalCost(data: Pick<Fixture, "monthlyCosts">, projectIds: string[], month: string) {
  return projectIds.reduce((sum, id) => sum + projectCost(data, id, month), 0);
}

export function scopeProjectIds(data: Pick<Fixture, "projects">, scope: BudgetConfig["scope"]) {
  return scope.allProjects ? data.projects.map((project) => project.id) : scope.projectIds;
}

export function lastMonthSpend(data: CostData, scope: BudgetConfig["scope"]) {
  return totalCost(data, scopeProjectIds(data, scope), previousMonth(currentMonth(data)));
}

// The amount alert percentages are measured against, or undefined while the
// specified amount is empty or not a number.
export function budgetAmount(data: CostData, config: BudgetConfig) {
  return config.amount.type === "specified" ? config.amount.target : lastMonthSpend(data, config.scope);
}
