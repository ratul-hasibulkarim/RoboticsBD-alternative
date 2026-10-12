import { render, screen } from "@testing-library/react";

import { OfferRow } from "@/components/OfferRow";
import { Offers } from "@/lib/api";

import { fixture } from "./fixtures";

const offers = Offers.parse(fixture("/v1/components/esp32-wroom-32/offers?country=BD&city=Dhaka&currency=BDT")).offers;

describe("LEGAL rule 8 — attribution & honest prices", () => {
  it("every offer names its source, links out, and shows an 'as of' time", () => {
    for (const o of offers) {
      const { unmount } = render(<ul><OfferRow offer={o} /></ul>);
      expect(screen.getByTestId("source-name")).toHaveTextContent(o.source.display_name);
      const link = screen.getByRole("link", { name: new RegExp(`View at ${o.source.display_name}`) });
      expect(link).toHaveAttribute("href", o.go_url);
      expect(link).toHaveAttribute("target", "_blank");
      expect(link.getAttribute("rel")).toContain("noopener");
      expect(screen.getByText(/as of/)).toBeInTheDocument();
      unmount();
    }
  });

  it("rel=sponsored only on affiliate links", () => {
    const sponsored = offers.find((o) => o.sponsored);
    const organic = offers.find((o) => !o.sponsored);
    expect(sponsored && organic).toBeTruthy();
    if (!sponsored || !organic) return;
    const a = render(<ul><OfferRow offer={sponsored} /></ul>);
    expect(a.getByRole("link").getAttribute("rel")).toContain("sponsored");
    a.unmount();
    const b = render(<ul><OfferRow offer={organic} /></ul>);
    expect(b.getByRole("link").getAttribute("rel")).not.toContain("sponsored");
  });
});
