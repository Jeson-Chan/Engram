import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期代理到本地网关；构建产物输出 web/dist（gateway /app 挂载点）。
// Vitest 配置在 vitest.config.ts（单独拆分——类型冲突，见该文件说明）。
export default defineConfig({
  plugins: [react()],
  // SPA 挂载在网关 /app 下（web_ui.py）——资源引用必须以 /app/ 为基
  base: "/app/",
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
});
