/** Plain GET form: works without JS, sitelinks-searchbox compatible (/search?q=). */
export function SearchBar({ defaultValue = "", autoFocus = false, size = "md" }: { defaultValue?: string; autoFocus?: boolean; size?: "md" | "lg" }) {
  return (
    <form action="/search" method="get" role="search" className="flex w-full gap-2">
      <label htmlFor={`q-${size}`} className="sr-only">Search part number or keyword</label>
      <input id={`q-${size}`} name="q" type="search" defaultValue={defaultValue} autoFocus={autoFocus} required maxLength={200}
        placeholder="Part number or keyword — e.g. ESP32-WROOM-32, 74HC595, buck converter"
        className={`w-full rounded-lg border border-line bg-surface px-4 text-ink placeholder:text-ink-soft ${size === "lg" ? "h-14 text-lg" : "h-11"}`} />
      <button type="submit" className={`rounded-lg bg-accent px-5 font-medium text-white dark:text-slate-950 ${size === "lg" ? "h-14" : "h-11"}`}>Search</button>
    </form>
  );
}
