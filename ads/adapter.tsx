/**
 * Spec path (§12) for the ad adapter. The implementation lives inside the Next.js app so it
 * resolves the app's React: web/components/ads/AdSlot.tsx. Policy: ads/placement_policy.yaml.
 */
export { AdBudgetProvider, AdSlot, isAllowed, POLICY } from "../web/components/ads/AdSlot";
export type { Placement, Template } from "../web/components/ads/AdSlot";
