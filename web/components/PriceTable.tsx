"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Offers, type TOffers, qs } from "@/lib/api";

import { OfferRow } from "./OfferRow";
import { type Mode, SortTabs } from "./SortTabs";

const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "";

async function fetchOffers(slug: string, p: Record<string, string | number | boolean>): Promise<TOffers> {
  const res = await fetch(`${PUBLIC_API}/v1/components/${encodeURIComponent(slug)}/offers${qs(p)}`);
  if (!res.ok) throw new Error(`offers ${res.status}`);
  return Offers.parse(await res.json());
}

/**
 * The full offer table. Server-rendered with the default view (Best overall, BD) so crawlers
 * and no-JS users get every price; tabs / filters re-query the API client-side.
 */
export function PriceTable({
  slug,
  initial,
  country,
  city,
  currency,
  limit,
  useInitial = true,
}: {
  slug: string;
  initial: TOffers;
  country: string;
  city: string | null;
  currency: string;
  limit?: number;
  useInitial?: boolean;
}) {
  const [mode, setMode] = useState<Mode>("best");
  const [localOnly, setLocalOnly] = useState(false);
  const [qty, setQty] = useState(1);
  const isInitial = useInitial && mode === "best" && !localOnly && qty === 1;
  const params = { mode, local_only: localOnly, qty, country, city: city ?? "", currency };
  const q = useQuery({
    queryKey: ["offers", slug, params],
    queryFn: () => fetchOffers(slug, params),
    initialData: isInitial ? initial : undefined,
    staleTime: 60_000,
  });
  const data = q.data ?? initial;
  const offers = limit ? data.offers.slice(0, limit) : data.offers;
  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <SortTabs value={mode} onChange={setMode} />
        {country === "BD" ? (
          <button
            type="button"
            aria-pressed={localOnly}
            onClick={() => setLocalOnly((v) => !v)}
            className={`min-h-11 rounded-full border px-3 text-sm ${localOnly ? "border-accent bg-accent-soft text-ink" : "border-line text-ink-soft"}`}
          >
            <span aria-hidden>🇧🇩 </span>Local only (ships from Bangladesh)
          </button>
        ) : null}
        <label className="ml-auto flex items-center gap-2 text-sm text-ink-soft">
          Qty
          <input
            type="number"
            min={1}
            max={100000}
            value={qty}
            onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))}
            className="h-11 w-24 rounded-lg border border-line bg-surface px-2 text-ink"
          />
        </label>
      </div>
      {q.isError ? <p role="alert" className="mb-2 text-sm text-warn">Couldn&apos;t refresh offers; showing the last loaded prices.</p> : null}
      {offers.length === 0 ? (
        <p className="rounded-xl border border-line p-6 text-sm text-ink-soft">
          No offers ship to {data.city ? `${data.city}, ` : ""}
          {data.country} right now{localOnly ? " from local shops" : ""}.
        </p>
      ) : (
        <ul className="rounded-xl border border-line" aria-busy={q.isFetching} aria-live="polite">
          {offers.map((o, i) => (
            <OfferRow key={o.listing_id} offer={o} highlight={i === 0} />
          ))}
        </ul>
      )}
      <p className="mt-2 text-xs text-ink-soft">
        Landed price = item + shipping + estimated import duty, per unit, in {data.currency} (FX {data.fx_day}). Duty is an
        estimate. Prices link to the seller; VoltFind does not sell anything.
      </p>
    </div>
  );
}
