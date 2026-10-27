import type { Prisma } from "@/generated/prisma/client";
import { db } from "@/lib/db";
import { budgetConfigSchema, draftBodySchema } from "@/lib/domain/schemas";
import type { BudgetConfig } from "@/lib/domain/types";
import { evaluate } from "@/lib/evaluator/evaluate";
import { pickScoredBudget, type ScoredBudget } from "@/lib/evaluator/pickScoredBudget";
import { defaults, fixture } from "@/lib/fixtures";

// Server only. Loads what scoring rule v1 needs from the stored record and
// writes Evaluation rows. Rows are only ever added, never overwritten.

type Client = Prisma.TransactionClient | typeof db;

const toJson = (value: unknown) => JSON.parse(JSON.stringify(value)) as Prisma.InputJsonValue;

// Rule v1 inputs: every save, when completion was declared (if it was), and
// the last draft, or the defaults when the create form was never touched.
export async function scoredBudget(client: Client, sessionId: string): Promise<ScoredBudget> {
  const session = await client.session.findUniqueOrThrow({
    where: { id: sessionId },
    select: { endedAt: true, terminationReason: true },
  });
  const saves = await client.budget.findMany({ where: { sessionId } });
  const draftRow = await client.budgetDraft.findUnique({ where: { sessionId } });
  const draft = draftRow ? draftBodySchema.safeParse(draftRow.draft) : null;
  return pickScoredBudget({
    saves: saves.map((save) => ({
      budgetId: save.id,
      version: save.version,
      savedAt: save.savedAt.getTime(),
      config: budgetConfigSchema.parse(save.config),
    })),
    completionDeclaredAt:
      session.terminationReason === "completion_declared" && session.endedAt
        ? session.endedAt.getTime()
        : null,
    lastDraft: draft?.success ? draft.data.config : defaults.config,
  });
}

export async function writeEvaluation(
  client: Client,
  sessionId: string,
  scored: { saved: boolean; config: BudgetConfig; budgetId?: string; version?: number },
) {
  const result = evaluate(scored.config, scored.saved, fixture);
  return client.evaluation.create({
    data: {
      sessionId,
      budgetId: scored.saved ? scored.budgetId : null,
      budgetVersion: scored.saved ? scored.version : null,
      criteria: toJson(result.criteria),
      overallSuccess: result.overall,
      resolvedRecipients: toJson(result.people),
      recipientMechanisms: toJson(Object.fromEntries(result.people.map((p) => [p.id, p.via]))),
      evaluatorVersion: result.version,
    },
  });
}

// At the end of a session nothing more can be saved. When nothing was saved,
// the last draft is scored now, so every ended session has an evaluation.
export async function scoreEndedSession(client: Client, sessionId: string) {
  const scored = await scoredBudget(client, sessionId);
  if (!scored.saved) await writeEvaluation(client, sessionId, scored);
}

// The stored evaluation of the budget that rule v1 scores, newest run first.
export async function sessionEvaluation(sessionId: string) {
  const scored = await scoredBudget(db, sessionId);
  const evaluation = await db.evaluation.findFirst({
    where: {
      sessionId,
      budgetId: scored.saved ? scored.budgetId : null,
      budgetVersion: scored.saved ? scored.version : null,
    },
    orderBy: { createdAt: "desc" },
  });
  return { scored, evaluation };
}

// Runs the current evaluate() over every stored session and adds one new
// Evaluation row per session.
export async function rescoreAll() {
  const sessions = await db.session.findMany({ select: { id: true } });
  for (const { id } of sessions) {
    await db.$transaction(async (tx) => writeEvaluation(tx, id, await scoredBudget(tx, id)));
  }
  return sessions.length;
}
