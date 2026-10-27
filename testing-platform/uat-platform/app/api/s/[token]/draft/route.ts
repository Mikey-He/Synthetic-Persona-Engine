import { liveSession } from "@/lib/api";
import { putDraft } from "@/lib/budgets";
import { draftBodySchema } from "@/lib/domain/schemas";

type Context = { params: Promise<{ token: string }> };

export async function PUT(request: Request, { params }: Context) {
  const { token } = await params;
  const live = await liveSession(token);
  if ("error" in live) return live.error;

  const body = draftBodySchema.safeParse(await request.json().catch(() => null));
  if (!body.success) return new Response(null, { status: 400 });

  await putDraft(live.session.id, body.data);
  return new Response(null, { status: 204 });
}
