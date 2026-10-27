import Link from "next/link";
import { formatTime, statusOf } from "@/components/admin/format";
import { RescoreButton } from "@/components/admin/forms";
import { db } from "@/lib/db";
import { sessionEvaluation } from "@/lib/scoring";

export default async function SessionsPage() {
  const sessions = await db.session.findMany({
    orderBy: { createdAt: "desc" },
    include: { participant: true },
  });
  const evaluations = await Promise.all(sessions.map((session) => sessionEvaluation(session.id)));

  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="page-title">Sessions</h1>
        <RescoreButton />
      </div>
      <table className="data-table mt-4">
        <thead>
          <tr>
            <th>Created</th>
            <th>Session</th>
            <th>Actor type</th>
            <th>Variant</th>
            <th>Dataset label</th>
            <th>Familiarity band</th>
            <th>Status</th>
            <th>Termination reason</th>
            <th>Evaluation</th>
          </tr>
        </thead>
        <tbody>
          {sessions.map((session, i) => {
            const evaluation = evaluations[i].evaluation;
            return (
              <tr key={session.id}>
                <td className="whitespace-nowrap">{formatTime(session.createdAt)}</td>
                <td>
                  <Link href={`/admin/sessions/${session.id}`} className="link">
                    {session.id}
                  </Link>
                </td>
                <td>{session.actorType}</td>
                <td>{session.variant}</td>
                <td>{session.datasetLabel}</td>
                <td>{session.participant?.familiarityBand ?? "—"}</td>
                <td>{statusOf(session)}</td>
                <td>{session.terminationReason ?? "—"}</td>
                <td>
                  {evaluation
                    ? `${evaluation.overallSuccess ? "Success" : "Failure"} (${evaluation.evaluatorVersion})`
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </>
  );
}
