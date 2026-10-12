import type { Metadata } from "next";
import Link from "next/link";

import { AlternativesGrid } from "@/components/ComponentCard";
import { Breadcrumbs, ComponentTabs } from "@/components/ComponentHeader";
import { Section } from "@/components/ui/primitives";
import { Card, apiGet } from "@/lib/api";
import { loadComponent } from "@/lib/component";
import { componentMetadata } from "@/lib/metadata";
import { z } from "zod";

export const revalidate = 3600;

/** On-demand ISR: rendered on first request, then cached for `revalidate` seconds. */
export async function generateStaticParams(): Promise<Array<Record<string, string>>> {
  return [];
}
type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return componentMetadata(await loadComponent((await params).slug), "/alternatives");
}

export default async function AlternativesPage({ params }: Props) {
  const c = await loadComponent((await params).slug);
  const alts = await apiGet(`/v1/components/${encodeURIComponent(c.slug)}/alternatives?limit=16`, z.array(Card));
  return (
    <article>
      <Breadcrumbs c={c} />
      <h1 className="mt-4 text-2xl font-bold">Alternatives to <span className="font-mono">{c.mpn}</span></h1>
      <ComponentTabs slug={c.slug} active="/alternatives" />
      <Section id="alts" title="Spec-similar parts in the same category">
        <AlternativesGrid items={alts} />
        <p className="mt-2 text-xs text-ink-soft">Selected by specification overlap. Always check the pinout and datasheet before substituting.</p>
      </Section>
      {alts[0] ? (
        <p className="mt-6 text-sm"><Link className="text-accent" href={`/compare?parts=${c.slug},${alts[0].slug}`}>Compare {c.mpn} vs {alts[0].mpn} →</Link></p>
      ) : null}
    </article>
  );
}
