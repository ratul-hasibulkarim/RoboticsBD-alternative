import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BrowseGrid } from "@/components/BrowsePage";
import { ApiError, Manufacturers, Paged, apiGet } from "@/lib/api";

export const revalidate = 3600;
type Props = { params: Promise<{ mfr: string }>; searchParams: Promise<{ page?: string }> };

async function nameOf(slug: string): Promise<string | null> {
  const all = await apiGet("/v1/manufacturers", Manufacturers);
  return all.find((m) => m.slug === slug)?.manufacturer ?? null;
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { mfr } = await params;
  const page = Number((await searchParams).page ?? 1);
  const name = (await nameOf(mfr)) ?? mfr;
  return { title: `${name} components — prices & datasheets`, alternates: { canonical: page > 1 ? `/manufacturer/${mfr}?page=${page}` : `/manufacturer/${mfr}` } };
}

export default async function ManufacturerPage({ params, searchParams }: Props) {
  const { mfr } = await params;
  const page = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  const name = await nameOf(mfr);
  if (!name) notFound();
  let data;
  try {
    data = await apiGet(`/v1/manufacturers/${encodeURIComponent(mfr)}?page=${page}&per_page=24`, Paged);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return (
    <>
      <h1 className="text-2xl font-bold">{name}</h1>
      <p className="text-sm text-ink-soft">{data.total} parts</p>
      <BrowseGrid items={data.items} total={data.total} page={page} perPage={data.per_page} basePath={`/manufacturer/${mfr}`} template="manufacturer" />
    </>
  );
}
