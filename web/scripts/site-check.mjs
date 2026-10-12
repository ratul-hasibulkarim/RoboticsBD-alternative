// W4 (SSR without JS), W5 (sitemaps), W6 (canonical uniqueness) + status codes.
// Builds and starts the real Next app against the fixture-replaying mock API.
//   node scripts/site-check.mjs            (build + check)
//   SKIP_BUILD=1 node scripts/site-check.mjs
import { spawn } from "node:child_process";

import { startMockApi } from "./mock-api.mjs";
import { startNext } from "./next-server.mjs";

const API_PORT = 8765;
const WEB_PORT = Number(process.env.WEB_PORT ?? 3100);
const SITE = "https://voltfind.test";
const BASE = `http://127.0.0.1:${WEB_PORT}`;
const env = { ...process.env, API_URL: `http://127.0.0.1:${API_PORT}`, NEXT_PUBLIC_SITE_URL: SITE, NEXT_TELEMETRY_DISABLED: "1" };
const failures = [];
const fail = (m) => { failures.push(m); console.error("FAIL", m); };
const ok = (m) => console.log("ok  ", m);

try {
  await fetch(BASE + "/robots.txt");
  console.error(`port ${WEB_PORT} is already serving something — stop it first (stale next-server?)`);
  process.exit(2);
} catch { /* free, good */ }
const mock = await startMockApi(API_PORT);
if (!process.env.SKIP_BUILD) {
  // Async spawn: the mock API lives in this process and must keep serving during the build.
  const code = await new Promise((resolve) => spawn("npx", ["next", "build"], { env, stdio: "inherit" }).on("exit", resolve));
  if (code !== 0) { mock.close(); process.exit(1); }
}
const stopWeb = await startNext(WEB_PORT, env);
const local = (u) => u.replace(SITE, BASE);
// "https://site" and "https://site/" are the same URL (RFC 3986 §6.2.3).
const sameUrl = (a, b) => a.replace(/^(https?:\/\/[^/]+)\/?$/, "$1/") === b.replace(/^(https?:\/\/[^/]+)\/?$/, "$1/");

try {
  // ---- W4: SSR — the raw HTML (no JS executed) contains price, specs, attribution and JSON-LD
  const html = await (await fetch(BASE + "/component/esp32-wroom-32")).text();
  const checks = {
    "lowest price": /৳520\.00/,
    "spec value": /3\.0V ~ 3\.6V/,
    "source attribution": /Demo Robotics BD/,
    "as-of timestamp": /as of /,
    "Product JSON-LD": /"@type":"Product"/,
    "AggregateOffer": /"@type":"AggregateOffer"/,
    "canonical": /<link rel="canonical" href="https:\/\/voltfind\.test\/component\/esp32-wroom-32"/,
    "datasheet link to publisher": /href="https:\/\/www\.espressif\.com\//,
  };
  for (const [name, re] of Object.entries(checks)) (re.test(html) ? ok : fail)(`W4 SSR contains ${name}`);
  if (/data-ad-placement/.test(html.split('id="offers"')[0] ?? "")) fail("ad markup before the offer table"); else ok("no ad above the offer table");

  // ---- status codes
  const status = async (p) => (await fetch(BASE + p, { redirect: "manual" })).status;
  ((await status("/component/does-not-exist")) === 404 ? ok : fail)("unknown component → 404");
  ((await status("/category/does-not-exist")) === 404 ? ok : fail)("unknown category → 404");
  const robots = await (await fetch(BASE + "/robots.txt")).text();
  (/Disallow: \/admin/.test(robots) && /Disallow: \/search\?/.test(robots) && /Sitemap: https:\/\/voltfind\.test\/sitemap-index\.xml/.test(robots) ? ok : fail)("robots.txt rules");

  // ---- W5: sitemaps
  const idx = await (await fetch(BASE + "/sitemap-index.xml")).text();
  const maps = [...idx.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
  (maps.length >= 4 ? ok : fail)(`W5 sitemap index lists ${maps.length} sitemaps`);
  const urls = new Set();
  for (const m of maps) {
    const res = await fetch(local(m));
    if (!res.ok) { fail(`W5 ${m} → ${res.status}`); continue; }
    const body = await res.text();
    const locs = [...body.matchAll(/<url><loc>([^<]+)<\/loc>/g)].map((x) => x[1]);
    if (locs.length > 50000) fail(`W5 ${m} has ${locs.length} > 50 000 URLs`);
    for (const l of locs) urls.add(l);
  }
  ok(`W5 ${urls.size} unique URLs across sitemaps`);

  // ---- W5 all URLs 200, W6 canonical uniqueness (each page canonicalises to itself)
  const canonicals = new Map();
  for (const u of urls) {
    const res = await fetch(local(u), { redirect: "manual" });
    if (res.status !== 200) { fail(`W5 ${u} → ${res.status}`); continue; }
    const page = await res.text();
    const canon = page.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
    if (!canon) { fail(`W6 ${u} has no canonical`); continue; }
    if (!sameUrl(canon, u)) fail(`W6 ${u} canonical points to ${canon}`);
    if (canonicals.has(canon)) fail(`W6 ${u} shares canonical with ${canonicals.get(canon)}`);
    canonicals.set(canon, u);
  }
  ok(`W5/W6 fetched ${urls.size} sitemap URLs, ${canonicals.size} unique canonicals`);

  // ---- orphans: every component in the sitemap is linked from a category/manufacturer page
  const comps = [...urls].filter((u) => /\/component\/[^/]+$/.test(u));
  const linked = new Set();
  for (const u of [...urls].filter((x) => /\/(category|manufacturer)\/[^/]+$/.test(x))) {
    const page = await (await fetch(local(u))).text();
    for (const m of page.matchAll(/href="(\/component\/[^"/]+)"/g)) linked.add(SITE + m[1]);
  }
  const orphans = comps.filter((c) => !linked.has(c));
  (orphans.length === 0 ? ok : fail)(`W5 no orphan component pages (${orphans.join(", ")})`);
} finally {
  stopWeb();
  mock.close();
}
console.log(failures.length ? `\n${failures.length} check(s) failed` : "\nall site checks passed");
process.exit(failures.length ? 1 : 0);
