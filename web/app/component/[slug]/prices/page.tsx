import type { Metadata } from "next";

import { JsonLd } from "@/components/JsonLd";
import { OffersPanel } from "@/components/OffersPanel";
import { PriceSparkline } from "@/components/PriceSparkline";
import { AdSlot } from "@/components/ads/AdSlot";
import { Breadcrumbs, ComponentTabs } from "@/components/ComponentHeader";
import { Section } from "@/components/ui/primitives";
import { getOffers } from "@/lib/api";
import { loadComponent } from "@/lib/component";
import { DEFAULT_GEO } from "@/lib/geo";
import { componentMetadata } from "@/lib/metadata";
import { priceDatasetJsonLd } from "@/lib/seo";
import { ADSENSE_CLIENT } from "@/lib/site";

export const revalidate = 3600;

/** On-demand ISR: rendered on first request, then cached for `revalidate` seconds. */
export async function generateStaticParams(): Promise<Array<Record<string, string>>> {
  return [];
}
type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return componentMetadata(await loadComponent((await params).slug), "/prices");
}

export default async function PricesPage({ params }: Props) {
  const c = await loadComponent((await params).slug);
  const offers = await getOffers(c.slug, { country: DEFAULT_GEO.country, city: DEFAULT_GEO.city ?? undefined, currency: DEFAULT_GEO.currency });
  return (
    <article>
      <JsonLd data={priceDatasetJsonLd(c)} />
      <Breadcrumbs c={c} />
      <h1 className="mt-4 text-2xl font-bold"><span className="font-mono">{c.mpn}</span> prices</h1>
      <ComponentTabs slug={c.slug} active="/prices" />
      <Section id="all-offers" title={`All ${offers.total} offers`}>
        <OffersPanel slug={c.slug} initial={offers} />
      </Section>
      <Section id="history" title="Price history">
        <PriceSparkline points={c.history} width={640} height={120} />
      </Section>
      <AdSlot id="prices-below-offers" placement="below_offers" template="prices" client={ADSENSE_CLIENT}
        slot={process.env.NEXT_PUBLIC_ADSENSE_SLOT_BELOW_OFFERS ?? ""} />
    </article>
  );
}
