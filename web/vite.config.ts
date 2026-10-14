/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

// In development the dashboard runs on Vite (5173) and proxies /api (REST + WebSocket) to the core on 127.0.0.1:8787,
// so the browser sees one origin and the SameSite=Strict session cookie works. In production the core serves the build.
export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    // FG_API_TARGET lets the end-to-end tests point the proxy at a throw-away core instance
    proxy: { "/api": { target: process.env.FG_API_TARGET ?? "http://127.0.0.1:8787", changeOrigin: false, ws: true } },
  },
  build: { outDir: "dist", sourcemap: true },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
