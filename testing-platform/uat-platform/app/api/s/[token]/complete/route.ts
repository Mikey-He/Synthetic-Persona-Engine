import { liveSession } from "@/lib/api";
import { db } from "@/lib/db";
import { eventBatchSchema, insertEvents } from "@/lib/events/server";
import { scoreEndedSession } from "@/lib/scoring";

type Context = { params: Promise<{ token: string }> };

// I'm finished. The request carries the last events (completion_declared and
// session_ended among them), stored together with the end of the session.
// Completion is recorded whether or not anything was saved.
export async function POST(request: Request, { params }: Context) {
  const { token } = await params;
  const live = await liveSession(token);
  if ("error" in live) return live.error;

  const body = eventBatchSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  await db.$transaction(async (tx) => {
    await insertEvents(tx, live.session.id, body.data.events);
    await tx.session.update({
      where: { id: live.session.id },
      data: { endedAt: new Date(), terminationReason: "completion_declared" },
    });
    await scoreEndedSession(tx, live.session.id);
  });
  return new Response(null, { status: 204 });
}
