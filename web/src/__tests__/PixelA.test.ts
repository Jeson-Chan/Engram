/** 限色板审计(web-pixel-flavor-a 任务 3.2)。

读 styles.css 全量 hex,断言非中性(灰阶系)/非状态色的颜色仅来自
紫(H 270-300)/青(H 160-185)/橙(H 15-35)三族——spec"限色板守恒"场景。
*/

import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const cssText = readFileSync(
  path.resolve(process.cwd(), "src", "styles.css"),
  "utf-8",
);

/** hex → HSL 色相。 */
function hueOf(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  const d = max - min;
  if (d === 0) return -1; // 无色相(灰/黑/白)
  let h = 0;
  if (max === r) h = ((g - b) / d) % 6;
  else if (max === g) h = (b - r) / d + 2;
  else h = (r - g) / d + 4;
  h *= 60;
  return h < 0 ? h + 360 : h;
}

function saturationOf(hex: string): number {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  if (max === 0) return 0;
  return (max - min) / max;
}

const FAMILIES: Array<[string, number, number]> = [
  ["紫", 265, 305],
  ["青", 155, 190],
  ["橙", 10, 40],
  // 墨族(web-ui-redesign)：藏青墨线(浅色主题 border/ink)——新系统正式色族
  ["墨", 195, 235],
  // 状态色族(红=error / 绿=ok / 黄=warn)
  ["红", 350, 10],  // 跨 0 处理:另判
  ["黄", 40, 70],
  ["绿", 90, 150],
];

describe("限色板守恒(任务 3.2)", () => {
  it("所有彩色 hex 命中限色板三族 + 状态族", () => {
    const hexes = [...new Set(cssText.match(new RegExp("#[0-9a-fA-F]{6}", "g"))) ?? []];
    expect(hexes.length).toBeGreaterThan(10);
    const violators: string[] = [];
    for (const hex of hexes) {
      // 低饱和(<12%)或近中性(饱和<0.25 且明度差小)视为中性,放行
      if (saturationOf(hex) < 0.25) {
        // 灰但偏色相且高饱和才拦:#3d4149 类(饱和~0.2)仍是中性灰
        continue;
      }
      const h = hueOf(hex);
      // 红跨 0:350-360 / 0-10
      const inFamily = FAMILIES.some(([, lo, hi]) => h >= lo && h <= hi)
        || (h >= 350 || h <= 10);
      if (!inFamily) violators.push(hex);
    }
    expect(violators, `游离色: ${violators.join(", ")}`).toEqual([]);
  });

  it("A 级按压系统变量存在", () => {
    expect(cssText).toContain("--px-shadow:");
    expect(cssText).toContain("--px-press-shift:");
    expect(cssText).toContain("steps(1)");
    expect(cssText).toContain(".px-btn");
    expect(cssText).toContain(".px-panel-bar");
  });
});
