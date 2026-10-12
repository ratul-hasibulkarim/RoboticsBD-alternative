// W1/W2 benchmark (not a merge gate — needs a deployed URL and Chrome).
//   LHCI_URL=https://preview.voltfind.com node scripts/lighthouse-ci.js
// Thresholds: Perf ≥ 90, SEO = 100, a11y ≥ 95, Best Practices ≥ 95, LCP < 2.0 s, CLS < 0.1.
import { spawnSync } from "node:child_process";

const base = process.env.LHCI_URL;
if (!base) {
  console.error("set LHCI_URL to a deployed site");
  process.exit(2);
}
const pages = ["/", "/component/esp32-wroom-32e", "/category/mcu", "/search?q=esp32"];
const min = { performance: 0.9, seo: 1, accessibility: 0.95, "best-practices": 0.95 };
let failed = false;
for (const p of pages) {
  const r = spawnSync("npx", ["--yes", "lighthouse@12.2.1", base + p, "--quiet", "--output=json", "--chrome-flags=--headless=new",
    "--preset=perf", "--form-factor=mobile", "--throttling-method=simulate", "--only-categories=performance,seo,accessibility,best-practices"],
    { encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  if (r.status !== 0) { console.error(r.stderr); process.exit(1); }
  const lhr = JSON.parse(r.stdout);
  const lcp = lhr.audits["largest-contentful-paint"].numericValue / 1000;
  const cls = lhr.audits["cumulative-layout-shift"].numericValue;
  const scores = Object.fromEntries(Object.entries(lhr.categories).map(([k, v]) => [k, v.score]));
  const bad = Object.entries(min).filter(([k, v]) => (scores[k] ?? 0) < v).map(([k]) => k);
  if (lcp >= 2.0) bad.push(`LCP ${lcp.toFixed(2)}s`);
  if (cls >= 0.1) bad.push(`CLS ${cls.toFixed(3)}`);
  console.log(`${bad.length ? "FAIL" : "ok  "} ${p} ${JSON.stringify(scores)} LCP=${lcp.toFixed(2)}s CLS=${cls.toFixed(3)} ${bad.join(", ")}`);
  failed ||= bad.length > 0;
}
process.exit(failed ? 1 : 0);
