import type { Metadata } from "next";
import Link from "next/link";

import { ApiError, Compare, apiGet } from "@/lib/api";
import { money } from "@/lib/format";

type SP = Promise<{ parts?: string }>;

function slugs(parts: string | undefined): string[] {
  return (parts ?? "").split(",").map((s) => s.trim()).filter(Boolean).slice(0, 4);
}

export async function generateMetadata({ searchParams }: { searchParams: SP }): Promise<Metadata> {
  const s = slugs((await searchParams).parts);
  if (s.length < 2) return { title: "Compare parts", robots: { index: false } };
  const sorted = [...s].sort();
  return {
    title: `${s.map((x) => x.toUpperCase()).join(" vs ")} — spec & price comparison`,
    // Canonical uses sorted slugs so a,b and b,a never compete (W6).
    alternates: { canonical: `/compare?parts=${sorted.join(",")}` },
  };
}

export default async function ComparePage({ searchParams }: { searchParams: SP }) {
  const s = slugs((await searchParams).parts);
  if (s.length < 2) return <p>Pick 2–4 parts to compare, e.g. <Link className="text-accent" href="/compare?parts=esp32-wroom-32,esp32-wroom-32d">ESP32-WROOM-32 vs 32D</Link>.</p>;
  let data;
  try {
    data = await apiGet(`/v1/compare?parts=${s.map(encodeURIComponent).join(",")}`, Compare);
  } catch (e) {
    if (e instanceof ApiError) return <p>One of these parts doesn&apos;t exist.</p>;
    throw e;
  }
  return (
    <>
      <h1 className="text-2xl font-bold">{data.components.map((c) => c.mpn).join(" vs ")}</h1>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-line">
              <th scope="col" className="py-2 text-left">Spec</th>
              {data.components.map((c) => <th key={c.slug} scope="col" className="py-2 text-left"><Link className="text-accent" href={`/component/${c.slug}`}>{c.mpn}</Link></th>)}
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-line"><th scope="row" className="py-2 text-left font-normal text-ink-soft">Lowest landed price</th>
              {data.components.map((c) => <td key={c.slug}>{c.low_price ? money(c.low_price.amount, c.low_price.currency) : "—"}</td>)}</tr>
            <tr className="border-b border-line"><th scope="row" className="py-2 text-left font-normal text-ink-soft">Manufacturer</th>
              {data.components.map((c) => <td key={c.slug}>{c.manufacturer ?? "—"}</td>)}</tr>
            <tr className="border-b border-line"><th scope="row" className="py-2 text-left font-normal text-ink-soft">Package</th>
              {data.components.map((c) => <td key={c.slug}>{c.package ?? "—"}</td>)}</tr>
            {data.spec_keys.map((k) => (
              <tr key={k} className="border-b border-line"><th scope="row" className="py-2 text-left font-normal text-ink-soft">{k}</th>
                {data.components.map((c) => <td key={c.slug}>{c.specs[k] ?? "—"}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
