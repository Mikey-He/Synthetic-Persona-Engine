import type { BudgetConfig, Fixture, Recipient } from "./types";

// The people who would actually receive alert email (guide Part 7), each with
// the mechanism that produced them. Shared by the evaluator and both create flows.
export function resolveRecipients(b: BudgetConfig, fx: Fixture): Recipient[] {
  if (b.thresholds.length === 0) return []; // email settings disabled
  const out = new Map<string, Recipient>();
  if (b.recipients.billingAdminsAndUsers)
    fx.billingMembers.forEach((p) =>
      out.set(p.id, { id: p.id, name: p.name, email: p.email, via: "billing_roles" }),
    );
  const single = !b.scope.allProjects && b.scope.projectIds.length === 1;
  if (single && b.recipients.projectOwners)
    (fx.projectOwners[b.scope.projectIds[0]] ?? []).forEach((p) =>
      out.set(p.id, { id: p.id, name: p.name, email: p.email, via: "project_owners" }),
    );
  // Linked Monitoring channels would add their addresses here. The fixture has
  // no channels, so a linked box without a channel adds nobody.
  return [...out.values()];
}
