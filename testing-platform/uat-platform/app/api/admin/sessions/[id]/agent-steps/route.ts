import { z } from "zod";
import { isAdmin, unauthorized } from "@/lib/admin";
import { db } from "@/lib/db";

type Context = { params: Promise<{ id: string }> };

// One agent step from the runner: the action it returned, whether it ran, and
// the model's stated reason. Failed attempts are recorded too (build plan, The loop).
const stepSchema = z.strictObject({
  stepNo: z.number().int().positive(),
  screenshotPath: z.string().min(1).nullable(),
  action: z.record(z.string(), z.unknown()),
  reason: z.string().nullable(),
  executed: z.boolean(),
  errorLabel: z
    .enum(["invalid_json", "out_of_bounds", "model_timeout", "browser_error", "no_visible_change"])
    .nullable(),
  latencyMs: z.number().int().nonnegative().nullable(),
});

export async function POST(request: Request, { params }: Context) {
  if (!(await isAdmin())) return unauthorized();
  const { id } = await params;
  const body = stepSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  const session = await db.session.findUnique({ where: { id }, select: { actorType: true, agentRunId: true } });
  if (!session) return new Response(null, { status: 404 });
  if (session.actorType !== "synthetic" || !session.agentRunId) return new Response(null, { status: 409 });

  const step = body.data;
  await db.$transaction([
    db.agentStep.create({ data: { ...step, action: step.action as object, sessionId: id } }),
    // The run starts with its first recorded step.
    db.agentRun.updateMany({ where: { id: session.agentRunId, startedAt: null }, data: { startedAt: new Date() } }),
  ]);
  return new Response(null, { status: 201 });
}
