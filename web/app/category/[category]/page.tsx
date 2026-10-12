import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BrowseGrid } from "@/components/BrowsePage";
import { ApiError, Paged, apiGet } from "@/lib/api";
import { titleCase } from "@/lib/format";

export const revalidate = 3600;
type Props = { params: Promise<{ category: string }>; searchParams: Promise<{ page?: string }> };

async function load(category: string, page: number) {
  try {
    return await apiGet(`/v1/categories/${encodeURIComponent(category)}?page=${page}&per_page=24`, Paged);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 422)) notFound();
    throw e;
  }
}

export async function generateMetadata({ params, searchParams }: Props): Promise<Metadata> {
  const { category } = await params;
  const page = Number((await searchParams).page ?? 1);
  const path = page > 1 ? `/category/${category}?page=${page}` : `/category/${category}`;
  return { title: `${titleCase(category)} — prices & datasheets`, alternates: { canonical: path } };
}

export default async function CategoryPage({ params, searchParams }: Props) {
  const { category } = await params;
  const page = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  const data = await load(category, page);
  return (
    <>
      <h1 className="text-2xl font-bold">{titleCase(category)}</h1>
      <p className="text-sm text-ink-soft">{data.total} parts · <Link className="text-accent" href={`/bangladesh/${category}`}>available in Bangladesh →</Link></p>
      <BrowseGrid items={data.items} total={data.total} page={page} perPage={data.per_page} basePath={`/category/${category}`} template="category" />
    </>
  );
}
