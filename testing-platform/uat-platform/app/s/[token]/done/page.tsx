import { Notice } from "@/components/console/Notice";
import { SurveyForm } from "@/components/console/SurveyForm";
import { db } from "@/lib/db";
import { getParticipantSession } from "@/lib/session";
import { SURVEY_INSTRUMENT, THANK_YOU } from "@/lib/survey";

type Props = { params: Promise<{ token: string }> };

export default async function DonePage({ params }: Props) {
  const { token } = await params;
  const session = await getParticipantSession(token);
  if (!session) return null; // the layout already showed "This link is not valid."
  if (session.actorType === "synthetic") return <Notice text="Session ended" />;

  const answered = await db.surveyResponse.findUnique({
    where: { sessionId_instrument: { sessionId: session.id, instrument: SURVEY_INSTRUMENT } },
  });
  if (answered) return <Notice text={THANK_YOU} />;

  return (
    <main className="mx-auto max-w-2xl px-8 py-16">
      <SurveyForm token={token} />
    </main>
  );
}
