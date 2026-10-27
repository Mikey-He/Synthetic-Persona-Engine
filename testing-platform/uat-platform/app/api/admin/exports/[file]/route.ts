import { isAdmin, unauthorized } from "@/lib/admin";
import {
  AGENT_STEP_COLUMNS,
  EXPORT_FILES,
  SESSION_COLUMNS,
  agentStepRows,
  eventsJson,
  exportFileName,
  sessionRows,
  toCsv,
  type ExportFile,
} from "@/lib/exports";

type Context = { params: Promise<{ file: string }> };

export async function GET(_request: Request, { params }: Context) {
  if (!(await isAdmin())) return unauthorized();
  const { file } = await params;
  if (!(file in EXPORT_FILES)) return new Response(null, { status: 404 });
  const name = file as ExportFile;

  const body =
    name === "events.json"
      ? JSON.stringify(await eventsJson(), null, 2)
      : name === "sessions.csv"
        ? toCsv(SESSION_COLUMNS, await sessionRows())
        : toCsv(AGENT_STEP_COLUMNS, await agentStepRows());

  return new Response(body, {
    headers: {
      "Content-Type": EXPORT_FILES[name].contentType,
      "Content-Disposition": `attachment; filename="${exportFileName(name)}"`,
      "Cache-Control": "no-store",
    },
  });
}
