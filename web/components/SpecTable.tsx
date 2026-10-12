export function SpecTable({ specs, limit }: { specs: Record<string, string>; limit?: number }) {
  const entries = Object.entries(specs);
  if (entries.length === 0) return <p className="text-sm text-ink-soft">No specifications collected yet.</p>;
  const shown = limit ? entries.slice(0, limit) : entries;
  const body = (rows: Array<[string, string]>) => (
    <table className="w-full text-sm">
      <tbody>
        {rows.map(([k, v]) => (
          <tr key={k} className="border-b border-line last:border-b-0">
            <th scope="row" className="w-1/2 py-2 pr-4 text-left font-normal text-ink-soft">{k}</th>
            <td className="py-2">{v}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
  return (
    <div className="rounded-xl border border-line px-4">
      {body(shown)}
      {limit && entries.length > limit ? (
        <details className="border-t border-line py-2">
          <summary className="cursor-pointer text-sm text-accent">Show all {entries.length} specifications</summary>
          {body(entries.slice(limit))}
        </details>
      ) : null}
    </div>
  );
}
