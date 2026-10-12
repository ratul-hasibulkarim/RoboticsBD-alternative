const SYMBOL: Record<string, string> = { BDT: "৳", USD: "$", EUR: "€" };

export function money(amount: string | number, currency: string): string {
  const n = typeof amount === "number" ? amount : Number(amount);
  const digits = n !== 0 && Math.abs(n) < 1 ? 3 : 2;
  const formatted = n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: digits });
  const sym = SYMBOL[currency];
  return sym ? `${sym}${formatted}` : `${currency} ${formatted}`;
}

/** USD minor units (cents) → display string in USD. */
export function usdMinor(cents: number | null | undefined): string | null {
  if (cents === null || cents === undefined) return null;
  return money(cents / 100, "USD");
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const diffS = Math.max(0, (now.getTime() - new Date(iso).getTime()) / 1000);
  if (diffS < 60) return "just now";
  const m = Math.floor(diffS / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.floor(h / 24)} days ago`;
}

export function isoDate(iso: string): string {
  return new Date(iso).toISOString().replace("T", " ").slice(0, 16) + " UTC";
}

export function titleCase(slug: string): string {
  return slug.replace(/[-_]/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function eta(days: number): string {
  if (days <= 1) return "1 day";
  const lo = Math.max(1, Math.floor(days - days * 0.3));
  const hi = Math.ceil(days + days * 0.3);
  return lo === hi ? `${lo} days` : `${lo}–${hi} days`;
}
