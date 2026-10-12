// Start `next start` in its own process group so the whole tree (npx → next-server) can be stopped.
import { spawn } from "node:child_process";

export async function startNext(port, env) {
  const child = spawn("npx", ["next", "start", "-p", String(port)], { env, stdio: ["ignore", "ignore", "inherit"], detached: true });
  const stop = () => {
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already gone */ }
  };
  process.on("exit", stop);
  for (let i = 0; i < 120; i++) {
    try {
      if ((await fetch(`http://127.0.0.1:${port}/robots.txt`)).ok) return stop;
    } catch { /* starting */ }
    await new Promise((r) => setTimeout(r, 500));
  }
  stop();
  throw new Error(`next start on :${port} did not come up`);
}
