// Replays real API responses exported by scripts/export_web_fixtures.py.
// Used by `site-check` (W4–W6) so the SSR/SEO checks run without Postgres/Python.
import { readFileSync } from "node:fs";
import { createServer } from "node:http";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "tests", "fixtures", "api");
const index = JSON.parse(readFileSync(join(dir, "index.json"), "utf8"));

const norm = (u) => {
  const url = new URL(u, "http://x");
  const params = [...url.searchParams.entries()].sort(([a], [b]) => a.localeCompare(b));
  return url.pathname + (params.length ? "?" + new URLSearchParams(params).toString() : "");
};
const table = new Map(Object.entries(index).map(([path, v]) => [norm(path), v]));

export function startMockApi(port = Number(process.env.MOCK_API_PORT ?? 8765)) {
  const server = createServer((req, res) => {
    const hit = table.get(norm(req.url ?? "/"));
    if (req.method === "POST" && /\/view$/.test(req.url ?? "")) { res.writeHead(204).end(); return; }
    // Click-out: the real API 302s to the seller; the mock sends to a local landing page.
    if (/^\/go\//.test(req.url ?? "")) { res.writeHead(302, { location: `http://127.0.0.1:${port}/landing` }).end(); return; }
    if (req.url === "/landing") { res.writeHead(200, { "content-type": "text/html" }).end("<!doctype html><title>Seller</title><h1>Seller page</h1>"); return; }
    if (!hit) {
      res.writeHead(404, { "content-type": "application/json" }).end(JSON.stringify({ detail: "not found" }));
      return;
    }
    res.writeHead(hit.status, { "content-type": "application/json" }).end(readFileSync(join(dir, hit.file)));
  });
  return new Promise((resolve) => server.listen(port, "127.0.0.1", () => resolve(server)));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  startMockApi().then(() => console.log("mock API on", process.env.MOCK_API_PORT ?? 8765));
}
