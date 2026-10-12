import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { BrowseGrid } from "@/components/BrowsePage";
import { ApiError, Paged, apiGet } from "@/lib/api";
import { titleCase } from "@/lib/format";

export const revalidate = 3600;
type Props = { params: Promise<{ category: string }>; searchParams: Promise<{ page?: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { category } = await params;
  return {
    title: `${titleCase(category)} price in Bangladesh`,
    description: `Compare ${titleCase(category).toLowerCase()} prices from shops that deliver in Bangladesh — Dhaka, Chattogram and nationwide.`,
    alternates: { canonical: `/bangladesh/${category}` },
  };
}

export default async function BdCategory({ params, searchParams }: Props) {
  const { category } = await params;
  const page = Math.max(1, Number((await searchParams).page ?? 1) || 1);
  let data;
  try {
    data = await apiGet(`/v1/categories/${encodeURIComponent(category)}?page=${page}&per_page=24&ships_to_bd=true`, Paged);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  return (
    <>
      <h1 className="text-2xl font-bold">{titleCase(category)} in Bangladesh</h1>
      <p className="text-sm text-ink-soft">{data.total} parts that ship to Bangladesh</p>
      <BrowseGrid items={data.items} total={data.total} page={page} perPage={data.per_page} basePath={`/bangladesh/${category}`} template="category" />
    </>
  );
}
