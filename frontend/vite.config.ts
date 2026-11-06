import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const target = process.env.VITE_API_TARGET || "http://127.0.0.1:8760";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, host: "127.0.0.1", proxy: { "/api": { target, changeOrigin: true } } },
  build: { outDir: "dist", emptyOutDir: true, assetsDir: "assets" },
});
