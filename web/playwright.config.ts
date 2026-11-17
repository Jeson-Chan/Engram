import { defineConfig } from "@playwright/test";

/**
 * Playwright smoke 配置（任务 5.7）。
 *
 * - baseURL 指向本地网关（scripts/demo.py 起的 /app）
 * - 浏览器走系统 Edge 通道（channel: msedge）——Win11 自带，
 *   无需下载 playwright 二进制（演示网络受限的环境兼容）
 * - 视口窄/宽各跑一遍（响应式壳的冒烟）
 */
export default defineConfig({
  testDir: "./e2e",
  // 真实 LLM 流式轮次（慢模型可达 1-3 分钟）—— smoke 每条链含 1 轮对话
  timeout: 300_000,
  retries: 0,
  use: {
    baseURL: process.env.ENGRAM_WEB_URL || "http://127.0.0.1:8000",
    channel: "msedge",
    headless: true,
    viewport: { width: 1280, height: 800 },
    trace: "off",
  },
  projects: [
    { name: "desktop", use: { viewport: { width: 1280, height: 800 } } },
    { name: "narrow", use: { viewport: { width: 480, height: 800 } } },
  ],
});
