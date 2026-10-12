import type { TOffer } from "@/lib/api";
import { eta, money } from "@/lib/format";

import { FreshnessDot } from "./FreshnessDot";
import { SourceBadge } from "./SourceBadge";
import { LinkButton } from "./ui/primitives";

export function OfferRow({ offer, highlight = false }: { offer: TOffer; highlight?: boolean }) {
  const rel = offer.sponsored ? "noopener sponsored nofollow" : "noopener nofollow";
  const per = offer.landed_per_unit;
  return (
    <li
      className={`grid grid-cols-1 gap-3 border-b border-line p-4 last:border-b-0 sm:grid-cols-[1fr_auto_auto] sm:items-center ${highlight ? "bg-accent-soft" : ""}`}
      data-testid="offer-row"
    >
      <div className="min-w-0">
        <SourceBadge name={offer.source.display_name} domain={offer.source.domain} trust={offer.source.trust_score} />
        <p className="mt-1 truncate text-sm text-ink-soft" title={offer.title}>
          {offer.title}
        </p>
        <p className="mt-1 flex flex-wrap items-center gap-3 text-xs text-ink-soft">
          <FreshnessDot freshness={offer.freshness} observedAt={offer.observed_at} />
          <span>{offer.in_stock === false ? "Out of stock" : offer.stock_qty ? `${offer.stock_qty.toLocaleString()} in stock` : offer.in_stock ? "In stock" : "Stock unknown"}</span>
          <span>Delivery ~{eta(offer.eta_days)}</span>
          {offer.ships_from ? <span>Ships from {offer.ships_from}</span> : null}
          {offer.moq > 1 ? <span>MOQ {offer.moq}</span> : null}
        </p>
      </div>
      <div className="text-left sm:text-right">
        <p className="text-lg font-semibold tabular-nums" data-testid="offer-price">
          {money(per.amount, per.currency)}
          <span className="text-xs font-normal text-ink-soft"> / unit landed</span>
        </p>
        <p className="text-xs text-ink-soft tabular-nums">
          {money(offer.unit_price.amount, offer.unit_price.currency)} + ship {money(offer.shipping.amount, offer.shipping.currency)}
          {Number(offer.duty_estimate.amount) > 0 ? ` + duty est. ${money(offer.duty_estimate.amount, offer.duty_estimate.currency)}` : ""}
        </p>
      </div>
      <LinkButton href={offer.go_url} target="_blank" rel={rel} aria-label={`View at ${offer.source.display_name} (opens in new tab)`}>
        View at {offer.source.display_name}
        {offer.sponsored ? <span className="sr-only"> (affiliate link)</span> : null}
      </LinkButton>
    </li>
  );
}
