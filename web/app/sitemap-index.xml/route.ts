import { componentFileCount, xml } from "@/lib/sitemap";
import { absolute } from "@/lib/site";

export const revalidate = 3600;

export async function GET() {
  const n = await componentFileCount();
  const files = [
    ...Array.from({ length: n }, (_, i) => `/sitemap-components-${i + 1}.xml`),
    ...Array.from({ length: n }, (_, i) => `/sitemap-images-${i + 1}.xml`),
    "/sitemap-categories.xml",
    "/sitemap-manufacturers.xml",
  ];
  const body = files.map((f) => `<sitemap><loc>${absolute(f)}</loc></sitemap>`).join("");
  return xml(`<?xml version="1.0" encoding="UTF-8"?><sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${body}</sitemapindex>`);
}
