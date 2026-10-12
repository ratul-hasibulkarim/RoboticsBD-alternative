import { NextResponse, type NextRequest } from "next/server";

/**
 * Retired parts must answer 410 Gone (§10.3) — App Router pages can only 404, so the
 * middleware checks a small cached list of retired slugs from the API.
 */
const API_URL = process.env.API_URL ?? "http://localhost:8000";
let retired: Set<string> = new Set();
let loadedAt = 0;

async function retiredSlugs(): Promise<Set<string>> {
  if (Date.now() - loadedAt < 10 * 60_000) return retired;
  try {
    const res = await fetch(`${API_URL}/v1/sitemap/retired`, { cache: "no-store" });
    if (res.ok) {
      const body: unknown = await res.json();
      if (Array.isArray(body)) retired = new Set(body.filter((x): x is string => typeof x === "string"));
    }
  } catch {
    // keep the previous list; never block page rendering on this
  }
  loadedAt = Date.now();
  return retired;
}

export async function middleware(req: NextRequest) {
  const slug = req.nextUrl.pathname.split("/")[2];
  if (slug && (await retiredSlugs()).has(slug)) {
    return new NextResponse(
      `<!doctype html><html lang="en"><head><meta name="robots" content="noindex"><title>Part retired</title></head><body><h1>This part has been retired</h1><p><a href="/">Search VoltFind</a></p></body></html>`,
      { status: 410, headers: { "content-type": "text/html; charset=utf-8" } },
    );
  }
  return NextResponse.next();
}

export const config = { matcher: ["/component/:slug*"] };
