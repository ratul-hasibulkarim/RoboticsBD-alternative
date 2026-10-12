// Runs the Playwright journeys (E2, E3) against the built site + fixture API.
//   npm run build (with API_URL=http://127.0.0.1:8765) && node scripts/e2e.mjs
import { spawn } from "node:child_process";

import { startMockApi } from "./mock-api.mjs";
import { startNext } from "./next-server.mjs";

const env = { ...process.env, API_URL: "http://127.0.0.1:8765", NEXT_PUBLIC_SITE_URL: "https://voltfind.test", NEXT_TELEMETRY_DISABLED: "1" };
const mock = await startMockApi(8765);
const stopWeb = await startNext(3100, env);
const code = await new Promise((resolve) => spawn("npx", ["playwright", "test"], { env, stdio: "inherit" }).on("exit", resolve));
stopWeb();
mock.close();
process.exit(code ?? 1);
