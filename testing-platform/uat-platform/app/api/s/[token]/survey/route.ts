import { z } from "zod";
import { db } from "@/lib/db";
import { SURVEY_INSTRUMENT } from "@/lib/survey";
import { getParticipantSession } from "@/lib/session";

type Context = { params: Promise<{ token: string }> };

const answerSchema = z.strictObject({ ease: z.number().int().min(1).max(7) });

// The post-task question. Humans only, answered once. It is asked after the
// session has ended, so an ended session is expected here.
export async function POST(request: Request, { params }: Context) {
  const { token } = await params;
  const session = await getParticipantSession(token);
  if (!session || session.actorType !== "human") return new Response(null, { status: 404 });

  const body = answerSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  const result = await db.surveyResponse.createMany({
    data: [{ sessionId: session.id, instrument: SURVEY_INSTRUMENT, answers: body.data }],
    skipDuplicates: true,
  });
  return new Response(null, { status: result.count === 1 ? 201 : 409 });
}
