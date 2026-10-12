"use client";

export type Mode = "cheapest" | "best" | "fastest";
const TABS: Array<{ id: Mode; label: string }> = [
  { id: "cheapest", label: "Cheapest" },
  { id: "best", label: "Best overall" },
  { id: "fastest", label: "Fastest" },
];

export function SortTabs({ value, onChange }: { value: Mode; onChange: (m: Mode) => void }) {
  return (
    <div role="tablist" aria-label="Sort offers" className="inline-flex rounded-lg border border-line p-1">
      {TABS.map((t) => (
        <button
          key={t.id}
          role="tab"
          type="button"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={`min-h-11 rounded-md px-3 text-sm ${value === t.id ? "bg-accent text-white dark:text-slate-950" : "text-ink-soft hover:text-ink"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
