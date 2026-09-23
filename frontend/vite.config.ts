import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// Dev proxy: /requests hit the FastAPI backend on :8000 so session cookies
// (same-origin) work during development without CORS machinery.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Same-origin cookies: in dev every API root proxies to FastAPI :8000.
      "^/(auth|me|dashboard|activities|sleep|metrics|coach|settings|integrations|events|context-docs|gym|labs|gear|watch|weather|imports|challenges|rankings|health|docs|openapi.json)": {
        target: "http://localhost:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
    chunkSizeWarningLimit: 1200,
    rollupOptions: {
      output: {
        manualChunks: {
          echarts: ["echarts"],
          vendor: ["react", "react-dom", "react-router-dom", "@tanstack/react-query"],
        },
      },
    },
  },
});
