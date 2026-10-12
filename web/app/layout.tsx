import type { Metadata, Viewport } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { JsonLd } from "@/components/JsonLd";
import { Providers } from "@/components/Providers";
import { SearchBar } from "@/components/SearchBar";
import { AdBudgetProvider } from "@/components/ads/AdSlot";
import { organizationJsonLd, websiteJsonLd } from "@/lib/seo";
import { SITE_NAME, SITE_URL } from "@/lib/site";

import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: { default: `${SITE_NAME} — electronic component prices, datasheets & tutorials`, template: `%s | ${SITE_NAME}` },
  description:
    "Find any electronic component, compare landed prices from Bangladeshi shops and global distributors, and get datasheets and wiring tutorials.",
  openGraph: { siteName: SITE_NAME, type: "website" },
  icons: { icon: "/icon.svg" },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1, themeColor: "#0e7490" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <a href="#main" className="skip-link">Skip to content</a>
        <JsonLd data={organizationJsonLd()} />
        <JsonLd data={websiteJsonLd()} />
        <header className="border-b border-line">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center">
            <Link href="/" className="text-xl font-bold tracking-tight">
              Volt<span className="text-accent">Find</span>
            </Link>
            <div className="flex-1"><SearchBar /></div>
          </div>
        </header>
        <Providers>
          <AdBudgetProvider>
            <main id="main" className="mx-auto max-w-6xl px-4 py-6">{children}</main>
          </AdBudgetProvider>
        </Providers>
        <footer className="mt-16 border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-6 px-4 py-8 text-sm text-ink-soft sm:grid-cols-3">
            <p>
              VoltFind indexes public product information and links to the seller. We don&apos;t sell, ship or hold stock.
              Prices, images and datasheets belong to and link to their sources.
            </p>
            <ul className="space-y-1">
              <li><Link href="/category">Browse categories</Link></li>
              <li><Link href="/manufacturer">Manufacturers</Link></li>
              <li><Link href="/bangladesh">Buy in Bangladesh</Link></li>
            </ul>
            <ul className="space-y-1">
              <li><Link href="/legal">Privacy &amp; legal</Link></li>
              <li><Link href="/legal/opt-out">Shop owners: opt out</Link></li>
              <li><Link href="/bot">About VoltFindBot</Link></li>
              <li><a href="/sitemap-index.xml">Sitemap</a></li>
            </ul>
          </div>
        </footer>
      </body>
    </html>
  );
}
