import Link from "next/link";

import type { TCard } from "@/lib/api";
import { usdMinor } from "@/lib/format";

export function ComponentCard({ c }: { c: TCard }) {
  const price = usdMinor(c.lowest_price_usd_minor);
  return (
    <Link href={`/component/${c.slug}`} className="flex h-full flex-col rounded-xl border border-line p-4 hover:border-accent" data-testid="component-card">
      <span className="font-mono text-sm font-semibold">{c.mpn}</span>
      <span className="mt-1 line-clamp-2 text-sm text-ink-soft">{c.title}</span>
      <span className="mt-auto pt-3 text-sm">
        {price ? <>from <strong className="tabular-nums">{price}</strong></> : <span className="text-ink-soft">No price yet</span>}
        <span className="text-xs text-ink-soft"> · {c.offer_count} offer{c.offer_count === 1 ? "" : "s"}</span>
      </span>
    </Link>
  );
}

export function AlternativesGrid({ items, title }: { items: TCard[]; title?: string }) {
  if (items.length === 0) return <p className="text-sm text-ink-soft">No close alternatives found yet.</p>;
  return (
    <ul className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label={title}>
      {items.map((c) => <li key={c.slug}><ComponentCard c={c} /></li>)}
    </ul>
  );
}
