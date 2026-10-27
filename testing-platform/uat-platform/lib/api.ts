import { getParticipantSession } from "@/lib/session";

// Participant API routes write only to a live session: 404 for an unknown
// token, 409 once the session has ended.
export async function liveSession(token: string) {
  const session = await getParticipantSession(token);
  if (!session) return { error: new Response(null, { status: 404 }) } as const;
  if (session.endedAt) return { error: new Response(null, { status: 409 }) } as const;
  return { session } as const;
}
