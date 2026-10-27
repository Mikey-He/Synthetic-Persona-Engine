import { isAdmin, unauthorized } from "@/lib/admin";
import { EVALUATOR_VERSION } from "@/lib/evaluator/evaluate";
import { rescoreAll } from "@/lib/scoring";

// Adds a new Evaluation row for every stored session with the current
// evaluator. Earlier rows stay as they are.
export async function POST() {
  if (!(await isAdmin())) return unauthorized();
  const sessions = await rescoreAll();
  return Response.json({ sessions, evaluatorVersion: EVALUATOR_VERSION });
}
