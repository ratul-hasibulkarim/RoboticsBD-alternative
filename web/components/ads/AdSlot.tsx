"use client";
/**
 * The single ad component (§11.2). Rules enforced here, mirrored from placement_policy.yaml
 * (scripts/check_ads_policy.py fails CI if they drift):
 *  - only allowed placements, only on their templates; hard ceiling of 3 slots per page
 *  - space is reserved up front (fixed min-height) → zero CLS
 *  - lazy: the ad request happens only when the slot nears the viewport, i.e. after the
 *    user has seen the primary content (slots are only placed below it)
 *  - sidebar only on viewports ≥ 1280 px; nothing sticky on mobile
 *  - consent: without ad consent, requests are non-personalised (npa=1)
 *  - auto-generated content that has not been human-reviewed never carries ads
 */
import { createContext, type ReactNode, useContext, useEffect, useRef, useState } from "react";

export type Placement = "in_feed_native" | "sidebar_sticky" | "below_offers" | "article_footer";
export type Template = "component" | "prices" | "search" | "category" | "manufacturer" | "use_case" | "guide";

export const POLICY = {
  maxSlotsPerPage: 3,
  allowed: {
    in_feed_native: { templates: ["search", "category", "manufacturer"], minHeight: 120 },
    sidebar_sticky: { templates: ["component", "search", "category"], minHeight: 600, minViewport: 1280 },
    below_offers: { templates: ["component", "prices"], minHeight: 250 },
    article_footer: { templates: ["use_case", "guide"], minHeight: 250 },
  },
  requireReviewed: ["component", "guide"],
} as const satisfies {
  maxSlotsPerPage: number;
  allowed: Record<Placement, { templates: readonly Template[]; minHeight: number; minViewport?: number }>;
  requireReviewed: readonly Template[];
};

type Ctx = { claim: (id: string) => boolean; release: (id: string) => void };
const AdBudget = createContext<Ctx | null>(null);

export function AdBudgetProvider({ children }: { children: ReactNode }) {
  const claimed = useRef(new Set<string>());
  const ctx: Ctx = {
    claim: (id) => {
      if (claimed.current.has(id)) return true;
      if (claimed.current.size >= POLICY.maxSlotsPerPage) return false;
      claimed.current.add(id);
      return true;
    },
    release: (id) => {
      claimed.current.delete(id);
    },
  };
  return <AdBudget.Provider value={ctx}>{children}</AdBudget.Provider>;
}

export function isAllowed(placement: Placement, template: Template, contentReviewed: boolean): boolean {
  const rule = POLICY.allowed[placement];
  const templates: readonly Template[] = rule.templates;
  if (!templates.includes(template)) return false;
  const needsReview: readonly Template[] = POLICY.requireReviewed;
  if (needsReview.includes(template) && !contentReviewed) return false;
  return true;
}

function hasAdConsent(): boolean {
  try {
    return document.cookie.split("; ").some((c) => c === "vf_ad_consent=1");
  } catch {
    return false;
  }
}

declare global {
  interface Window {
    adsbygoogle?: unknown[];
  }
}

export function AdSlot({
  id,
  placement,
  template,
  contentReviewed = true,
  client,
  slot,
}: {
  id: string;
  placement: Placement;
  template: Template;
  contentReviewed?: boolean;
  client: string;
  slot: string;
}) {
  const budget = useContext(AdBudget);
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [granted, setGranted] = useState(false);
  const rule = POLICY.allowed[placement];
  const allowed = isAllowed(placement, template, contentReviewed) && Boolean(client) && Boolean(slot);

  useEffect(() => {
    if (!allowed || !budget) return;
    const minViewport = "minViewport" in rule ? rule.minViewport : 0;
    if (window.innerWidth < minViewport) return;
    if (!budget.claim(id)) return;
    setGranted(true);
    return () => budget.release(id);
  }, [allowed, budget, id, rule]);

  useEffect(() => {
    if (!granted || !ref.current) return;
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    io.observe(ref.current);
    return () => io.disconnect();
  }, [granted]);

  useEffect(() => {
    if (!visible) return;
    if (!document.querySelector("script[data-vf-adsense]")) {
      const s = document.createElement("script");
      s.async = true;
      s.src = `https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=${encodeURIComponent(client)}`;
      s.crossOrigin = "anonymous";
      s.dataset.vfAdsense = "1";
      document.head.appendChild(s);
    }
    (window.adsbygoogle = window.adsbygoogle ?? []).push({});
  }, [visible, client]);

  // Over budget (or viewport too narrow): render nothing. scripts/check_ads_policy.py keeps every
  // template at ≤ 3 slots statically, so this runtime cap is a backstop, not a layout path.
  if (!allowed || !granted) return null;
  return (
    <aside aria-label="Advertisement" data-ad-placement={placement} ref={ref}
      className={placement === "sidebar_sticky" ? "sticky top-4 hidden xl:block" : "my-8"}
      style={{ minHeight: rule.minHeight }}>
      <p className="mb-1 text-[10px] uppercase tracking-wide text-ink-soft">Advertisement</p>
      {visible ? (
        <ins className="adsbygoogle block" style={{ display: "block", minHeight: rule.minHeight - 16 }}
          data-ad-client={client} data-ad-slot={slot} data-ad-format="auto" data-full-width-responsive="true"
          data-npa={hasAdConsent() ? undefined : "1"} />
      ) : null}
    </aside>
  );
}
