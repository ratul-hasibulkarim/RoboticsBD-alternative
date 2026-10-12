import type { Metadata } from "next";

import { AlertsClient } from "@/components/AlertsClient";

export const metadata: Metadata = { title: "Price alerts", robots: { index: false, follow: false } };

export default function AlertsPage() {
  return (
    <>
      <h1 className="text-2xl font-bold">Price alerts</h1>
      <p className="mt-1 text-sm text-ink-soft">We e-mail you once when a part drops to your target price (landed, per unit). Up to 10 alerts.</p>
      <AlertsClient />
    </>
  );
}
