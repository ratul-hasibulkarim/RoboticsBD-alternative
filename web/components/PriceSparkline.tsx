import { usdMinor } from "@/lib/format";

/** Server-rendered SVG price history (§7.3) — visible to crawlers, no JS. */
export function PriceSparkline({ points, width = 240, height = 56 }: { points: Array<{ day: string; min_usd_minor: number }>; width?: number; height?: number }) {
  if (points.length < 2) return <p className="text-xs text-ink-soft">Price history builds up as we re-check prices.</p>;
  const vals = points.map((p) => p.min_usd_minor);
  const lo = Math.min(...vals);
  const hi = Math.max(...vals);
  const span = hi - lo || 1;
  const pad = 4;
  const x = (i: number) => pad + (i * (width - 2 * pad)) / (points.length - 1);
  const y = (v: number) => height - pad - ((v - lo) * (height - 2 * pad)) / span;
  const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.min_usd_minor).toFixed(1)}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  return (
    <figure>
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img"
        aria-label={`Lowest price from ${usdMinor(first?.min_usd_minor)} on ${first?.day} to ${usdMinor(last?.min_usd_minor)} on ${last?.day}`}>
        <path d={d} fill="none" stroke="currentColor" strokeWidth={2} className="text-accent" />
        <circle cx={x(points.length - 1)} cy={y(last?.min_usd_minor ?? lo)} r={3} className="fill-accent" />
      </svg>
      <figcaption className="text-xs text-ink-soft">
        {points.length}-day low: {usdMinor(lo)} · high: {usdMinor(hi)} (USD, lowest landed per day)
      </figcaption>
    </figure>
  );
}
