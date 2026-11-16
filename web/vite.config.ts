import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// 开发期代理到本地网关；构建产物输出 web/dist（gateway /app 挂载点）
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/sessions": "http://127.0.0.1:8000",
      "/runs": "http://127.0.0.1:8000",
      "/memory": "http://127.0.0.1:8000",
      "/status": "http://127.0.0.1:8000",
    },
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
} satisfies import("vitest/config").UserConfig);
