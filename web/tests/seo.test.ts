import { ComponentDetail } from "@/lib/api";
import { breadcrumbJsonLd, faqJsonLd, jsonLdString, productJsonLd, websiteJsonLd } from "@/lib/seo";
import { validateJsonLd } from "@/scripts/schema-rules";

import { fixture } from "./fixtures";

const c = ComponentDetail.parse(fixture("/v1/components/esp32-wroom-32?country=BD&city=Dhaka&currency=BDT&track=false"));

describe("JSON-LD (W3)", () => {
  it("Product has AggregateOffer with low/high/count/currency", () => {
    const p = productJsonLd(c);
    expect(validateJsonLd(p)).toEqual([]);
    expect(p.offers).toMatchObject({ "@type": "AggregateOffer", priceCurrency: "BDT", offerCount: c.offer_count });
  });
  it("breadcrumbs, FAQ and WebSite validate", () => {
    expect(validateJsonLd(breadcrumbJsonLd(c))).toEqual([]);
    const faq = faqJsonLd(c);
    expect(faq).not.toBeNull();
    if (faq) expect(validateJsonLd(faq)).toEqual([]);
    expect(validateJsonLd(websiteJsonLd())).toEqual([]);
  });
  it("serialisation cannot break out of the script tag", () => {
    const evil = { ...c, title: "</script><script>alert(1)</script>" };
    expect(jsonLdString(productJsonLd(evil))).not.toContain("</script>");
  });
});
