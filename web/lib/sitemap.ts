import { Categories, Manufacturers, SitemapCount, SitemapEntries, apiGet } from "./api";
import { absolute } from "./site";

export const PER_FILE = 45_000; // < 50 000 limit (W5)
const COMPONENT_SUBPAGES = ["", "/prices", "/datasheet", "/use-cases", "/alternatives"] as const;

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function urlset(urls: Array<{ loc: string; lastmod?: string; images?: string[] }>, withImages = false): string {
  const ns = withImages ? ' xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"' : "";
  const body = urls
    .map((u) => {
      const imgs = withImages ? (u.images ?? []).map((i) => `<image:image><image:loc>${esc(i)}</image:loc></image:image>`).join("") : "";
      return `<url><loc>${esc(u.loc)}</loc>${u.lastmod ? `<lastmod>${u.lastmod}</lastmod>` : ""}${imgs}</url>`;
    })
    .join("");
  return `<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"${ns}>${body}</urlset>`;
}

export function xml(body: string): Response {
  return new Response(body, { headers: { "content-type": "application/xml; charset=utf-8", "cache-control": "public, max-age=3600" } });
}

/** Each component contributes 5 URLs, so component files hold PER_FILE / 5 parts. */
export const PARTS_PER_FILE = Math.floor(PER_FILE / COMPONENT_SUBPAGES.length);

export async function componentFileCount(): Promise<number> {
  const { components } = await apiGet("/v1/sitemap/count", SitemapCount, { revalidate: 3600 });
  return Math.max(1, Math.ceil(components / PARTS_PER_FILE));
}

export async function componentUrls(n: number): Promise<Array<{ loc: string; lastmod: string; images: string[] }>> {
  // API pages are 45 000 slugs; map our smaller file size onto them.
  const start = (n - 1) * PARTS_PER_FILE;
  const apiPage = Math.floor(start / 45_000) + 1;
  const entries = await apiGet(`/v1/sitemap/components?page=${apiPage}`, SitemapEntries, { revalidate: 3600 });
  const offset = start - (apiPage - 1) * 45_000;
  return entries.slice(offset, offset + PARTS_PER_FILE).flatMap((e) =>
    COMPONENT_SUBPAGES.map((sub) => ({
      loc: absolute(`/component/${e.slug}${sub}`),
      lastmod: e.updated_at.slice(0, 10),
      images: sub === "" && e.image_url ? [e.image_url] : [],
    })),
  );
}

export async function categoryUrls() {
  const cats = await apiGet("/v1/categories", Categories, { revalidate: 3600 });
  return [
    { loc: absolute("/") },
    { loc: absolute("/category") },
    { loc: absolute("/bangladesh") },
    ...cats.flatMap((c) => [{ loc: absolute(`/category/${c.category}`) }, { loc: absolute(`/bangladesh/${c.category}`) }]),
  ];
}

export async function manufacturerUrls() {
  const m = await apiGet("/v1/manufacturers", Manufacturers, { revalidate: 3600 });
  return [{ loc: absolute("/manufacturer") }, ...m.map((x) => ({ loc: absolute(`/manufacturer/${x.slug}`) }))];
}
