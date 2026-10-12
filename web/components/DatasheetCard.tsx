type Ds = { url: string; host: string; revision: string | null; page_count: number | null; language: string | null; is_primary: boolean; checked_at: string };

/** Links to the publisher's copy — datasheets are never mirrored (LEGAL rule 7). */
export function DatasheetCard({ ds, mpn }: { ds: Ds; mpn: string }) {
  return (
    <a href={ds.url} target="_blank" rel="noopener nofollow" className="flex items-center justify-between gap-4 rounded-xl border border-line p-4 hover:border-accent">
      <span>
        <span className="block font-medium">{ds.is_primary ? `${mpn} datasheet` : `Alternate datasheet`}</span>
        <span className="block text-xs text-ink-soft">
          Hosted by {ds.host}
          {ds.revision ? ` · rev ${ds.revision}` : ""}
          {ds.page_count ? ` · ${ds.page_count} pages` : ""}
          {ds.language ? ` · ${ds.language}` : ""}
        </span>
      </span>
      <span aria-hidden className="text-accent">PDF ↗</span>
    </a>
  );
}
