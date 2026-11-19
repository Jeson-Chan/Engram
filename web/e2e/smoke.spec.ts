/**
 * Playwright smoke — web-research-workbench 任务 5.7。
 *
 * 场景链：新建会话 → 流式回答 → 展开召回记忆 → 刷新恢复（会话/历史/最近 Run）。
 * 前置：先 `python -m engram.backend.app.demo.seed` 预置数据，再起网关（Web UI 开启）。
 * 运行：cd web && npx playwright test
 */

import { expect, test } from "@playwright/test";

test("smoke: session -> streaming answer -> memory -> refresh restore", async ({ page }) => {
  await page.goto("/app");

  // 1. 新建会话（宽/窄壳都有"新建会话"入口；窄屏先开会话抽屉）
  const isNarrow = page.viewportSize() && page.viewportSize()!.width < 900;
  if (isNarrow) {
    await page.getByText("会话", { exact: true }).first().click();
  }
  await page.getByText("+ 新建会话").click();

  // 2. 流式回答：输入问题 → 等回答开始 + 等流终态（send 在 streaming 时禁用）
  const composer = page.getByTestId("composer");
  await expect(composer).toBeVisible();
  await composer.fill("分层记忆怎么实现？");
  await page.getByTestId("send").click();
  const conversation = page.getByTestId("conversation");
  // 流式回答到达（answer 增量渲染；超时容忍模型较慢）
  await expect(
    conversation.locator(".msg.assistant .body").first(),
  ).toBeVisible({ timeout: 90_000 });
  // 等流结束（done 终态 → streaming=false → 按钮文本回到"发送"）
  // ——提前刷新会打断运行（checkpointer 只落已完成的 superstep，历史会缺）
  await expect(page.getByTestId("send")).toHaveText("发送", { timeout: 180_000 });
  await expect(page.locator(".cursor")).toHaveCount(0);

  // 3. Memory Explorer 展开记忆（窄屏走抽屉，宽屏走 Inspector tab）
  if (isNarrow) {
    await page.getByText("Memory", { exact: true }).first().click();
  } else {
    await page.getByText("Memory", { exact: true }).last().click();
  }
  const memoryExplorer = page.getByTestId("memory-explorer");
  await expect(memoryExplorer).toBeVisible();

  // 4. 刷新恢复：同一会话（URL ?s=）+ 历史消息 + 仍可输入
  await page.reload();
  await expect(page.getByTestId("conversation")).toBeVisible();
  await expect(page.getByTestId("composer")).toBeVisible();
  // 历史消息回放（MessageView.role=human → class msg human）
  await expect(
    page.locator(".msg.human, .msg.user").first(),
  ).toBeVisible({ timeout: 30_000 });
});
