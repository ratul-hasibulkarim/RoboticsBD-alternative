import type { Metadata } from "next";
import Link from "next/link";
import { cookies, headers } from "next/headers";

import { FilterSidebar } from "@/components/FilterSidebar";
import { NotifyForm } from "@/components/NotifyForm";
import { AdSlot } from "@/components/ads/AdSlot";
import { SearchResponse, apiGet, qs } from "@/lib/api";
import { usdMinor } from "@/lib/format";
import { geoFrom } from "@/lib/geo";
import { ADSENSE_CLIENT } from "@/lib/site";

// Parameterised search results are thin pages: never indexed (robots.txt also blocks /search?).
export const metadata: Metadata = { title: "Search", robots: { index: false, follow: true } };
export const dynamic = "force-dynamic";

type SP = Promise<Record<string, string | string[] | undefined>>;
const one = (v: string | string[] | undefined) => (Array.isArray(v) ? v[0] : v);

export default async function SearchPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const params = {
    q: one(sp.q)?.slice(0, 200), page: one(sp.page), category: one(sp.category), manufacturer: one(sp.manufacturer),
    package: one(sp.package), in_stock: one(sp.in_stock), ships_to_bd: one(sp.ships_to_bd), sort: one(sp.sort),
  };
  if (!params.q) return <p>Type a part number or keyword to search.</p>;
  const geo = geoFrom(await headers(), (await cookies()).get("vf_geo")?.value);
  const res = await apiGet(`/v1/search${qs({ ...params, country: geo.country, city: geo.city })}`, SearchResponse, {
    revalidate: false,
    headers: { "cf-ipcountry": geo.country },
  });
  const page = Number(params.page ?? 1);
  return (
    <div className="grid gap-8 md:grid-cols-[220px_1fr]">
      <FilterSidebar facets={res.facets} params={params} />
      <div>
        <h1 className="text-xl font-semibold">
          {res.found.toLocaleString()} result{res.found === 1 ? "" : "s"} for “{res.query}”
        </h1>
        <p className="text-xs text-ink-soft">{res.took_ms} ms</p>
        {res.message ? (
          <div className="mt-4 rounded-xl border border-line bg-surface-2 p-4">
            <p>{res.message}</p>
            <NotifyForm q={res.query} />
          </div>
        ) : null}
        <ul className="mt-4 divide-y divide-line rounded-xl border border-line">
          {res.hits.map((h, i) => (
            <li key={h.id}>
              <Link href={`/component/${h.slug}`} className="flex items-center justify-between gap-4 p-4 hover:bg-surface-2">
                <span className="min-w-0">
                  <span className="block font-mono font-semibold">{h.mpn}</span>
                  <span className="block truncate text-sm text-ink-soft">{h.title}{h.manufacturer ? ` · ${h.manufacturer}` : ""}</span>
                </span>
                <span className="shrink-0 text-right text-sm">
                  {usdMinor(h.lowest_price_usd_minor) ? <strong className="tabular-nums">from {usdMinor(h.lowest_price_usd_minor)}</strong> : <span className="text-ink-soft">no price yet</span>}
                  <span className="block text-xs text-ink-soft">{h.offer_count} offers{h.ships_to_bd ? " · ships to BD" : ""}</span>
                </span>
              </Link>
              {i === 7 ? (
                <AdSlot id="search-in-feed" placement="in_feed_native" template="search" client={ADSENSE_CLIENT}
                  slot={process.env.NEXT_PUBLIC_ADSENSE_SLOT_IN_FEED ?? ""} />
              ) : null}
            </li>
          ))}
        </ul>
        <nav aria-label="Pagination" className="mt-4 flex justify-between text-sm">
          {page > 1 ? <Link href={`/search${qs({ ...params, page: page - 1 })}`}>← Previous</Link> : <span />}
          {page * res.per_page < res.found ? <Link href={`/search${qs({ ...params, page: page + 1 })}`}>Next →</Link> : null}
        </nav>
      </div>
    </div>
  );
}
