"use client";

import { useState } from "react";

const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "";

export function NotifyForm({ q }: { q: string }) {
  const [done, setDone] = useState(false);
  async function submit(form: FormData) {
    const res = await fetch(`${PUBLIC_API}/v1/notify-when-indexed`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), q }),
    });
    setDone(res.ok);
  }
  if (done) return <p role="status" className="mt-2 text-sm text-good">We&apos;ll e-mail you once it&apos;s indexed.</p>;
  return (
    <form action={submit} className="mt-3 flex max-w-md gap-2">
      <label htmlFor="notify-email" className="sr-only">E-mail</label>
      <input id="notify-email" name="email" type="email" required placeholder="you@example.com"
        className="h-11 flex-1 rounded-lg border border-line bg-surface px-3" />
      <button type="submit" className="h-11 rounded-lg bg-accent px-4 text-white dark:text-slate-950">Notify me</button>
    </form>
  );
}
