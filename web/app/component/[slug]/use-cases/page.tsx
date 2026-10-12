import type { Metadata } from "next";

import { Breadcrumbs, ComponentTabs } from "@/components/ComponentHeader";
import { JsonLd } from "@/components/JsonLd";
import { UseCaseCard } from "@/components/UseCaseCard";
import { AdSlot } from "@/components/ads/AdSlot";
import { Section } from "@/components/ui/primitives";
import { UseCase, apiGet } from "@/lib/api";
import { loadComponent } from "@/lib/component";
import { componentMetadata } from "@/lib/metadata";
import { howToJsonLd } from "@/lib/seo";
import { ADSENSE_CLIENT } from "@/lib/site";
import { z } from "zod";

export const revalidate = 3600;

/** On-demand ISR: rendered on first request, then cached for `revalidate` seconds. */
export async function generateStaticParams(): Promise<Array<Record<string, string>>> {
  return [];
}
type Props = { params: Promise<{ slug: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return componentMetadata(await loadComponent((await params).slug), "/use-cases");
}

export default async function UseCasesPage({ params }: Props) {
  const c = await loadComponent((await params).slug);
  const all = await apiGet(`/v1/components/${encodeURIComponent(c.slug)}/use-cases`, z.array(UseCase));
  return (
    <article>
      {all.slice(0, 5).map((u) => <JsonLd key={u.id} data={howToJsonLd(u, c.mpn)} />)}
      <Breadcrumbs c={c} />
      <h1 className="mt-4 text-2xl font-bold">How to use the <span className="font-mono">{c.mpn}</span></h1>
      <ComponentTabs slug={c.slug} active="/use-cases" />
      <Section id="tutorials" title={`${all.length} tutorials, projects and discussions`}>
        {all.length ? (
          <ul className="grid gap-4 md:grid-cols-2">{all.map((u) => <li key={u.id}><UseCaseCard uc={u} showCode /></li>)}</ul>
        ) : (
          <p className="text-sm text-ink-soft">No tutorials collected yet.</p>
        )}
      </Section>
      <AdSlot id="usecase-footer" placement="article_footer" template="use_case" client={ADSENSE_CLIENT}
        slot={process.env.NEXT_PUBLIC_ADSENSE_SLOT_FOOTER ?? ""} />
    </article>
  );
}
