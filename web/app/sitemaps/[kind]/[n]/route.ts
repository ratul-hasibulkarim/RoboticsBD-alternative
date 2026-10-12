import { categoryUrls, componentUrls, manufacturerUrls, urlset, xml } from "@/lib/sitemap";

export const revalidate = 3600;

export async function GET(_req: Request, { params }: { params: Promise<{ kind: string; n: string }> }) {
  const { kind, n: nRaw } = await params;
  const n = Number(nRaw);
  if (!Number.isInteger(n) || n < 1) return new Response("not found", { status: 404 });
  switch (kind) {
    case "components":
      return xml(urlset(await componentUrls(n)));
    case "images":
      return xml(urlset((await componentUrls(n)).filter((u) => u.images.length > 0), true));
    case "categories":
      return n === 1 ? xml(urlset(await categoryUrls())) : new Response("not found", { status: 404 });
    case "manufacturers":
      return n === 1 ? xml(urlset(await manufacturerUrls())) : new Response("not found", { status: 404 });
    default:
      return new Response("not found", { status: 404 });
  }
}
