import { connection } from "next/server";
import type { ReactNode } from "react";
import { Notice } from "@/components/console/Notice";
import { ViewportGate } from "@/components/console/ViewportGate";
import { EventLoggerProvider } from "@/lib/events/EventLoggerProvider";
import { getParticipantSession, lastEventSeq } from "@/lib/session";

type Props = { children: ReactNode; params: Promise<{ token: string }> };

export default async function ParticipantLayout({ children, params }: Props) {
  await connection(); // participant pages read live session data, so render per request
  const { token } = await params;
  const session = await getParticipantSession(token);
  if (!session) return <Notice text="This link is not valid." />;

  return (
    <EventLoggerProvider
      token={token}
      lastSeq={await lastEventSeq(session.id)}
      started={session.startedAt !== null}
      active={session.endedAt === null}
    >
      {children}
      <ViewportGate />
    </EventLoggerProvider>
  );
}
