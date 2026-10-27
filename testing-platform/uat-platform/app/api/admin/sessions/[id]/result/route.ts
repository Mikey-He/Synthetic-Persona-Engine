import { isAdmin, unauthorized } from "@/lib/admin";
import { listBudgets } from "@/lib/budgets";
import { db } from "@/lib/db";
import { sessionEvaluation } from "@/lib/scoring";

type Context = { params: Promise<{ id: string }> };

// The saved budgets and the evaluation that scoring rule v1 picks, for the AI
// engine's own scoring once a run has stopped (engine-design.md 7). Research side
// only, behind the console cookie; the agent's browser never reaches it.
export async function GET(_request: Request, { params }: Context) {
  if (!(await isAdmin())) return unauthorized();
  const { id } = await params;
  const session = await db.session.findUnique({
    where: { id },
    select: { endedAt: true, terminationReason: true, _count: { select: { budgets: true } } },
  });
  if (!session) return new Response(null, { status: 404 });

  const [budgets, { scored, evaluation }] = await Promise.all([listBudgets(id), sessionEvaluation(id)]);
  return Response.json({
    ended: session.endedAt !== null,
    terminationReason: session.terminationReason,
    saves: session._count.budgets, // every saved version, including saves that changed nothing
    budgets: budgets.map((b) => ({ id: b.id, version: b.version, savedAt: b.savedAt, config: b.config })),
    scored: scored.saved
      ? { saved: true, budgetId: scored.budgetId, version: scored.version }
      : { saved: false },
    evaluation: evaluation && {
      criteria: evaluation.criteria,
      overall: evaluation.overallSuccess,
      recipients: evaluation.resolvedRecipients,
      evaluatorVersion: evaluation.evaluatorVersion,
    },
  });
}
