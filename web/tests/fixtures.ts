import { readFileSync } from "node:fs";
import { join } from "node:path";

const dir = join(__dirname, "fixtures", "api");
const index: Record<string, { file: string; status: number }> = JSON.parse(readFileSync(join(dir, "index.json"), "utf8"));

export function fixture(path: string): unknown {
  const hit = index[path];
  if (!hit) throw new Error(`no fixture for ${path}`);
  return JSON.parse(readFileSync(join(dir, hit.file), "utf8"));
}

export const allFixtures = (): Array<[string, unknown]> => Object.keys(index).map((p) => [p, fixture(p)]);
