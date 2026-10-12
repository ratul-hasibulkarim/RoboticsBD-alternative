import { isoDate, relativeTime } from "@/lib/format";

const COLORS = { fresh: "bg-good", recent: "bg-warn", stale: "bg-stale" } as const;
const LABEL = { fresh: "updated within 6 hours", recent: "updated within 2 days", stale: "older than 2 days" } as const;

/** Honest freshness signal (§9.3): every price shows "as of" + a dot. */
export function FreshnessDot({ freshness, observedAt }: { freshness: "fresh" | "recent" | "stale"; observedAt: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-soft">
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${COLORS[freshness]}`} />
      <time dateTime={observedAt} title={`${LABEL[freshness]} — ${isoDate(observedAt)}`}>
        as of {relativeTime(observedAt)}
      </time>
    </span>
  );
}
