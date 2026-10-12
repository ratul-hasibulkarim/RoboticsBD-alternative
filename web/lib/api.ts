/**
 * Typed API client. Every response is validated with Zod at runtime (spec §15) so a
 * contract drift fails loudly in CI (web/tests/contract.test.ts) instead of rendering junk.
 */
import { z } from "zod";

export const API_URL = process.env.API_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const Money = z.object({ amount: z.string(), currency: z.string(), usd_minor: z.number().int() });
const SourceRef = z.object({ name: z.string(), display_name: z.string(), domain: z.string(), trust_score: z.number() });

export const Offer = z.object({
  listing_id: z.string(),
  source: SourceRef,
  url: z.string(),
  go_url: z.string(),
  sponsored: z.boolean(),
  title: z.string(),
  condition: z.string(),
  in_stock: z.boolean().nullable(),
  stock_qty: z.number().int().nullable(),
  moq: z.number().int(),
  quantity: z.number().int(),
  unit_price: Money,
  landed_total: Money,
  landed_per_unit: Money,
  shipping: Money,
  duty_estimate: Money,
  eta_days: z.number(),
  distance_km: z.number().nullable(),
  ships_from: z.string().nullable(),
  observed_at: z.string(),
  freshness: z.enum(["fresh", "recent", "stale"]),
  score: z.number(),
});

export const Offers = z.object({
  component_slug: z.string(),
  mode: z.enum(["best", "cheapest", "fastest"]),
  quantity: z.number().int(),
  currency: z.string(),
  country: z.string(),
  city: z.string().nullable(),
  local_only: z.boolean(),
  offers: z.array(Offer),
  total: z.number().int(),
  fx_day: z.string(),
});

export const Card = z.object({
  slug: z.string(),
  mpn: z.string(),
  title: z.string(),
  manufacturer: z.string().nullable(),
  category: z.string(),
  subcategory: z.string().nullable(),
  package: z.string().nullable(),
  image_url: z.string().nullable(),
  lowest_price_usd_minor: z.number().int().nullable(),
  offer_count: z.number().int(),
});

const ImageOut = z.object({
  url: z.string(),
  width: z.number().int().nullable(),
  height: z.number().int().nullable(),
  attribution: z.string(),
  license: z.string(),
});

const Datasheet = z.object({
  url: z.string(),
  host: z.string(),
  revision: z.string().nullable(),
  page_count: z.number().int().nullable(),
  language: z.string().nullable(),
  is_primary: z.boolean(),
  checked_at: z.string(),
});

export const UseCase = z.object({
  id: z.string(),
  slug: z.string(),
  title: z.string(),
  difficulty: z.string().nullable(),
  summary: z.string(),
  steps: z.array(z.string()),
  thumbnail_url: z.string().nullable(),
  code_language: z.string().nullable(),
  code_snippet: z.string().nullable(),
  code_license: z.string().nullable(),
  source_type: z.string(),
  source_url: z.string(),
  source_author: z.string().nullable(),
  source_license: z.string().nullable(),
  upvotes: z.number().int(),
});

export const ComponentDetail = z.object({
  id: z.string(),
  slug: z.string(),
  mpn: z.string(),
  title: z.string(),
  manufacturer: z.string().nullable(),
  category: z.string(),
  subcategory: z.string().nullable(),
  package: z.string().nullable(),
  lifecycle: z.string(),
  short_desc: z.string().nullable(),
  prose_md: z.string().nullable(),
  prose_reviewed: z.boolean(),
  specs: z.record(z.string(), z.string()),
  images: z.array(ImageOut),
  datasheets: z.array(Datasheet),
  use_cases: z.array(UseCase),
  alternatives: z.array(Card),
  related: z.array(Card),
  history: z.array(z.object({ day: z.string(), min_usd_minor: z.number().int() })),
  offer_summary: Offers,
  low_price: Money.nullable(),
  high_price: Money.nullable(),
  offer_count: z.number().int(),
  faq: z.array(z.object({ question: z.string(), answer: z.string() })),
  breadcrumbs: z.array(z.object({ name: z.string(), path: z.string() })),
  updated_at: z.string(),
});

