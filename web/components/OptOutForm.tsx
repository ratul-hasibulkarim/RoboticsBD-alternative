"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL ?? "";

export function OptOutForm() {
  const [state, setState] = useState<"idle" | "done" | "error">("idle");
  if (state === "done") return <p role="status" className="mt-4 text-good">Request received. We&apos;ll e-mail you when it&apos;s done.</p>;
  return (
    <form className="mt-6 flex max-w-md flex-col gap-3" action={async (f) => {
      const r = await fetch(`${API}/v1/legal/opt-out`, { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ domain: String(f.get("domain") ?? "").toLowerCase().trim(), contact_email: f.get("email"), reason: f.get("reason") }) });
      setState(r.ok ? "done" : "error");
    }}>
      <label className="text-sm">Domain<input name="domain" required placeholder="yourshop.com" className="mt-1 h-11 w-full rounded-lg border border-line bg-surface px-3" /></label>
      <label className="text-sm">Contact e-mail<input name="email" type="email" required className="mt-1 h-11 w-full rounded-lg border border-line bg-surface px-3" /></label>
      <label className="text-sm">Reason<textarea name="reason" required minLength={5} className="mt-1 w-full rounded-lg border border-line bg-surface p-3" /></label>
      <button type="submit" className="h-11 rounded-lg bg-accent px-4 text-white dark:text-slate-950">Send request</button>
      {state === "error" ? <p role="alert" className="text-sm text-warn">Please check the domain and e-mail.</p> : null}
    </form>
  );
}
