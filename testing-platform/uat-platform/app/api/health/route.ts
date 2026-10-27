import { connection } from "next/server";
import { buildVersion } from "@/lib/build";
import { TASK_VERSION } from "@/lib/domain/task";
import { EVALUATOR_VERSION } from "@/lib/evaluator/evaluate";
import { defaults, defaultsHash, fixture, fixtureHash } from "@/lib/fixtures";

// Deployment check. Reports the build and the frozen files without touching
// the database or any participant data.
export async function GET() {
  await connection();
  return Response.json({
    status: "ok",
    buildVersion: buildVersion(),
    fixtureVersion: fixture.fixtureVersion,
    fixtureHash,
    defaultsVersion: defaults.defaultsVersion,
    defaultsHash,
    taskVersion: TASK_VERSION,
    evaluatorVersion: EVALUATOR_VERSION,
  });
}
