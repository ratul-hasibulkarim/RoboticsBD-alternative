import { notFound, permanentRedirect } from "next/navigation";
import { cache } from "react";

import { ApiError, type TComponent, getComponent, goneInfo } from "./api";
import { DEFAULT_GEO } from "./geo";

/**
 * Loads a component for its ISR pages (default market: Dhaka/BDT).
 * 404 → notFound(); merged → permanent redirect; retired → 410 is served by middleware.ts.
 */
export const loadComponent = cache(async (slug: string): Promise<TComponent> => {
  try {
    return await getComponent(slug, DEFAULT_GEO.city ? { country: DEFAULT_GEO.country, city: DEFAULT_GEO.city, currency: DEFAULT_GEO.currency } : {});
  } catch (err) {
    const gone = goneInfo(err);
    if (gone?.status === "merged" && gone.redirect_to) permanentRedirect(`/component/${gone.redirect_to}`);
    if (err instanceof ApiError && (err.status === 404 || err.status === 410)) notFound();
    throw err;
  }
});
