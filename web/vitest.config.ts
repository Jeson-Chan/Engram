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
    // review medium：tsconfig 已声明 vitest/globals 类型——runtime 同步开启，
    // 否则"忘了 import describe"的测试 tsc 通过、运行时炸
    globals: true,
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
