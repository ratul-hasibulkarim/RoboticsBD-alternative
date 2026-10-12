import { z } from "zod";

import { Card, Categories, Compare, ComponentDetail, Manufacturers, Offers, Paged, SearchResponse, SitemapCount, SitemapEntries, UseCase } from "@/lib/api";

import { allFixtures } from "./fixtures";

/** Every exported API response must parse with the web's Zod schemas (API ↔ web contract). */
const SCHEMA_FOR: Array<[RegExp, z.ZodType]> = [
  [/^\/v1\/components\/[^/?]+\?/, ComponentDetail],
  [/\/offers\?/, Offers],
  [/\/use-cases$/, z.array(UseCase)],
  [/\/alternatives\?/, z.array(Card)],
  [/^\/v1\/categories$/, Categories],
  [/^\/v1\/categories\/.+/, Paged],
  [/^\/v1\/manufacturers$/, Manufacturers],
  [/^\/v1\/manufacturers\/.+/, Paged],
  [/^\/v1\/trending/, z.array(Card)],
  [/^\/v1\/sitemap\/components/, SitemapEntries],
  [/^\/v1\/sitemap\/count/, SitemapCount],
  [/^\/v1\/sitemap\/retired/, z.array(z.string())],
  [/^\/v1\/search/, SearchResponse],
  [/^\/v1\/compare/, Compare],
];

describe("API contract", () => {
  for (const [path, body] of allFixtures()) {
    it(path, () => {
      const match = SCHEMA_FOR.find(([re]) => re.test(path));
      expect(match, `no schema mapped for ${path}`).toBeDefined();
      match?.[1].parse(body);
    });
  }
});
