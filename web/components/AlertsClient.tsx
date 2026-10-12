"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { z } from "zod";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";
const Alert = z.object({
  id: z.string(), component_slug: z.string(), component_title: z.string(), target: z.string(), currency: z.string(),
  quantity: z.number(), ship_to: z.string(), active: z.boolean(), armed: z.boolean(), last_fired_at: z.string().nullable(),
});
const Session = z.object({ session_token: z.string(), email: z.string() });
const KEY = "vf_session";

function readSession(): string | null {
  try { return sessionStorage.getItem(KEY); } catch { return null; }
}

export function AlertsClient() {
  const qc = useQueryClient();
  const [token, setToken] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    const login = url.searchParams.get("token");
    if (login) {
      void fetch(`${API}/v1/alerts/session`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: login }) })
        .then(async (r) => {
          if (!r.ok) { setMsg("That sign-in link has expired. Request a new one."); return; }
          const s = Session.parse(await r.json());
          sessionStorage.setItem(KEY, s.session_token);
          setToken(s.session_token);
          window.history.replaceState(null, "", "/alerts");
        });
    } else setToken(readSession());
  }, []);

  const alerts = useQuery({
    queryKey: ["alerts", token],
    enabled: Boolean(token),
    queryFn: async () => {
      const r = await fetch(`${API}/v1/alerts`, { headers: { authorization: `Bearer ${token}` } });
      if (!r.ok) throw new Error(String(r.status));
      return z.array(Alert).parse(await r.json());
    },
  });

  if (!token) {
    return (
      <form className="mt-6 flex max-w-md gap-2" action={async (f) => {
        const r = await fetch(`${API}/v1/alerts/request-link`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ email: f.get("email") }) });
        setMsg(r.ok ? "Check your inbox for a sign-in link." : "Couldn't send the link — try again later.");
      }}>
        <label htmlFor="alert-email" className="sr-only">E-mail</label>
        <input id="alert-email" name="email" type="email" required placeholder="you@example.com" className="h-11 flex-1 rounded-lg border border-line bg-surface px-3" />
        <button className="h-11 rounded-lg bg-accent px-4 text-white dark:text-slate-950" type="submit">Email me a link</button>
        {msg ? <p role="status" className="basis-full text-sm">{msg}</p> : null}
      </form>
    );
  }

  const del = async (id: string) => {
    await fetch(`${API}/v1/alerts/${id}`, { method: "DELETE", headers: { authorization: `Bearer ${token}` } });
    await qc.invalidateQueries({ queryKey: ["alerts"] });
  };
  const deleteAccount = async () => {
    if (!window.confirm("Delete your account and all alerts?")) return;
    await fetch(`${API}/v1/account`, { method: "DELETE", headers: { authorization: `Bearer ${token}` } });
    sessionStorage.removeItem(KEY);
    setToken(null);
  };
  return (
    <div className="mt-6">
      {alerts.data?.length === 0 ? <p className="text-sm text-ink-soft">No alerts yet — use “Set price alert” on any part page.</p> : null}
      <ul className="divide-y divide-line rounded-xl border border-line">
        {alerts.data?.map((a) => (
          <li key={a.id} className="flex items-center justify-between gap-4 p-4">
            <span>
              <a className="font-medium" href={`/component/${a.component_slug}`}>{a.component_title}</a>
              <span className="block text-xs text-ink-soft">Target {a.currency} {a.target} × {a.quantity} to {a.ship_to} · {a.armed ? "watching" : "fired, re-arms when price rises"}</span>
            </span>
            <button type="button" className="text-sm text-warn" onClick={() => void del(a.id)}>Delete</button>
          </li>
        ))}
      </ul>
      <button type="button" className="mt-6 text-sm text-ink-soft underline" onClick={() => void deleteAccount()}>Delete my account</button>
    </div>
  );
}
