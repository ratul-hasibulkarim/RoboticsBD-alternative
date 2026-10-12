import type { Metadata } from "next";
import Link from "next/link";

import { JsonLd } from "@/components/JsonLd";
import { OffersPanel } from "@/components/OffersPanel";
import { PriceSparkline } from "@/components/PriceSparkline";
import { ReportButton } from "@/components/ReportButton";
import { SpecTable } from "@/components/SpecTable";
import { UseCaseCard } from "@/components/UseCaseCard";
import { ViewBeacon } from "@/components/ViewBeacon";
import { AdSlot } from "@/components/ads/AdSlot";
import { AlternativesGrid } from "@/components/ComponentCard";
import { Breadcrumbs, ComponentTabs } from "@/components/ComponentHeader";
import { DatasheetCard } from "@/components/DatasheetCard";
import { ImageGallery } from "@/components/ImageGallery";
import { Section } from "@/components/ui/primitives";
import { SitemapEntries, apiGet } from "@/lib/api";
import { loadComponent } from "@/lib/component";
import { money, titleCase } from "@/lib/format";
import { componentMetadata } from "@/lib/metadata";
import { breadcrumbJsonLd, faqJsonLd, priceDatasetJsonLd, productJsonLd } from "@/lib/seo";
import { ADSENSE_CLIENT } from "@/lib/site";

export const revalidate = 3600;
export const dynamicParams = true;

/** Pre-build the top 1 000 parts (spec v1.1 row 24); the long tail renders on first request. */
export async function generateStaticParams(): Promise<Array<{ slug: string }>> {
  if (process.env.SKIP_STATIC_PARAMS === "1") return [];
  try {
    const entries = await apiGet("/v1/sitemap/components?page=1", SitemapEntries, { revalidate: false });
    return entries.slice(0, 1000).map((e) => ({ slug: e.slug }));
  } catch {
    return [];
  }
}

type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return componentMetadata(await loadComponent((await params).slug), "");
}

export default async function ComponentPage({ params }: Props) {
  const c = await loadComponent((await params).slug);
  const top = c.offer_summary.offers[0];
  return (
    <article>
      <JsonLd data={productJsonLd(c)} />
      <JsonLd data={breadcrumbJsonLd(c)} />
      <JsonLd data={faqJsonLd(c)} />
      <JsonLd data={priceDatasetJsonLd(c)} />
      <ViewBeacon slug={c.slug} />
      <Breadcrumbs c={c} />

      <div className="mt-4 grid gap-8 lg:grid-cols-[384px_1fr]">
        <ImageGallery images={c.images} alt={`${c.mpn} ${c.title}`} />
        <div>
          <h1 className="text-2xl font-bold sm:text-3xl">
            <span className="font-mono">{c.mpn}</span>
            {c.manufacturer ? <span className="text-ink-soft"> · {c.manufacturer}</span> : null}
          </h1>
          <p className="mt-2 text-ink-soft">{c.title}</p>
          <p className="mt-1 text-sm text-ink-soft">
            <Link href={`/category/${c.category}`}>{titleCase(c.category)}</Link>
            {c.package ? ` · ${c.package}` : ""}
            {c.lifecycle !== "unknown" ? ` · lifecycle: ${c.lifecycle}` : ""}
          </p>
          {top ? (
            <div className="mt-4 rounded-xl border border-line bg-surface-2 p-4" data-testid="price-box">
              <p className="text-sm text-ink-soft">Lowest landed price (Dhaka)</p>
              <p className="text-3xl font-bold tabular-nums">
                {c.low_price ? money(c.low_price.amount, c.low_price.currency) : money(top.landed_per_unit.amount, top.landed_per_unit.currency)}
              </p>
              <p className="text-sm text-ink-soft">
                {c.offer_count} offer{c.offer_count === 1 ? "" : "s"} · best overall: {top.source.display_name}
              </p>
              <div className="mt-3"><PriceSparkline points={c.history} /></div>
            </div>
          ) : (
            <p className="mt-4 rounded-xl border border-line p-4 text-sm text-ink-soft">No current offers. Set a price alert to hear when one appears.</p>
          )}
        </div>
      </div>

      <ComponentTabs slug={c.slug} active="" />

      <Section id="offers" title="Where to buy" action={<Link className="text-sm text-accent" href={`/component/${c.slug}/prices`}>All {c.offer_count} offers →</Link>}>
        <OffersPanel slug={c.slug} initial={c.offer_summary} limit={5} />
      </Section>

      <Section id="specs" title="Key specifications">
        <SpecTable specs={c.specs} limit={8} />
      </Section>

      {c.prose_md ? (
        <Section id="about" title={`About the ${c.mpn}`}>
          <div className="max-w-prose whitespace-pre-line text-sm leading-relaxed">{c.prose_md}</div>
        </Section>
      ) : null}

      <Section id="datasheet" title="Datasheet">
        {c.datasheets.length ? (
          <div className="grid gap-3 sm:grid-cols-2">{c.datasheets.slice(0, 2).map((d) => <DatasheetCard key={d.url} ds={d} mpn={c.mpn} />)}</div>
        ) : (
          <p className="text-sm text-ink-soft">No datasheet link yet.</p>
        )}
      </Section>

      <Section id="use-cases" title="Tutorials & projects" action={<Link className="text-sm text-accent" href={`/component/${c.slug}/use-cases`}>All tutorials →</Link>}>
        {c.use_cases.length ? (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{c.use_cases.slice(0, 3).map((u) => <li key={u.id}><UseCaseCard uc={u} /></li>)}</ul>
        ) : (
          <p className="text-sm text-ink-soft">No tutorials collected yet.</p>
        )}
      </Section>

      <Section id="alternatives" title="Alternatives">
        <AlternativesGrid items={c.alternatives} title={`Alternatives to ${c.mpn}`} />
      </Section>

      {/* Ad only after the primary content (price table + specs), never above the fold (§11.1). */}
      <AdSlot id="component-below-offers" placement="below_offers" template="component" contentReviewed={c.prose_reviewed || !c.prose_md}
        client={ADSENSE_CLIENT} slot={process.env.NEXT_PUBLIC_ADSENSE_SLOT_BELOW_OFFERS ?? ""} />

      {c.related.length ? (
        <Section id="related" title="Related parts">
          <AlternativesGrid items={c.related.slice(0, 8)} title="Related parts" />
        </Section>
      ) : null}

      {c.faq.length ? (
        <Section id="faq" title="FAQ">
          <dl className="space-y-4">
            {c.faq.map((f) => (
              <div key={f.question}>
                <dt className="font-medium">{f.question}</dt>
                <dd className="mt-1 text-sm text-ink-soft">{f.answer}</dd>
              </div>
            ))}
          </dl>
        </Section>
      ) : null}

      <div className="mt-10 flex flex-wrap items-center justify-between gap-4 border-t border-line pt-4 text-xs text-ink-soft">
        <p>Prices and images belong to the linked sellers. Data refreshed continuously; each price shows when it was checked.</p>
        <ReportButton slug={c.slug} />
      </div>
    </article>
  );
}
