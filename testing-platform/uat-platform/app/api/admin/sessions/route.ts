import { z } from "zod";
import { isAdmin, unauthorized } from "@/lib/admin";
import { nextEvaluationVariant } from "@/lib/assignment";
import { createSession } from "@/lib/session";

const newSessionSchema = z.discriminatedUnion("actorType", [
  z.strictObject({
    actorType: z.literal("human"),
    familiarityBand: z.enum(["low", "medium", "high"]),
    // "evaluation" is the main study: the variant comes from block assignment
    // and the label follows it (evaluation_A or evaluation_B).
    datasetLabel: z.enum(["pilot", "calibration_A", "evaluation"]),
    variant: z.enum(["A", "B"]).optional(), // pilot only; defaults to A
  }),
  z.strictObject({
    actorType: z.literal("synthetic"),
    modelId: z.string().trim().min(1),
    promptVersion: z.string().trim().min(1),
    personaId: z.string().trim().min(1),
    calibrationId: z.string().trim().min(1).nullable(),
    temperature: z.number().min(0).max(2).nullable().optional(),
    variant: z.enum(["A", "B"]).default("A"),
  }),
]);

// Creates a session and returns its link. Humans start at consent, synthetic
// users at the billing overview. No name or email is ever taken.
export async function POST(request: Request) {
  if (!(await isAdmin())) return unauthorized();
  const body = newSessionSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  const input = body.data;
  let session;
  if (input.actorType === "human") {
    const { familiarityBand, datasetLabel, variant } = input;
    // calibration_A is A only, and block assignment picks the main-study variant.
    if (datasetLabel !== "pilot" && variant !== undefined) return new Response(null, { status: 400 });
    const human = { actorType: "human", familiarityBand } as const;
    if (datasetLabel === "evaluation") {
      const assigned = await nextEvaluationVariant(familiarityBand);
      session = await createSession({ ...human, variant: assigned, datasetLabel: `evaluation_${assigned}` });
    } else {
      session = await createSession({ ...human, variant: datasetLabel === "pilot" ? (variant ?? "A") : "A", datasetLabel });
    }
  } else {
    session = await createSession({
      actorType: "synthetic",
      variant: input.variant,
      agentRun: {
        modelId: input.modelId,
        promptVersion: input.promptVersion,
        personaId: input.personaId,
        calibrationId: input.calibrationId,
        temperature: input.temperature ?? null,
      },
    });
  }

  const origin = new URL(request.url).origin;
  const path = input.actorType === "human" ? `/s/${session.token}` : `/s/${session.token}/billing`;
  return Response.json(
    { id: session.id, token: session.token, link: `${origin}${path}`, variant: session.variant },
    { status: 201 },
  );
}
