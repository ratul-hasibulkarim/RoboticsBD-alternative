import type { Metadata } from "next";

import { AlternativesGrid } from "@/components/ComponentCard";
import { Breadcrumbs, ComponentTabs } from "@/components/ComponentHeader";
import { DatasheetCard } from "@/components/DatasheetCard";
import { SpecTable } from "@/components/SpecTable";
import { Section } from "@/components/ui/primitives";
import { loadComponent } from "@/lib/component";
import { componentMetadata } from "@/lib/metadata";

export const revalidate = 3600;

/** On-demand ISR: rendered on first request, then cached for `revalidate` seconds. */
export async function generateStaticParams(): Promise<Array<Record<string, string>>> {
  return [];
}
type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return componentMetadata(await loadComponent((await params).slug), "/datasheet");
}

export default async function DatasheetPage({ params }: Props) {
  const c = await loadComponent((await params).slug);
  return (
    <article>
      <Breadcrumbs c={c} />
      <h1 className="mt-4 text-2xl font-bold"><span className="font-mono">{c.mpn}</span> datasheet</h1>
      <ComponentTabs slug={c.slug} active="/datasheet" />
      <Section id="ds" title="Datasheets">
        {c.datasheets.length ? (
          <div className="grid gap-3 sm:grid-cols-2">{c.datasheets.map((d) => <DatasheetCard key={d.url} ds={d} mpn={c.mpn} />)}</div>
        ) : (
          <p className="text-sm text-ink-soft">We haven&apos;t found a datasheet link for {c.mpn} yet.</p>
        )}
        <p className="mt-2 text-xs text-ink-soft">Datasheets open on the publisher&apos;s site. VoltFind never hosts copies.</p>
      </Section>
      <Section id="specs" title="Specifications"><SpecTable specs={c.specs} /></Section>
      <Section id="alts" title="Alternates"><AlternativesGrid items={c.alternatives} /></Section>
    </article>
  );
}
