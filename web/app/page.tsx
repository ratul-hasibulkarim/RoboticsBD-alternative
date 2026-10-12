import type { Metadata } from "next";
import Link from "next/link";

import { ComponentCard } from "@/components/ComponentCard";
import { SearchBar } from "@/components/SearchBar";
import { Section } from "@/components/ui/primitives";
import { Card, Categories, apiGet } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { z } from "zod";

export const revalidate = 600;
export const metadata: Metadata = { alternates: { canonical: "/" } };

export default async function Home() {
  const [cats, trending] = await Promise.all([
    apiGet("/v1/categories", Categories, { revalidate: 600 }).catch(() => []),
    apiGet("/v1/trending?limit=12", z.array(Card), { revalidate: 600 }).catch(() => []),
  ]);
  return (
    <>
      <section className="py-8 text-center sm:py-14">
        <h1 className="text-3xl font-bold sm:text-4xl">Find any electronic part. See the real landed price.</h1>
        <p className="mx-auto mt-3 max-w-2xl text-ink-soft">
          Prices from Bangladeshi shops and global distributors, ranked by total cost to your door — plus datasheets and wiring tutorials.
        </p>
        <div className="mx-auto mt-6 max-w-2xl"><SearchBar size="lg" autoFocus /></div>
      </section>
      <Section id="categories" title="Browse by category">
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {cats.map((c) => (
            <li key={c.category}>
              <Link href={`/category/${c.category}`} className="flex min-h-11 items-center justify-between rounded-lg border border-line px-3 py-2 hover:border-accent">
                <span>{titleCase(c.category)}</span><span className="text-xs text-ink-soft">{c.count}</span>
              </Link>
            </li>
          ))}
        </ul>
      </Section>
      <Section id="trending" title="Trending this week">
        <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">{trending.map((c) => <li key={c.slug}><ComponentCard c={c} /></li>)}</ul>
      </Section>
    </>
  );
}
