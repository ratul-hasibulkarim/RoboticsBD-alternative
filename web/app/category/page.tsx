import type { Metadata } from "next";
import Link from "next/link";

import { Categories, apiGet } from "@/lib/api";
import { titleCase } from "@/lib/format";

export const revalidate = 3600;
export const metadata: Metadata = { title: "Electronic component categories", alternates: { canonical: "/category" } };

export default async function CategoryIndex() {
  const cats = await apiGet("/v1/categories", Categories);
  return (
    <>
      <h1 className="text-2xl font-bold">Categories</h1>
      <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cats.map((c) => (
          <li key={c.category}><Link className="block rounded-lg border border-line p-3 hover:border-accent" href={`/category/${c.category}`}>{titleCase(c.category)} <span className="text-ink-soft">({c.count})</span></Link></li>
        ))}
      </ul>
    </>
  );
}
