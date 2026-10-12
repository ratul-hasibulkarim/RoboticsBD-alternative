"use client";

import { useState } from "react";

const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "";
const FIELDS = ["price", "stock", "specs", "datasheet", "image", "match", "other"] as const;

export function ReportButton({ slug }: { slug: string }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  async function submit(form: FormData) {
    setState("sending");
    const res = await fetch(`${PUBLIC_API}/v1/reports`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ component_slug: slug, field: form.get("field"), message: form.get("message") }),
    });
    setState(res.ok ? "done" : "error");
  }
  if (state === "done") return <p role="status" className="text-sm text-good">Thanks — we&apos;ll check it.</p>;
  return (
    <div>
      <button type="button" className="text-sm text-ink-soft underline" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        Report incorrect data
      </button>
      {open ? (
        <form action={submit} className="mt-2 flex max-w-md flex-col gap-2">
          <label className="text-sm">What is wrong?
            <select name="field" className="mt-1 h-11 w-full rounded-lg border border-line bg-surface px-2">
              {FIELDS.map((f) => <option key={f} value={f}>{f}</option>)}
            </select>
          </label>
          <label className="text-sm">Details
            <textarea name="message" required minLength={5} maxLength={2000} className="mt-1 w-full rounded-lg border border-line bg-surface p-2" />
          </label>
          <button type="submit" disabled={state === "sending"} className="h-11 rounded-lg bg-accent px-4 text-white dark:text-slate-950">Send report</button>
          {state === "error" ? <p role="alert" className="text-sm text-warn">Couldn&apos;t send — try again.</p> : null}
        </form>
      ) : null}
    </div>
  );
}
