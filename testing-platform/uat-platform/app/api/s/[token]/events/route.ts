import { liveSession } from "@/lib/api";
import { db } from "@/lib/db";
import { eventBatchSchema, insertEvents } from "@/lib/events/server";

type Context = { params: Promise<{ token: string }> };

export async function POST(request: Request, { params }: Context) {
  const { token } = await params;
  const live = await liveSession(token);
  if ("error" in live) return live.error;

  const body = eventBatchSchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  await db.$transaction((tx) => insertEvents(tx, live.session.id, body.data.events));
  return new Response(null, { status: 204 });
}
