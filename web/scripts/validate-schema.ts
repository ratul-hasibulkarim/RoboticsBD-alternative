/**
 * W3: validates every JSON-LD template against real API fixtures. Exit 1 on any error.
 *   npm run validate:schema
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { ComponentDetail } from "../lib/api";
import { breadcrumbJsonLd, faqJsonLd, howToJsonLd, organizationJsonLd, priceDatasetJsonLd, productJsonLd, websiteJsonLd } from "../lib/seo";
import { jsonLdWarnings, validateJsonLd } from "./schema-rules";

const dir = join(import.meta.dirname, "..", "tests", "fixtures", "api");
const index: Record<string, { file: string }> = JSON.parse(readFileSync(join(dir, "index.json"), "utf8"));
let failures = 0;
let checked = 0;

function check(label: string, data: unknown) {
  if (data === null) return;
  checked++;
  for (const w of jsonLdWarnings(data)) console.warn(`warn ${label}: ${w}`);
  const errs = validateJsonLd(data);
  if (errs.length) {
    failures++;
    console.error(`FAIL ${label}\n  - ${errs.join("\n  - ")}`);
  }
}

check("Organization", organizationJsonLd());
check("WebSite", websiteJsonLd());
for (const [path, { file }] of Object.entries(index)) {
  if (!/^\/v1\/components\/[^/?]+\?/.test(path)) continue;
  const c = ComponentDetail.parse(JSON.parse(readFileSync(join(dir, file), "utf8")));
  if (c.offer_count > 0) check(`Product ${c.slug}`, productJsonLd(c));
  check(`Breadcrumb ${c.slug}`, breadcrumbJsonLd(c));
  check(`FAQ ${c.slug}`, faqJsonLd(c));
  check(`Dataset ${c.slug}`, priceDatasetJsonLd(c));
  for (const u of c.use_cases) check(`HowTo ${c.slug}/${u.slug}`, howToJsonLd(u, c.mpn));
}
console.log(`${checked} JSON-LD blocks checked, ${failures} failed`);
process.exit(failures ? 1 : 0);
