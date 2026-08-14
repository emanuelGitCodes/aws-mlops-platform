import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The dev server proxies `/api` to the backend, so the browser sends
// same-origin requests and the backend needs no CORS configuration. In the
// deployed shape CloudFront routes `/api/*` to the same origin, so the
// frontend code never holds a backend URL.
const backend = process.env.BACKEND_ORIGIN ?? "http://localhost:8080";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
