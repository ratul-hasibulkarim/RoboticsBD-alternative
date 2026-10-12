import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Privacy & legal", alternates: { canonical: "/legal" } };

export default function Legal() {
  return (
    <article className="prose max-w-prose space-y-4">
      <h1 className="text-2xl font-bold">Privacy &amp; legal</h1>
      <h2 className="text-lg font-semibold">What VoltFind is</h2>
      <p>VoltFind indexes public product information — part numbers, prices, stock, specifications, and links to images and datasheets — and links every fact back to its source. We do not sell, ship or hold stock.</p>
      <h2 className="text-lg font-semibold">What we collect about you</h2>
      <p>Nothing, unless you create a price alert: then we store your e-mail address and your alerts. Search statistics use a salted hash that rotates daily and cannot be traced back to your IP address. You can delete your account and every alert from the <Link className="text-accent" href="/alerts">alerts page</Link>.</p>
      <h2 className="text-lg font-semibold">Ads</h2>
      <p>Some pages show Google AdSense ads below the main content. Without your consent, ads are non-personalised.</p>
      <h2 className="text-lg font-semibold">Shop and site owners</h2>
      <p>Our crawler obeys robots.txt and identifies itself as <Link className="text-accent" href="/bot">VoltFindBot</Link>. To be removed, use the <Link className="text-accent" href="/legal/opt-out">opt-out form</Link>.</p>
    </article>
  );
}
