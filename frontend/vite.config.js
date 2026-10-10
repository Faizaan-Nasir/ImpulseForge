import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.POWERNEXT_BACKEND_URL || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: { "/v1": { target }, "/health": { target } },
    },
    test: { environment: "jsdom", setupFiles: ["./tests/setup.js"] },
  };
});
