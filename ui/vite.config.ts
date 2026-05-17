import path from "node:path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Flask serves the built SPA from `static/dist/`, so build output goes one
// directory up out of `ui/`. Dev proxies /api to gunicorn at :9998 so the SPA
// can talk to the live Flask server without CORS dances.
export default defineConfig({
  plugins: [react()],
  base: "/",
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:9998",
        changeOrigin: true,
      },
      "/login": "http://127.0.0.1:9998",
      "/pair": "http://127.0.0.1:9998",
      "/terminal": "http://127.0.0.1:9998",
    },
  },
  build: {
    outDir: "../static/dist",
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
          radix: [
            "@radix-ui/react-dialog",
            "@radix-ui/react-dropdown-menu",
            "@radix-ui/react-tabs",
            "@radix-ui/react-toast",
          ],
        },
      },
    },
  },
});
