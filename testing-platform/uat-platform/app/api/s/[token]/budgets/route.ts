import { liveSession } from "@/lib/api";
import { saveBudget } from "@/lib/budgets";
import { validateConfig } from "@/lib/domain/rules";
import { saveBodySchema } from "@/lib/domain/schemas";

type Context = { params: Promise<{ token: string }> };

// Saves a budget version. The response carries the budget id and version only:
// evaluation results never reach a participant.
export async function POST(request: Request, { params }: Context) {
  const { token } = await params;
  const live = await liveSession(token);
  if ("error" in live) return live.error;

  const body = saveBodySchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return Response.json({ issues: [] }, { status: 400 });

  const issues = validateConfig(body.data.config);
  if (issues.length > 0) return Response.json({ issues }, { status: 400 });

  const saved = await saveBudget(live.session.id, body.data.config, body.data.editingBudgetId);
  return Response.json({ budgetId: saved.id, version: saved.version }, { status: 201 });
}
