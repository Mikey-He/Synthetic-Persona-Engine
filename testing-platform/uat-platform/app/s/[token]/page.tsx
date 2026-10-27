import Link from "next/link";
import { redirect } from "next/navigation";
import { Notice } from "@/components/console/Notice";
import { getParticipantSession } from "@/lib/session";

type Props = { params: Promise<{ token: string }> };

export default async function ConsentPage({ params }: Props) {
  const { token } = await params;
  const session = await getParticipantSession(token);
  if (session?.endedAt) return <Notice text="This session has ended." />;
  // Consent is for humans. Agent sessions start at the billing overview.
  if (session?.actorType === "synthetic") redirect(`/s/${token}/billing`);

  return (
    <main className="mx-auto max-w-2xl px-8 py-16">
      <h1 className="page-title">Before you start</h1>
      {/* Placeholder stays visible until the ethics-reviewed consent text replaces it. */}
      <p className="mt-4">[Consent text goes here after ethics review]</p>
      <Link href={`/s/${token}/billing`} className="btn-primary mt-8">
        Start task
      </Link>
    </main>
  );
}
