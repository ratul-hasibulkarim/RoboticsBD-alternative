/**
 * E2 (search → component → best price → click-out in < 30 s, zero errors) and
 * E3 (375×667: no horizontal scroll, primary controls reachable).
 * Run via web/scripts/e2e.mjs, which serves the built site against the fixture API.
 */
import { expect, test } from "@playwright/test";

test.describe("E3 — mobile 375×667", () => {
  test.use({ viewport: { width: 375, height: 667 }, isMobile: true, hasTouch: true });

  for (const path of ["/", "/search?q=esp32", "/component/esp32-wroom-32", "/component/esp32-wroom-32/prices", "/category/wireless"]) {
    test(`no horizontal scroll on ${path}`, async ({ page }) => {
      await page.goto(path);
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }

  test("offer buttons are reachable and tap-sized", async ({ page }) => {
    await page.goto("/component/esp32-wroom-32");
    const btn = page.getByRole("link", { name: /View at Demo Robotics BD/ }).first();
    await btn.scrollIntoViewIfNeeded();
    await expect(btn).toBeVisible();
    const box = await btn.boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
    expect((box?.x ?? -1) >= 0 && (box?.x ?? 0) + (box?.width ?? 0) <= 375).toBe(true);
  });
});

test("E2 — search → part → best price → click-out under 30 s with no errors", async ({ page, context }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const t0 = Date.now();
  await page.goto("/");
  await page.getByRole("searchbox", { name: /Search part number/ }).first().fill("esp32");
  await page.getByRole("button", { name: "Search" }).first().click();
  await page.getByRole("link", { name: /ESP32-WROOM-32/ }).first().click();
  await expect(page.getByTestId("price-box")).toBeVisible();
  const [outbound] = await Promise.all([
    context.waitForEvent("page"),
    page.getByRole("link", { name: /View at / }).first().click(),
  ]);
  await outbound.waitForLoadState();
  expect(outbound.url()).toContain("/landing");
  expect(Date.now() - t0).toBeLessThan(30_000);
  expect(errors.filter((e) => !/Failed to load resource/.test(e))).toEqual([]);
});
