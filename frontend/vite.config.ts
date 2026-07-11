import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Where the Django API lives. dev.sh sets VITE_BACKEND_URL to match the
// backend host/port; defaults to the local Django dev server.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

// Dev-server host/port, overridable for remote/HPC use (e.g. VITE_HOST=0.0.0.0).
const host = process.env.VITE_HOST || "127.0.0.1";
const port = Number(process.env.VITE_PORT || "5173");

export default defineConfig({
  plugins: [react()],
  server: {
    host,
    port,
    // The dev server proxies API + media requests to the Django backend so the
    // SPA can use same-origin relative URLs.
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/media": { target: backend, changeOrigin: true },
    },
  },
});
