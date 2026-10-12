import { render } from "@testing-library/react";

import { AdBudgetProvider, AdSlot, POLICY, isAllowed } from "@/components/ads/AdSlot";

class IO {
  observe() {}
  disconnect() {}
}

beforeAll(() => {
  Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  Object.defineProperty(window, "IntersectionObserver", { value: IO, configurable: true });
});

describe("ad policy (§11)", () => {
  it("rejects placements on templates they are not allowed on", () => {
    expect(isAllowed("below_offers", "component", true)).toBe(true);
    expect(isAllowed("in_feed_native", "component", true)).toBe(false);
    expect(isAllowed("article_footer", "search", true)).toBe(false);
  });

  it("never runs ads on unreviewed auto-generated content", () => {
    expect(isAllowed("below_offers", "component", false)).toBe(false);
  });

  it("caps slots per page at 3 and reserves space", () => {
    const { container } = render(
      <AdBudgetProvider>
        {["a", "b", "c", "d", "e"].map((id) => (
          <AdSlot key={id} id={id} placement="sidebar_sticky" template="search" client="ca-pub-1" slot="1" />
        ))}
      </AdBudgetProvider>,
    );
    const slots = container.querySelectorAll("[data-ad-placement]");
    expect(POLICY.maxSlotsPerPage).toBe(3);
    expect(slots.length).toBe(3);
    // ad requests happen only once a claimed slot nears the viewport
    expect(container.querySelectorAll("ins.adsbygoogle").length).toBe(0);
    for (const s of slots) expect((s as HTMLElement).style.minHeight).toBe("600px");
  });

  it("hides the sidebar on viewports narrower than 1280 px", () => {
    Object.defineProperty(window, "innerWidth", { value: 375, configurable: true });
    const { container } = render(
      <AdBudgetProvider><AdSlot id="s" placement="sidebar_sticky" template="search" client="ca-pub-1" slot="1" /></AdBudgetProvider>,
    );
    expect(container).toBeEmptyDOMElement();
    Object.defineProperty(window, "innerWidth", { value: 1440, configurable: true });
  });

  it("renders nothing without a configured AdSense client", () => {
    const { container } = render(<AdSlot id="x" placement="below_offers" template="component" client="" slot="" />);
    expect(container).toBeEmptyDOMElement();
  });
});
