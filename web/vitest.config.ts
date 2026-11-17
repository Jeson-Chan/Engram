import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

// Vitest 独立配置（与 vite.config.ts 分离：vitest 捆绑的 vite 类型
// 与项目的 vite 6 类型不兼容，合在一个文件会让 tsc -b 报冲突）
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
