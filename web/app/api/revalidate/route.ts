import { revalidatePath } from "next/cache";
import { NextResponse } from "next/server";
import { z } from "zod";

const Body = z.object({ paths: z.array(z.string().regex(/^\/component\/[a-z0-9-]+(\/[a-z-]+)?$/)).max(20) });

/** On-demand ISR (§10.1): called by the indexer when prices/extraction for a part change. */
export async function POST(req: Request) {
  const secret = process.env.REVALIDATE_SECRET;
  if (!secret || req.headers.get("x-revalidate-secret") !== secret) return NextResponse.json({ ok: false }, { status: 401 });
  const parsed = Body.safeParse(await req.json().catch(() => null));
  if (!parsed.success) return NextResponse.json({ ok: false }, { status: 422 });
  for (const p of parsed.data.paths) revalidatePath(p);
  return NextResponse.json({ ok: true, revalidated: parsed.data.paths.length });
}
