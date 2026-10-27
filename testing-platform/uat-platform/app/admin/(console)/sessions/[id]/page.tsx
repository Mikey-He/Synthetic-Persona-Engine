import { notFound } from "next/navigation";
import { formatTime, passFail, sinceStart, statusOf } from "@/components/admin/format";
import { EndSessionButton } from "@/components/admin/forms";
import { db } from "@/lib/db";
import type { Recipient } from "@/lib/domain/types";
import { sessionEvaluation } from "@/lib/scoring";

type Props = { params: Promise<{ id: string }> };

const CRITERIA = ["scope", "period", "amount", "alert", "recipients", "persistence"] as const;

export default async function SessionDetailPage({ params }: Props) {
  const { id } = await params;
  const session = await db.session.findUnique({
    where: { id },
    include: { participant: true, agentRun: true, events: { orderBy: { seq: "asc" } } },
  });
  if (!session) notFound();

  const { scored, evaluation } = await sessionEvaluation(id);
  const criteria = (evaluation?.criteria ?? {}) as Record<string, boolean>;
  const people = (evaluation?.resolvedRecipients ?? []) as Recipient[];
  const firstAt = session.events[0]?.clientTs.getTime() ?? 0;

  const facts: [string, string][] = [
    ["Participant link", session.actorType === "human" ? `/s/${session.token}` : `/s/${session.token}/billing`],
    ["Actor type", session.actorType],
    ["Variant", session.variant],
    ["Dataset label", session.datasetLabel],
    ["Familiarity band", session.participant?.familiarityBand ?? "—"],
    ["Model ID", session.agentRun?.modelId ?? "—"],
    ["Prompt version", session.agentRun?.promptVersion ?? "—"],
    ["Persona ID", session.agentRun?.personaId ?? "—"],
    ["Calibration ID", session.agentRun?.calibrationId ?? "—"],
    ["Versions", `${session.fixtureVersion} · ${session.defaultsVersion} · ${session.taskVersion} · build ${session.buildVersion} · ${session.evaluatorVersion}`],
    ["Viewport and zoom", session.viewport ? `${JSON.stringify(session.viewport)} at ${session.zoom}` : "—"],
    ["Created", formatTime(session.createdAt)],
    ["Started", formatTime(session.startedAt)],
    ["Ended", formatTime(session.endedAt)],
    ["Status", statusOf(session)],
    ["Termination reason", session.terminationReason ?? "—"],
  ];

  return (
    <>
      <div className="flex items-center gap-4">
        <h1 className="page-title">Session {session.id}</h1>
        {!session.endedAt && <EndSessionButton sessionId={session.id} />}
      </div>
      <dl className="mt-4 grid max-w-4xl grid-cols-[200px_1fr] gap-x-6 gap-y-1">
        {facts.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted">{label}</dt>
            <dd className="break-all">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-8 flex items-start gap-8">
        <section className="min-w-0 flex-1">
          <h2 className="text-[16px] font-medium">Event timeline</h2>
          <table className="data-table mt-2 text-[12px]">
            <thead>
              <tr>
                <th>Seq</th>
                <th>Type</th>
                <th>Since start</th>
                <th>Target</th>
                <th>Payload</th>
              </tr>
            </thead>
            <tbody>
              {session.events.map((event) => (
                <tr key={event.id} className="align-top">
                  <td>{event.seq}</td>
                  <td className="whitespace-nowrap">{event.type}</td>
                  <td className="whitespace-nowrap">{sinceStart(event.clientTs.getTime() - firstAt)}</td>
                  <td className="break-all">{event.target ?? ""}</td>
                  <td className="break-all font-mono">{event.payload === null ? "" : JSON.stringify(event.payload)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <aside className="w-[420px] shrink-0 space-y-6">
          <section>
            <h2 className="text-[16px] font-medium">Scored budget</h2>
            <p className="mt-1 text-muted">
              {scored.saved ? `Budget ${scored.budgetId}, version ${scored.version}` : "Nothing saved: the last draft"}
            </p>
            <pre className="mt-2 max-h-96 overflow-auto rounded border border-line bg-surface p-3 text-[12px]">
              {JSON.stringify(scored.config, null, 2)}
            </pre>
          </section>
          <section>
            <h2 className="text-[16px] font-medium">Evaluation</h2>
            {evaluation ? (
              <>
                <p className="mt-1 text-muted">
                  {evaluation.evaluatorVersion} · {formatTime(evaluation.createdAt)}
                </p>
                <table className="data-table mt-2">
                  <tbody>
                    {CRITERIA.map((criterion) => (
                      <tr key={criterion}>
                        <td>{criterion}</td>
                        <td>{passFail(criteria[criterion])}</td>
                      </tr>
                    ))}
                    <tr>
                      <td className="font-medium">overall</td>
                      <td className="font-medium">{passFail(evaluation.overallSuccess)}</td>
                    </tr>
                  </tbody>
                </table>
                <h3 className="mt-4 font-medium">Resolved recipients</h3>
                {people.length === 0 ? (
                  <p className="text-muted">Nobody</p>
                ) : (
                  <ul className="mt-1">
                    {people.map((person) => (
                      <li key={person.id}>
                        {person.name} · {person.via}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <p className="mt-1 text-muted">Not scored yet.</p>
            )}
          </section>
        </aside>
      </div>
    </>
  );
}
