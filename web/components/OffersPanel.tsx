"use client";

import type { TOffers } from "@/lib/api";
import { DEFAULT_GEO } from "@/lib/geo";
import { useGeo } from "@/lib/useGeo";

import { GeoBanner } from "./GeoBanner";
import { PriceTable } from "./PriceTable";

/** Geo-aware wrapper: SSR renders Dhaka/BDT; a visitor's saved location re-ranks client-side. */
export function OffersPanel({ slug, initial, limit }: { slug: string; initial: TOffers; limit?: number }) {
  const geo = useGeo(DEFAULT_GEO);
  const sameAsSsr = geo.country === initial.country && geo.currency === initial.currency && (geo.city ?? null) === (initial.city ?? null);
  return (
    <div>
      <div className="mb-3"><GeoBanner country={geo.country} city={geo.city} currency={geo.currency} /></div>
      <PriceTable key={`${geo.country}-${geo.city}-${geo.currency}`} slug={slug} initial={initial} country={geo.country}
        city={geo.city} currency={geo.currency} limit={limit} useInitial={sameAsSsr} />
    </div>
  );
}
