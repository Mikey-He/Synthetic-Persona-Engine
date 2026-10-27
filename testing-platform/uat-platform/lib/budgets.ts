import { randomUUID } from "node:crypto";
import type { Prisma } from "@/generated/prisma/client";
import { db } from "@/lib/db";
import { budgetConfigSchema, draftBodySchema } from "@/lib/domain/schemas";
import type { BudgetConfig } from "@/lib/domain/types";
import { writeEvaluation } from "@/lib/scoring";

// Server only. Drafts, budgets and evaluations hang off the session.

export type Draft = { config: BudgetConfig; editingBudgetId: string | null };
export type SavedBudget = { id: string; version: number; config: BudgetConfig; savedAt: Date };

// JSON round trip: drops undefined keys and stores NaN as null.
const toJson = (value: unknown) => JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;

export async function getDraft(sessionId: string): Promise<Draft | null> {
  const row = await db.budgetDraft.findUnique({ where: { sessionId } });
  if (!row) return null;
  const parsed = draftBodySchema.safeParse(row.draft);
  return parsed.success ? parsed.data : null;
}

export async function putDraft(sessionId: string, draft: Draft) {
  const json = toJson(draft);
  await db.budgetDraft.upsert({
    where: { sessionId },
    create: { sessionId, draft: json },
    update: { draft: json },
  });
}

const toSaved = (row: { id: string; version: number; config: unknown; savedAt: Date }) => ({
  id: row.id,
  version: row.version,
  config: budgetConfigSchema.parse(row.config),
  savedAt: row.savedAt,
});

// Latest version of each budget, most recently saved first.
export async function listBudgets(sessionId: string): Promise<SavedBudget[]> {
  const rows = await db.budget.findMany({
    where: { sessionId },
    orderBy: [{ savedAt: "desc" }, { version: "desc" }],
  });
  const latest = new Map<string, SavedBudget>();
  for (const row of rows) if (!latest.has(row.id)) latest.set(row.id, toSaved(row));
  return [...latest.values()];
}

export async function getBudget(sessionId: string, id: string): Promise<SavedBudget | null> {
  const row = await db.budget.findFirst({ where: { sessionId, id }, orderBy: { version: "desc" } });
  return row ? toSaved(row) : null;
}

// Writes a new version row (a new budget, or the next version of the one being
// edited), scores it, and clears the draft. The evaluation never leaves the server.
export async function saveBudget(sessionId: string, config: BudgetConfig, editingBudgetId: string | null) {
  return db.$transaction(async (tx) => {
    const edited = editingBudgetId
      ? await tx.budget.findFirst({
          where: { sessionId, id: editingBudgetId },
          orderBy: { version: "desc" },
        })
      : null;
    const id = edited?.id ?? randomUUID();
    const version = (edited?.version ?? 0) + 1;

    await tx.budget.create({ data: { id, version, sessionId, config: toJson(config) } });

    await writeEvaluation(tx, sessionId, { saved: true, config, budgetId: id, version });

    await tx.budgetDraft.deleteMany({ where: { sessionId } });
    return { id, version };
  });
}
