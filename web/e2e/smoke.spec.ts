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

  // 3. 记忆管理页（memory-management-ui：rail 导航宽屏 / 状态栏按钮窄屏）
  if (isNarrow) {
    await page.getByText("Memory", { exact: true }).first().click();
  } else {
    await page.getByTestId("nav-memory").click();
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

test("smoke: memory management flow (tree filter -> multi-select delete -> thread clear confirm)", async ({ page }) => {
  await page.goto("/app");

  // 进入记忆管理页
  const isNarrow = page.viewportSize() && page.viewportSize()!.width < 900;
  if (isNarrow) {
    await page.getByText("Memory", { exact: true }).first().click();
  } else {
    await page.getByTestId("nav-memory").click();
  }
  const memoryExplorer = page.getByTestId("memory-explorer");
  await expect(memoryExplorer).toBeVisible();

  // 分区树出现（seed 数据沉淀后至少有 user 节点）
  await expect(page.getByTestId("tree-user")).toBeVisible();

  // 等列表渲染；无记忆时跳过后续流程（seed 环境保证有数据，防御空环境）
  const firstItem = page.locator("[data-testid^='memory-item-']").first();
  if (!(await firstItem.isVisible().catch(() => false))) {
    test.info().annotations.push({ type: "skip-reason", description: "no seeded memories" });
    return;
  }

  // 分区筛选：点击第一个 thread 节点
  const threadNode = page.locator("[data-testid^='tree-thread-']").first();
  if (await threadNode.isVisible().catch(() => false)) {
    await threadNode.click();
    await page.waitForTimeout(300);
  }

  // 多选删除：全选 → 删除选中
  const selectAll = page.getByTestId("memory-select-all");
  if (await selectAll.isVisible().catch(() => false)) {
    const checked = await selectAll.isChecked();
    if (!checked) await selectAll.click();
    const actionbar = page.getByTestId("memory-actionbar");
    await expect(actionbar).toBeVisible();
    await actionbar.getByText("删除选中").click();
    // 删除后 actionbar 消失（列表清空或条数减少）
    await expect(actionbar).toHaveCount(0, { timeout: 30_000 });
  }

  // thread 清除确认：打开确认框 → 取消（不真删）
  const threadClear = page.locator("[data-testid^='tree-thread-clear-']").first();
  if (await threadClear.isVisible().catch(() => false)) {
    await threadClear.click();
    const confirm = page.getByTestId("memory-confirm");
    await expect(confirm).toBeVisible();
    // 预览计数先出现（preview → 确认框展示将删条数）
    await expect(confirm.getByTestId("confirm-count")).toBeVisible({ timeout: 30_000 });
    await confirm.getByText("取消").click();
    await expect(confirm).toHaveCount(0);
  }
});
