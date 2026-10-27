import { resolveRecipients } from "@/lib/domain/resolveRecipients";
import type { BudgetConfig, Evaluation, Fixture } from "@/lib/domain/types";

// Pure: no database, network, clock or randomness. Bump the version on any
// change and re-score stored sessions from the researcher console.
export const EVALUATOR_VERSION = "eval-v1";

const same = (a: string[], b: string[]) => {
  const left = [...a].sort();
  const right = [...b].sort();
  return left.length === right.length && left.every((value, i) => value === right[i]);
};

export function evaluate(b: BudgetConfig, saved: boolean, fx: Fixture): Evaluation {
  const people = resolveRecipients(b, fx);
  const criteria = {
    scope: !b.scope.allProjects && same(b.scope.projectIds, ["atlas-demo"]),
    period: b.period === "monthly",
    amount: b.amount.type === "specified" && b.amount.target === 1000,
    alert: b.thresholds.some((t) => t.percent === 80 && t.trigger === "actual"),
    recipients: people.length === 1 && people[0].id === "sam-rivera",
    persistence: saved,
  };
  return {
    criteria,
    overall: Object.values(criteria).every(Boolean),
    people,
    version: EVALUATOR_VERSION,
  };
}
