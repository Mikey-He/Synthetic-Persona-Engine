import { isAdmin, unauthorized } from "@/lib/admin";
import { db } from "@/lib/db";

type Context = { params: Promise<{ id: string }> };

// Session status for the agent runner, which stops once the agent has clicked
// I'm finished. Research side only; the agent never sees this.
export async function GET(_request: Request, { params }: Context) {
  if (!(await isAdmin())) return unauthorized();
  const { id } = await params;
  const session = await db.session.findUnique({
    where: { id },
    select: { endedAt: true, terminationReason: true },
  });
  if (!session) return new Response(null, { status: 404 });
  return Response.json({ ended: session.endedAt !== null, terminationReason: session.terminationReason });
}
