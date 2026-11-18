import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

// 开发期代理到本地网关；构建产物输出 web/dist（gateway /app 挂载点）。
// Vitest 配置在 vitest.config.ts（单独拆分——类型冲突，见该文件说明）。
export default defineConfig({
  plugins: [react()],
  // SPA 挂载在网关 /app 下（web_ui.py）——资源引用必须以 /app/ 为基
  base: "/app/",
  // review medium：与 tsconfig.paths / vitest.config 的 alias 保持同步
  //（否则 tsc 通过的 @/x 导入在 dev/build 解析失败）
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
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
