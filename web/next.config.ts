import type { NextConfig } from "next";

const API_URL = process.env.API_URL ?? "http://localhost:8000";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Source-hosted images are rendered `unoptimized` (hotlinked, LEGAL rule 7). Only licensed
  // images (manufacturer / CC) go through the optimizer for AVIF/WebP.
  images: {
    formats: ["image/avif", "image/webp"],
    remotePatterns: [{ protocol: "https", hostname: "**" }],
    minimumCacheTTL: 86400,
  },
  async rewrites() {
    return [
      { source: "/go/:id", destination: `${API_URL}/go/:id` },
      { source: "/sitemap-:kind(components|images)-:n(\\d+).xml", destination: "/sitemaps/:kind/:n" },
      { source: "/sitemap-:kind(categories|manufacturers).xml", destination: "/sitemaps/:kind/1" },
    ];
  },
  async headers() {
    return [
      { source: "/:path*", headers: securityHeaders },
      { source: "/admin/:path*", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }] },
      { source: "/alerts", headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }] },
    ];
  },
  async redirects() {
    return [{ source: "/component", destination: "/", permanent: true }];
  },
};

export default config;
