import Link from "next/link";

import { ComponentCard } from "./ComponentCard";
import { AdSlot, type Template } from "./ads/AdSlot";
import type { TCard } from "@/lib/api";
import { ADSENSE_CLIENT } from "@/lib/site";

export function BrowseGrid({ items, total, page, perPage, basePath, template }: {
  items: TCard[]; total: number; page: number; perPage: number; basePath: string; template: Template;
}) {
  return (
    <>
      <ul className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        {items.map((c, i) => (
          <li key={c.slug} className={i === 8 ? "col-span-2 md:col-span-4" : ""}>
            {i === 8 ? (
              <AdSlot id={`${template}-in-feed`} placement="in_feed_native" template={template} client={ADSENSE_CLIENT}
                slot={process.env.NEXT_PUBLIC_ADSENSE_SLOT_IN_FEED ?? ""} />
            ) : null}
            <ComponentCard c={c} />
          </li>
        ))}
      </ul>
      <nav aria-label="Pagination" className="mt-6 flex justify-between text-sm">
        {page > 1 ? <Link href={page === 2 ? basePath : `${basePath}?page=${page - 1}`}>← Previous</Link> : <span />}
        {page * perPage < total ? <Link href={`${basePath}?page=${page + 1}`}>Next →</Link> : null}
      </nav>
    </>
  );
}
