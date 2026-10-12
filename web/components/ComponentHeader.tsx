import Link from "next/link";

import type { TComponent } from "@/lib/api";

const TABS = [
  ["", "Overview"],
  ["/prices", "All prices"],
  ["/datasheet", "Datasheet"],
  ["/use-cases", "Tutorials"],
  ["/alternatives", "Alternatives"],
] as const;

export function Breadcrumbs({ c }: { c: TComponent }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm text-ink-soft">
      <ol className="flex flex-wrap gap-1">
        {c.breadcrumbs.map((b, i) => (
          <li key={b.path} className="flex gap-1">
            {i > 0 ? <span aria-hidden>/</span> : null}
            {i === c.breadcrumbs.length - 1 ? <span aria-current="page">{b.name}</span> : <Link href={b.path}>{b.name}</Link>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export function ComponentTabs({ slug, active }: { slug: string; active: string }) {
  return (
    <nav aria-label="Component sections" className="mt-4 flex gap-1 overflow-x-auto border-b border-line">
      {TABS.map(([path, label]) => (
        <Link key={path} href={`/component/${slug}${path}`} aria-current={active === path ? "page" : undefined}
          className={`min-h-11 whitespace-nowrap px-3 py-3 text-sm ${active === path ? "border-b-2 border-accent font-medium" : "text-ink-soft"}`}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
