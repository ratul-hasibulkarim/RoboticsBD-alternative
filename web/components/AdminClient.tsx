"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { z } from "zod";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const Item = z.object({ id: z.number(), kind: z.string(), ref_id: z.string(), reason: z.string(), payload: z.record(z.string(), z.unknown()), status: z.string(), created_at: z.string() });
const Src = z.object({ name: z.string(), display_name: z.string(), type: z.string(), legal_review_status: z.string(), crawl_status: z.string(), crawl_status_reason: z.string().nullable(), active: z.boolean() });

/** Minimal console: review queue + source health. Token is kept in memory only. */
export function AdminClient() {
  const qc = useQueryClient();
  const [token, setToken] = useState("");
  const h = { authorization: `Bearer ${token}`, "content-type": "application/json" };
  const review = useQuery({ queryKey: ["review", token], enabled: token.length > 0, queryFn: async () => {
    const r = await fetch(`${API}/v1/admin/review`, { headers: h });
    if (!r.ok) throw new Error(String(r.status));
    return z.array(Item).parse(await r.json());
  } });
  const sources = useQuery({ queryKey: ["sources", token], enabled: token.length > 0, queryFn: async () => {
    const r = await fetch(`${API}/v1/admin/sources`, { headers: h });
    if (!r.ok) throw new Error(String(r.status));
    return z.array(Src).parse(await r.json());
  } });
  const resolve = async (id: number, componentId: string | null) => {
    await fetch(`${API}/v1/admin/review/${id}/resolve`, { method: "POST", headers: h, body: JSON.stringify({ component_id: componentId }) });
    await qc.invalidateQueries({ queryKey: ["review"] });
  };
  if (!token) {
    return (
      <form className="flex max-w-md gap-2" onSubmit={(e) => { e.preventDefault(); const v = new FormData(e.currentTarget).get("t"); setToken(typeof v === "string" ? v : ""); }}>
        <label htmlFor="t" className="sr-only">Admin token</label>
        <input id="t" name="t" type="password" required className="h-11 flex-1 rounded-lg border border-line bg-surface px-3" placeholder="Admin token" />
        <button className="h-11 rounded-lg bg-accent px-4 text-white" type="submit">Open</button>
      </form>
    );
  }
  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-xl font-bold">Review queue ({review.data?.length ?? "…"})</h1>
        {review.isError ? <p role="alert">Token rejected.</p> : null}
        <ul className="mt-3 divide-y divide-line rounded-xl border border-line text-sm">
          {review.data?.map((it) => {
            const suggested = typeof it.payload.suggested_component === "string" ? it.payload.suggested_component : null;
            return (
              <li key={it.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <span><strong>{it.kind}</strong> · {it.reason}<code className="block text-xs text-ink-soft">{JSON.stringify(it.payload).slice(0, 220)}</code></span>
                <span className="flex gap-2">
                  {suggested ? <button type="button" className="rounded border border-line px-2 py-1" onClick={() => void resolve(it.id, suggested)}>Accept suggestion</button> : null}
                  <button type="button" className="rounded border border-line px-2 py-1" onClick={() => void resolve(it.id, null)}>Reject / done</button>
                </span>
              </li>
            );
          })}
        </ul>
      </section>
      <section>
        <h2 className="text-xl font-bold">Sources</h2>
        <table className="mt-3 w-full text-sm">
          <thead><tr className="text-left"><th>Source</th><th>Type</th><th>Legal</th><th>Crawl</th></tr></thead>
          <tbody>
            {sources.data?.map((s) => (
              <tr key={s.name} className="border-t border-line"><td className="py-2">{s.display_name}</td><td>{s.type}</td><td>{s.legal_review_status}</td>
                <td title={s.crawl_status_reason ?? ""}>{s.crawl_status}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
