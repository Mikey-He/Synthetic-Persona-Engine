import { buildVersion } from "@/lib/build";
import { db } from "@/lib/db";
import { countOf, settingTimes } from "@/lib/metrics";
import { fixtureHash } from "@/lib/fixtures";
import { sessionEvaluation } from "@/lib/scoring";
import { SURVEY_INSTRUMENT } from "@/lib/survey";

// Server only. Every export carries the build version and the first 8
// characters of the fixture hash in its file name, so exports from different
// builds are never merged by accident.

export const EXPORT_FILES = {
  "events.json": { kind: "events", contentType: "application/json" },
  "sessions.csv": { kind: "sessions", contentType: "text/csv; charset=utf-8" },
  "agent_steps.csv": { kind: "agent_steps", contentType: "text/csv; charset=utf-8" },
} as const;

export type ExportFile = keyof typeof EXPORT_FILES;

export function exportFileName(file: ExportFile) {
  const [, extension] = file.split(".");
  return `${EXPORT_FILES[file].kind}_build-${buildVersion()}_fx-${fixtureHash.slice(0, 8)}.${extension}`;
}

// Column order exactly as in docs/build-plan.md (Exports and analysis handoff).
export const SESSION_COLUMNS = [
  "session_id", "actor_type", "variant", "dataset_label", "familiarity_band", "model_id",
  "prompt_version", "persona_id", "calibration_id", "fixture_version", "build_version",
  "evaluator_version", "termination_reason", "overall_success", "crit_scope", "crit_period",
  "crit_amount", "crit_alert", "crit_recipients", "crit_persistence", "resolved_recipient_ids",
  "recipient_mechanisms", "time_scope_ms", "time_period_ms", "time_amount_ms", "time_alert_ms",
  "time_recipients_ms", "setting_returns", "review_edits", "n_events", "n_saves",
  "reopened_after_save", "survey_satisfaction",
] as const;

export const AGENT_STEP_COLUMNS = [
  "session_id", "step_no", "screenshot_path", "action", "reason", "executed", "error_label", "latency_ms",
] as const;

function csvCell(value: unknown) {
  if (value === null || value === undefined) return "";
  const text = typeof value === "object" ? JSON.stringify(value) : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: readonly string[], rows: Record<string, unknown>[]) {
  const lines = [columns.join(","), ...rows.map((row) => columns.map((c) => csvCell(row[c])).join(","))];
  return `${lines.join("\n")}\n`;
}

export async function eventsJson() {
  const sessions = await db.session.findMany({
    orderBy: { createdAt: "asc" },
    select: { id: true, events: { orderBy: { seq: "asc" } } },
  });
  return {
    build_version: buildVersion(),
    fixture_hash: fixtureHash,
    sessions: sessions.map((session) => ({
      session_id: session.id,
      events: session.events.map((event) => ({
        seq: event.seq,
        type: event.type,
        client_ts: event.clientTs.toISOString(),
        server_ts: event.serverTs.toISOString(),
        target: event.target,
        payload: event.payload,
        screenshot_ref: event.screenshotRef,
      })),
    })),
  };
}

export async function sessionRows() {
  const sessions = await db.session.findMany({
    orderBy: { createdAt: "asc" },
    include: {
      participant: true,
      agentRun: true,
      events: { orderBy: { seq: "asc" }, select: { type: true, clientTs: true, payload: true } },
      surveyResponses: { where: { instrument: SURVEY_INSTRUMENT } },
      _count: { select: { budgets: true } },
    },
  });

  const rows: Record<string, unknown>[] = [];
  for (const session of sessions) {
    const { evaluation } = await sessionEvaluation(session.id);
    const criteria = (evaluation?.criteria ?? {}) as Record<string, boolean>;
    const people = (evaluation?.resolvedRecipients ?? []) as { id: string; via: string }[];
    const times = settingTimes(session.events);
    const survey = session.surveyResponses[0]?.answers as { ease?: number } | undefined;
    // review_edits exists only for sessions that went through guided screens.
    const guided = session.events.some((event) => event.type === "screen_viewed");
    rows.push({
      session_id: session.id,
      actor_type: session.actorType,
      variant: session.variant,
      dataset_label: session.datasetLabel,
      familiarity_band: session.participant?.familiarityBand,
      model_id: session.agentRun?.modelId,
      prompt_version: session.agentRun?.promptVersion,
      persona_id: session.agentRun?.personaId,
      calibration_id: session.agentRun?.calibrationId,
      fixture_version: session.fixtureVersion,
      build_version: session.buildVersion,
      evaluator_version: evaluation?.evaluatorVersion,
      termination_reason: session.terminationReason,
      overall_success: evaluation?.overallSuccess,
      crit_scope: criteria.scope,
      crit_period: criteria.period,
      crit_amount: criteria.amount,
      crit_alert: criteria.alert,
      crit_recipients: criteria.recipients,
      crit_persistence: criteria.persistence,
      resolved_recipient_ids: evaluation ? people.map((p) => p.id).join(";") : null,
      recipient_mechanisms: evaluation ? people.map((p) => `${p.id}:${p.via}`).join(";") : null,
      time_scope_ms: times.scope,
      time_period_ms: times.period,
      time_amount_ms: times.amount,
      time_alert_ms: times.alert,
      time_recipients_ms: times.recipients,
      setting_returns: countOf(session.events, "setting_returned"),
      review_edits: guided ? countOf(session.events, "review_edit") : null,
      n_events: session.events.length,
      n_saves: session._count.budgets,
      reopened_after_save: countOf(session.events, "budget_reopened") > 0,
      survey_satisfaction: survey?.ease,
    });
  }
  return rows;
}

export async function agentStepRows() {
  const steps = await db.agentStep.findMany({ orderBy: [{ sessionId: "asc" }, { stepNo: "asc" }] });
  return steps.map((step) => ({
    session_id: step.sessionId,
    step_no: step.stepNo,
    screenshot_path: step.screenshotPath,
    action: step.action,
    reason: step.reason,
    executed: step.executed,
    error_label: step.errorLabel,
    latency_ms: step.latencyMs,
  }));
}
