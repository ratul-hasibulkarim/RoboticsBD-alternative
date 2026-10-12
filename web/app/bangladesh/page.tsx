import type { Metadata } from "next";
import Link from "next/link";

import { Categories, apiGet } from "@/lib/api";
import { titleCase } from "@/lib/format";

export const revalidate = 3600;
export const metadata: Metadata = {
  title: "Buy electronic components in Bangladesh — compare local shop prices",
  description: "Compare prices for microcontrollers, sensors, modules and ICs from shops in Dhaka and across Bangladesh, with delivery estimates.",
  alternates: { canonical: "/bangladesh" },
};

export default async function Bangladesh() {
  const cats = await apiGet("/v1/categories", Categories);
  return (
    <>
      <h1 className="text-2xl font-bold">Electronic components in Bangladesh</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Prices from Bangladeshi shops (in ৳, with delivery estimates to your city) and from international distributors that ship to Bangladesh,
        including estimated import duty.
      </p>
      <ul className="mt-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {cats.map((c) => <li key={c.category}><Link className="block rounded-lg border border-line p-3 hover:border-accent" href={`/bangladesh/${c.category}`}>{titleCase(c.category)} in Bangladesh</Link></li>)}
      </ul>
    </>
  );
}
