import { z } from "zod";
import { isAdmin, unauthorized } from "@/lib/admin";
import { abandonSession, endSessionAs } from "@/lib/session";

type Context = { params: Promise<{ id: string }> };

// With no body: End session in the console, for a session the participant
// left, recorded as abandoned. With a body: the agent runner ends a synthetic
// session by one of its stop rules (build plan, Stop rules and labels).
const runnerEndSchema = z.strictObject({
  terminationReason: z.enum(["abandoned", "step_limit", "time_limit", "loop", "technical_error"]),
});

export async function POST(request: Request, { params }: Context) {
  if (!(await isAdmin())) return unauthorized();
  const { id } = await params;
  const text = await request.text();
  let ended: boolean | null;
  if (text.trim() === "") {
    ended = await abandonSession(id).catch(() => null);
  } else {
    const body = runnerEndSchema.safeParse(JSON.parse(text || "null"));
    if (!body.success) return new Response(null, { status: 400 });
    ended = await endSessionAs(id, body.data.terminationReason, "agent_runner").catch(() => null);
  }
  if (ended === null) return new Response(null, { status: 404 });
  return new Response(null, { status: ended ? 204 : 409 });
}
