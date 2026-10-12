"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

const COUNTRIES: Array<[string, string]> = [["BD", "Bangladesh"], ["IN", "India"], ["US", "United States"], ["GB", "United Kingdom"], ["DE", "Germany"], ["SG", "Singapore"]];
const BD_CITIES = ["Dhaka", "Chattogram", "Khulna", "Rajshahi", "Sylhet", "Barishal", "Rangpur", "Mymensingh", "Cumilla", "Gazipur"];

/** Shows whose prices you see and lets users change it (stored in a first-party cookie). */
export function GeoBanner({ country, city, currency }: { country: string; city: string | null; currency: string }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [c, setC] = useState(country);
  const [ci, setCi] = useState(city ?? "");
  const [cur, setCur] = useState(currency);
  const save = () => {
    document.cookie = `vf_geo=${encodeURIComponent([c, c === "BD" ? ci : "", cur].join("|"))}; path=/; max-age=31536000; samesite=lax`;
    setOpen(false);
    router.refresh();
  };
  return (
    <div className="text-sm text-ink-soft">
      Prices for <strong className="text-ink">{city ? `${city}, ` : ""}{country}</strong> in {currency} ·{" "}
      <button type="button" className="text-accent underline" onClick={() => setOpen((v) => !v)} aria-expanded={open}>change</button>
      {open ? (
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="flex flex-col">Country
            <select value={c} onChange={(e) => setC(e.target.value)} className="h-11 rounded-lg border border-line bg-surface px-2 text-ink">
              {COUNTRIES.map(([code, name]) => <option key={code} value={code}>{name}</option>)}
            </select>
          </label>
          {c === "BD" ? (
            <label className="flex flex-col">City
              <select value={ci} onChange={(e) => setCi(e.target.value)} className="h-11 rounded-lg border border-line bg-surface px-2 text-ink">
                {BD_CITIES.map((x) => <option key={x}>{x}</option>)}
              </select>
            </label>
          ) : null}
          <label className="flex flex-col">Currency
            <select value={cur} onChange={(e) => setCur(e.target.value)} className="h-11 rounded-lg border border-line bg-surface px-2 text-ink">
              {["BDT", "USD", "EUR"].map((x) => <option key={x}>{x}</option>)}
            </select>
          </label>
          <button type="button" onClick={save} className="h-11 rounded-lg bg-accent px-4 text-white dark:text-slate-950">Save</button>
        </div>
      ) : null}
    </div>
  );
}
