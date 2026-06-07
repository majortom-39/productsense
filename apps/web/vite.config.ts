import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5176,
    host: true,
    strictPort: true,
  },
  build: {
    // Split heavy / rarely-mounted vendor bundles into their own chunks
    // so the initial chat-shell payload stays small. recharts (~150 KB
    // gzipped) is the big one — it's only needed when a research card
    // happens to use a chart render_kind.
    rollupOptions: {
      output: {
        manualChunks: {
          recharts: ["recharts"],
          markdown: ["react-markdown", "remark-gfm"],
          supabase: ["@supabase/supabase-js"],
        },
      },
    },
    chunkSizeWarningLimit: 600,
  },
});
