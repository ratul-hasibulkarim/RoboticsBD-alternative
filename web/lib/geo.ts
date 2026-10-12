/** Server-side geo resolution: explicit cookie (user choice) > Cloudflare headers > Dhaka default. */
export type Geo = { country: string; city: string | null; currency: "BDT" | "USD" | "EUR" };

const EURO = new Set(["DE", "FR", "NL", "IT", "ES", "IE", "AT", "BE", "FI", "PT"]);

export function currencyFor(country: string): Geo["currency"] {
  if (country === "BD") return "BDT";
  return EURO.has(country) ? "EUR" : "USD";
}

export const DEFAULT_GEO: Geo = { country: "BD", city: "Dhaka", currency: "BDT" };

export function parseGeoCookie(raw: string | undefined): Partial<Geo> {
  if (!raw) return {};
  const [country, city, currency] = decodeURIComponent(raw).split("|");
  const out: Partial<Geo> = {};
  if (country && /^[A-Z]{2}$/.test(country)) out.country = country;
  if (city) out.city = city.slice(0, 40);
  if (currency === "BDT" || currency === "USD" || currency === "EUR") out.currency = currency;
  return out;
}

export function geoFrom(headers: { get(name: string): string | null }, cookie: string | undefined): Geo {
  const c = parseGeoCookie(cookie);
  const cfCountry = headers.get("cf-ipcountry");
  const country = c.country ?? (cfCountry && /^[A-Z]{2}$/.test(cfCountry) ? cfCountry : DEFAULT_GEO.country);
  const city = c.city ?? headers.get("cf-ipcity") ?? (country === "BD" ? DEFAULT_GEO.city : null);
  return { country, city, currency: c.currency ?? currencyFor(country) };
}

export function geoCookieValue(g: Geo): string {
  return encodeURIComponent([g.country, g.city ?? "", g.currency].join("|"));
}
