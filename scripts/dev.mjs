import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
const root = fileURLToPath(new URL("../", import.meta.url));
const jobs = [];
let closing = false;
function close(code = 0) {
  if (closing) return;
  closing = true;
  process.exitCode = code;
  for (const job of jobs) {
    try {
      if (job.pid && process.platform !== "win32")
        process.kill(-job.pid, "SIGTERM");
      else job.kill("SIGTERM");
    } catch {
      /* The process may already have exited. */
    }
  }
  setTimeout(() => process.exit(code), 500).unref();
}
function launch(command, args, directory) {
  const job = spawn(command, args, {
    cwd: join(root, directory),
    stdio: "inherit",
    detached: process.platform !== "win32",
  });
  jobs.push(job);
  job.on("error", (error) => {
    console.error(error.message);
    close(1);
  });
  job.on("exit", (code) => {
    if (!closing) close(code || 0);
  });
  return job;
}
process.on("SIGINT", () => close());
process.on("SIGTERM", () => close());
launch("uv", ["run", "python", "-m", "powernext", "serve", "--reload"], "backend");
const target = process.env.POWERNEXT_BACKEND_URL || "http://127.0.0.1:8000";
let ready = false;
for (let attempt = 0; attempt < 100 && !closing; attempt++) {
  try {
    const response = await fetch(`${target}/health`, {
      signal: AbortSignal.timeout(400),
    });
    if (response.ok) {
      ready = true;
      break;
    }
  } catch {
    /* The backend is still starting. */
  }
  await new Promise((resolve) => setTimeout(resolve, 200));
}
if (!closing && ready) {
  launch("npm", ["run", "dev"], "frontend");
  console.log(
    `PowerNext dashboard: http://127.0.0.1:5173 · Backend: ${target}`,
  );
} else if (!closing) {
  console.error("Backend did not become ready; inspect its startup output.");
  close(1);
}
