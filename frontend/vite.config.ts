import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies API + media requests to the Django backend so the
// SPA can use same-origin relative URLs. Override the target with
// VITE_BACKEND_URL if the backend runs elsewhere.
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/media": { target: backend, changeOrigin: true },
    },
  },
});
