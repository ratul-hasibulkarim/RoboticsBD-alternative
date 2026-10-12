/**
 * JSON-LD builders (§10.2), typed with schema-dts so a wrong property is a compile error.
 * FAQPage / HowTo are emitted as valid markup but are not relied on for rich results (spec v1.1 row 8).
 */
import type {
  AggregateOffer,
  BreadcrumbList,
  Dataset,
  FAQPage,
  HowTo,
  ItemAvailability,
  Organization,
  Product,
  WebSite,
  WithContext,
} from "schema-dts";

import type { TComponent, TUseCase } from "./api";
import { SITE_NAME, absolute } from "./site";

export type JsonLd =
  | WithContext<Product>
  | WithContext<BreadcrumbList>
  | WithContext<FAQPage>
  | WithContext<HowTo>
  | WithContext<Organization>
  | WithContext<WebSite>
  | WithContext<Dataset>;

const IN_STOCK: ItemAvailability = "https://schema.org/InStock";
const OUT_OF_STOCK: ItemAvailability = "https://schema.org/OutOfStock";

export function productJsonLd(c: TComponent): WithContext<Product> {
  const url = absolute(`/component/${c.slug}`);
  const anyInStock = c.offer_summary.offers.some((o) => o.in_stock !== false);
  const product: WithContext<Product> = {
    "@context": "https://schema.org",
    "@type": "Product",
    "@id": `${url}#product`,
    name: c.title,
    mpn: c.mpn,
    sku: c.mpn,
    url,
    category: c.category,
    description: c.short_desc ?? `${c.mpn}${c.manufacturer ? ` by ${c.manufacturer}` : ""}: prices, datasheet and tutorials.`,
    image: c.images.map((i) => i.url),
    additionalProperty: Object.entries(c.specs)
      .slice(0, 20)
      .map(([name, value]) => ({ "@type": "PropertyValue" as const, name, value })),
  };
  if (c.manufacturer) {
    product.brand = { "@type": "Brand", name: c.manufacturer };
    product.manufacturer = { "@type": "Organization", name: c.manufacturer };
  }
  if (c.low_price && c.high_price && c.offer_count > 0) {
    const offers: AggregateOffer = {
      "@type": "AggregateOffer",
      priceCurrency: c.low_price.currency,
      lowPrice: c.low_price.amount,
      highPrice: c.high_price.amount,
      offerCount: c.offer_count,
      availability: anyInStock ? IN_STOCK : OUT_OF_STOCK,
      url,
    };
    product.offers = offers;
  }
  return product;
}

export function breadcrumbJsonLd(c: Pick<TComponent, "breadcrumbs">): WithContext<BreadcrumbList> {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: c.breadcrumbs.map((b, i) => ({
      "@type": "ListItem" as const,
      position: i + 1,
      name: b.name,
      item: absolute(b.path),
    })),
  };
}

export function faqJsonLd(c: Pick<TComponent, "faq">): WithContext<FAQPage> | null {
  if (c.faq.length === 0) return null;
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: c.faq.map((f) => ({
      "@type": "Question" as const,
      name: f.question,
      acceptedAnswer: { "@type": "Answer" as const, text: f.answer },
    })),
  };
}

export function howToJsonLd(u: TUseCase, componentName: string): WithContext<HowTo> {
  return {
    "@context": "https://schema.org",
    "@type": "HowTo",
    name: u.title,
    description: u.summary,
    tool: [{ "@type": "HowToTool", name: componentName }],
    step: (u.steps.length > 0 ? u.steps : [u.summary]).map((text, i) => ({
      "@type": "HowToStep" as const,
      position: i + 1,
      text,
    })),
    isBasedOn: u.source_url,
  };
}

export function organizationJsonLd(): WithContext<Organization> {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: absolute("/"),
    logo: absolute("/icon.svg"),
  };
}

export function websiteJsonLd(): WithContext<WebSite> {
  // SearchAction's query-input is not in schema-dts' Action type; it is spread in as an extension.
  const site: WithContext<WebSite> = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: absolute("/"),
    potentialAction: {
      "@type": "SearchAction",
      target: { "@type": "EntryPoint", urlTemplate: absolute("/search?q={search_term_string}") },
      ...{ "query-input": "required name=search_term_string" },
    },
  };
  return site;
}

export function priceDatasetJsonLd(c: TComponent): WithContext<Dataset> | null {
  if (c.history.length < 2) return null;
  const first = c.history[0];
  const last = c.history[c.history.length - 1];
  if (!first || !last) return null;
  return {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: `${c.mpn} price history`,
    description: `Daily lowest observed landed price (USD) for ${c.mpn} across ${c.offer_count} sources.`,
    url: absolute(`/component/${c.slug}/prices`),
    temporalCoverage: `${first.day}/${last.day}`,
    creator: { "@type": "Organization", name: SITE_NAME },
    isAccessibleForFree: true,
    variableMeasured: "lowest landed price (USD)",
  };
}

/** Serialise for <script type="application/ld+json">, escaping "<" so the content can't close the tag. */
export function jsonLdString(data: JsonLd): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

export function componentDescription(c: TComponent): string {
  const price = c.low_price ? ` from ${c.low_price.currency} ${c.low_price.amount}` : "";
  const parts = [
    `${c.mpn}${c.manufacturer ? ` (${c.manufacturer})` : ""}`,
    `compare ${c.offer_count} price${c.offer_count === 1 ? "" : "s"}${price}`,
    c.datasheets.length ? "datasheet" : null,
    c.use_cases.length ? "wiring & code examples" : null,
  ].filter(Boolean);
  return `${parts.join(" · ")}. Lowest landed price with shipping to Bangladesh and worldwide.`.slice(0, 160);
}