export const SearchHit = z.object({
  id: z.string(),
  slug: z.string(),
  mpn: z.string(),
  title: z.string(),
  manufacturer: z.string().nullable(),
  category: z.string(),
  package: z.string().nullable(),
  lowest_price_usd_minor: z.number().int().nullable(),
  offer_count: z.number().int(),
  in_stock: z.boolean(),
  ships_to_bd: z.boolean(),
  image_url: z.string().nullable(),
});

export const SearchResponse = z.object({
  query: z.string(),
  kind: z.string(),
  hits: z.array(SearchHit),
  found: z.number().int(),
  page: z.number().int(),
  per_page: z.number().int(),
  facets: z.record(z.string(), z.array(z.tuple([z.string(), z.number().int()]))),
  backend: z.string(),
  took_ms: z.number(),
  message: z.string().nullable(),
  discovery_queued: z.boolean(),
});

export const Paged = z.object({ items: z.array(Card), total: z.number().int(), page: z.number().int(), per_page: z.number().int() });
export const Categories = z.array(z.object({ category: z.string(), count: z.number().int() }));
export const Manufacturers = z.array(z.object({ manufacturer: z.string(), slug: z.string(), count: z.number().int() }));
export const SitemapEntries = z.array(z.object({ slug: z.string(), updated_at: z.string(), image_url: z.string().nullable() }));
export const SitemapCount = z.object({ components: z.number().int(), per_file: z.number().int() });
export const Compare = z.object({ components: z.array(ComponentDetail), spec_keys: z.array(z.string()) });
export const History = z.array(z.object({ day: z.string(), min_usd_minor: z.number().int() }));

export type TOffer = z.infer<typeof Offer>;
export type TOffers = z.infer<typeof Offers>;
export type TCard = z.infer<typeof Card>;
export type TComponent = z.infer<typeof ComponentDetail>;
export type TUseCase = z.infer<typeof UseCase>;
export type TSearch = z.infer<typeof SearchResponse>;

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: unknown,
  ) {
    super(`API ${status}`);
  }
}

export type Gone = { status: "merged" | "retired"; redirect_to: string | null };

const GoneBody = z.object({ detail: z.object({ status: z.enum(["merged", "retired"]), redirect_to: z.string().nullable() }) });

export function goneInfo(err: unknown): Gone | null {
  if (!(err instanceof ApiError) || (err.status !== 301 && err.status !== 410)) return null;
  const parsed = GoneBody.safeParse(err.body);
  return parsed.success ? parsed.data.detail : null;
}

type FetchOpts = { revalidate?: number | false; headers?: Record<string, string>; tags?: string[] };

export async function apiGet<T>(path: string, schema: z.ZodType<T>, opts: FetchOpts = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    headers: { accept: "application/json", ...opts.headers },
    redirect: "manual",
    next: opts.revalidate === false ? undefined : { revalidate: opts.revalidate ?? 3600, tags: opts.tags },
    cache: opts.revalidate === false ? "no-store" : undefined,
  });
  if (!res.ok) {
    let body: unknown = null;
    try {
      body = await res.json();
    } catch {
      body = null;
    }
    throw new ApiError(res.status, body);
  }
  return schema.parse(await res.json());
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== "") u.set(k, String(v));
  const s = u.toString();
  return s ? `?${s}` : "";
}

export const getComponent = (slug: string, geo: GeoParams) =>
  apiGet(`/v1/components/${encodeURIComponent(slug)}${qs({ ...geo, track: false })}`, ComponentDetail, {
    tags: [`component:${slug}`],
  });

export const getOffers = (slug: string, p: GeoParams & { mode?: string; qty?: number; local_only?: boolean; page?: number }) =>
  apiGet(`/v1/components/${encodeURIComponent(slug)}/offers${qs(p)}`, Offers, { tags: [`component:${slug}`] });

export type GeoParams = { country?: string; city?: string; currency?: string };
