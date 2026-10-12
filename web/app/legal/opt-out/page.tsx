import type { Metadata } from "next";

import { OptOutForm } from "@/components/OptOutForm";

export const metadata: Metadata = { title: "Opt out — remove your site from VoltFind", alternates: { canonical: "/legal/opt-out" } };

export default function OptOut() {
  return (
    <>
      <h1 className="text-2xl font-bold">Remove your site from VoltFind</h1>
      <p className="mt-2 max-w-prose text-ink-soft">
        Tell us your domain and we&apos;ll stop crawling it and hide its listings once we confirm the request (usually within 24 hours).
        You can also block us immediately with <code>User-agent: VoltFindBot</code> / <code>Disallow: /</code> in your robots.txt.
      </p>
      <OptOutForm />
    </>
  );
}
