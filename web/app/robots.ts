import type { MetadataRoute } from "next";

import { absolute } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/", disallow: ["/admin", "/api/", "/search?", "/search", "/alerts", "/go/"] }],
    sitemap: absolute("/sitemap-index.xml"),
  };
}
