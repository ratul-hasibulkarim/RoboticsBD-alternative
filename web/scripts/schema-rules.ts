/**
 * Offline structured-data validation (spec v1.1 row 9 — Rich Results Test has no API).
 * Encodes Google's documented required/recommended properties for the types we emit.
 */
type Obj = Record<string, unknown>;

const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v);
const nonEmpty = (v: unknown) => v !== undefined && v !== null && v !== "" && !(Array.isArray(v) && v.length === 0);

function req(o: Obj, keys: string[], path: string, errs: string[]) {
  for (const k of keys) if (!nonEmpty(o[k])) errs.push(`${path}: missing ${k}`);
}

function isUrl(v: unknown): boolean {
  return typeof v === "string" && /^https?:\/\//.test(v);
}

/** Recommended (not required) properties — reported, never fail the build. */
export function jsonLdWarnings(data: unknown): string[] {
  if (!isObj(data)) return [];
  const w: string[] = [];
  if (data["@type"] === "Product" && !nonEmpty(data.image)) w.push("Product: image recommended");
  if (data["@type"] === "Product" && !nonEmpty(data.brand)) w.push("Product: brand recommended");
  return w;
}

export function validateJsonLd(data: unknown): string[] {
  const errs: string[] = [];
  if (!isObj(data)) return ["not an object"];
  if (data["@context"] !== "https://schema.org") errs.push("@context must be https://schema.org");
  const t = data["@type"];
  switch (t) {
    case "Product": {
      req(data, ["name", "offers"], "Product", errs);
      const offers = data.offers;
      if (isObj(offers)) {
        if (offers["@type"] === "AggregateOffer") {
          req(offers, ["lowPrice", "priceCurrency", "offerCount"], "AggregateOffer", errs);
          if (Number(offers.lowPrice) > Number(offers.highPrice)) errs.push("AggregateOffer: lowPrice > highPrice");
          if (typeof offers.priceCurrency === "string" && !/^[A-Z]{3}$/.test(offers.priceCurrency)) errs.push("priceCurrency must be ISO 4217");
        } else req(offers, ["price", "priceCurrency"], "Offer", errs);
      }
      break;
    }
    case "BreadcrumbList": {
      const items = data.itemListElement;
      if (!Array.isArray(items) || items.length === 0) errs.push("BreadcrumbList: no items");
      else items.forEach((it, i) => {
        if (!isObj(it)) return errs.push(`item ${i} not object`);
        req(it, ["position", "name"], `ListItem[${i}]`, errs);
        if (it.position !== i + 1) errs.push(`ListItem[${i}]: position should be ${i + 1}`);
        if (i < items.length - 1 && !isUrl(it.item)) errs.push(`ListItem[${i}]: item URL required`);
      });
      break;
    }
    case "FAQPage": {
      const qs = data.mainEntity;
      if (!Array.isArray(qs) || qs.length === 0) errs.push("FAQPage: no questions");
      else qs.forEach((q, i) => {
        if (!isObj(q)) return errs.push(`Question ${i} not object`);
        req(q, ["name"], `Question[${i}]`, errs);
        if (!isObj(q.acceptedAnswer) || !nonEmpty(q.acceptedAnswer.text)) errs.push(`Question[${i}]: acceptedAnswer.text required`);
      });
      break;
    }
    case "HowTo":
      req(data, ["name", "step"], "HowTo", errs);
      break;
    case "WebSite": {
      req(data, ["name", "url"], "WebSite", errs);
      const a = data.potentialAction;
      if (!isObj(a) || a["@type"] !== "SearchAction" || !nonEmpty(a["query-input"])) errs.push("WebSite: SearchAction with query-input required");
      break;
    }
    case "Organization":
      req(data, ["name", "url"], "Organization", errs);
      break;
    case "Dataset":
      req(data, ["name", "description"], "Dataset", errs);
      break;
    default:
      errs.push(`unknown @type ${String(t)}`);
  }
  return errs;
}
