import Link from "next/link";

import { qs } from "@/lib/api";
import { titleCase } from "@/lib/format";

type Facets = Record<string, Array<[string, number]>>;

export function FilterSidebar({ facets, params }: { facets: Facets; params: Record<string, string | undefined> }) {
  const link = (key: string, value: string | undefined) => `/search${qs({ ...params, page: undefined, [key]: value })}`;
  return (
    <nav aria-label="Filters" className="space-y-6 text-sm">
      <div>
        <h3 className="mb-2 font-medium">Availability</h3>
        <ul className="space-y-1">
          <li><Link className={params.in_stock ? "text-accent" : ""} href={link("in_stock", params.in_stock ? undefined : "true")}>In stock only</Link></li>
          <li><Link className={params.ships_to_bd ? "text-accent" : ""} href={link("ships_to_bd", params.ships_to_bd ? undefined : "true")}>Ships to Bangladesh</Link></li>
        </ul>
      </div>
      {(["category", "manufacturer", "package"] as const).map((key) =>
        (facets[key]?.length ?? 0) > 0 ? (
          <div key={key}>
            <h3 className="mb-2 font-medium">{titleCase(key)}</h3>
            <ul className="space-y-1">
              {(facets[key] ?? []).slice(0, 10).map(([value, count]) => (
                <li key={value}>
                  <Link href={link(key, params[key] === value ? undefined : value)} className={params[key] === value ? "text-accent" : ""}>
                    {key === "category" ? titleCase(value) : value} <span className="text-ink-soft">({count})</span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
    </nav>
  );
}
