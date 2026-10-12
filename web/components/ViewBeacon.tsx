"use client";

import { useEffect } from "react";

const PUBLIC_API = process.env.NEXT_PUBLIC_API_URL ?? "";

export function ViewBeacon({ slug }: { slug: string }) {
  useEffect(() => {
    const url = `${PUBLIC_API}/v1/components/${encodeURIComponent(slug)}/view`;
    if (navigator.sendBeacon) navigator.sendBeacon(url);
    else void fetch(url, { method: "POST", keepalive: true });
  }, [slug]);
  return null;
}
