import type { TUseCase } from "@/lib/api";

const SOURCE_LABEL: Record<string, string> = { youtube: "YouTube", github: "GitHub", reddit: "Reddit", blog: "Blog", forum: "Forum", editorial: "VoltFind" };

export function UseCaseCard({ uc, showCode = false }: { uc: TUseCase; showCode?: boolean }) {
  return (
    <article className="flex h-full flex-col rounded-xl border border-line p-4">
      <h3 className="font-medium">
        <a href={uc.source_url} target="_blank" rel="noopener nofollow" className="hover:text-accent">{uc.title}</a>
      </h3>
      <p className="mt-1 text-xs text-ink-soft">
        {SOURCE_LABEL[uc.source_type] ?? uc.source_type}
        {uc.source_author ? ` · ${uc.source_author}` : ""}
        {uc.difficulty ? ` · ${uc.difficulty}` : ""}
      </p>
      <p className="mt-2 flex-1 text-sm">{uc.summary}</p>
      {showCode && uc.code_snippet ? (
        <figure className="mt-3">
          <pre className="max-h-72 overflow-auto rounded-lg bg-surface-2 p-3 text-xs"><code>{uc.code_snippet}</code></pre>
          <figcaption className="mt-1 text-xs text-ink-soft">Code licensed {uc.code_license}, from {uc.source_url}</figcaption>
        </figure>
      ) : null}
      <a href={uc.source_url} target="_blank" rel="noopener nofollow" className="mt-3 text-sm text-accent">
        Read at {SOURCE_LABEL[uc.source_type] ?? "source"} ↗
      </a>
    </article>
  );
}
