import type { Metadata } from "next";
import Link from "next/link";

import { Manufacturers, apiGet } from "@/lib/api";

export const revalidate = 3600;
export const metadata: Metadata = { title: "Manufacturers", alternates: { canonical: "/manufacturer" } };

export default async function ManufacturerIndex() {
  const mfrs = await apiGet("/v1/manufacturers", Manufacturers);
  return (
    <>
      <h1 className="text-2xl font-bold">Manufacturers</h1>
      <ul className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {mfrs.map((m) => <li key={m.slug}><Link className="block rounded-lg border border-line p-3 hover:border-accent" href={`/manufacturer/${m.slug}`}>{m.manufacturer} <span className="text-ink-soft">({m.count})</span></Link></li>)}
      </ul>
    </>
  );
}
