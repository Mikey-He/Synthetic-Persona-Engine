import type { ReactNode } from "react";
import { Notice } from "@/components/console/Notice";
import { ParticipantShell } from "@/components/console/ParticipantShell";
import { fixture } from "@/lib/fixtures";
import { getParticipantSession } from "@/lib/session";

type Props = { children: ReactNode; params: Promise<{ token: string }> };

export default async function ConsoleLayout({ children, params }: Props) {
  const { token } = await params;
  const session = await getParticipantSession(token);
  if (session?.endedAt) return <Notice text="This session has ended." />;

  const you = fixture.billingMembers.find((member) => member.isYou);
  return (
    <ParticipantShell
      token={token}
      accountName={fixture.billingAccount.name}
      userName={you?.name ?? ""}
    >
      {children}
    </ParticipantShell>
  );
}
