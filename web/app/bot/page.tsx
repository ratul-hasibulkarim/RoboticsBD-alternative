import type { Metadata } from "next";

export const metadata: Metadata = { title: "VoltFindBot — our crawler", alternates: { canonical: "/bot" } };

export default function Bot() {
  return (
    <article className="max-w-prose space-y-4">
      <h1 className="text-2xl font-bold">VoltFindBot</h1>
      <p>User agent: <code>VoltFindBot/1.0 (+https://voltfind.com/bot)</code></p>
      <ul className="list-disc space-y-1 pl-6">
        <li>Obeys robots.txt (re-read every 24 hours). If your robots.txt can&apos;t be fetched, we don&apos;t crawl.</li>
        <li>Default speed: one request every 2 seconds per site, slower if your <code>Crawl-delay</code> asks for it.</li>
        <li>Backs off on HTTP 429/503 and honours <code>Retry-After</code>. Stops completely on 403/451 until a human reviews it.</li>
        <li>Never logs in, never sends cookies, never solves CAPTCHAs.</li>
        <li>Keeps only product data (price, title, part number, specs) and links to your images and datasheets.</li>
      </ul>
      <p>To block it: <code>User-agent: VoltFindBot</code> then <code>Disallow: /</code>. To ask for removal, use our opt-out form.</p>
    </article>
  );
}
