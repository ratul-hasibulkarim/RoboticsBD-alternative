import { Badge } from "./ui/primitives";

/** Attribution is mandatory (LEGAL rule 8): every price/image/datasheet names its source. */
export function SourceBadge({ name, domain, trust }: { name: string; domain: string; trust: number }) {
  const level = trust >= 0.9 ? "Authorised distributor" : trust >= 0.75 ? "Established shop" : "Shop";
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <span className="font-medium" data-testid="source-name">
        {name}
      </span>
      <Badge title={`${domain} — trust ${Math.round(trust * 100)}%`}>{level}</Badge>
    </span>
  );
}
