"use client";

import { useEffect, useState } from "react";

import { DEFAULT_GEO, type Geo, parseGeoCookie } from "./geo";

/** Client geo: the vf_geo cookie (user's choice) over the server default. */
export function useGeo(initial: Geo = DEFAULT_GEO): Geo {
  const [geo, setGeo] = useState<Geo>(initial);
  useEffect(() => {
    const raw = document.cookie.split("; ").find((c) => c.startsWith("vf_geo="))?.slice(7);
    const c = parseGeoCookie(raw);
    if (c.country || c.currency) setGeo({ ...initial, ...c, city: c.country && c.country !== "BD" ? null : (c.city ?? initial.city) });
  }, [initial]);
  return geo;
}
