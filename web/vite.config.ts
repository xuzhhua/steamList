import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 后端在 8080 端口托管 API 与构建产物（app/static）；开发期由 Vite 代理 /api。
export default defineConfig({
  plugins: [react()],
  base: "/",
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
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
          vendor: ["react", "react-dom", "react-router-dom"],
          echarts: ["echarts"],
        },
      },
    },
  },
});
