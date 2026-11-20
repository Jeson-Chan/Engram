/**
 * 像素图标系统 v5 —— 基于 @hackernoon/pixel-icon-library(2300+ 图标,
 * 24px 网格,单色平涂),替换 v4 手绘 16 网格。
 *
 * 接入方式:SVG 源拷贝到 src/assets/icons/(无 fill,默认黑)——
 * `?raw` 内联 + 统一注入 fill=currentColor,由父级 color 挂语义色。
 * 渲染尺寸 16/20px 时 24 网格无锯齿(浏览器整格缩放,crispEdges 保持)。
 */

import { useMemo } from "react";

// vite ?raw imports:svg 字符串(24×24 viewBox,无 fill)
import rawSession from "../assets/icons/session.svg?raw";
import rawMemory from "../assets/icons/memory.svg?raw";
import rawEpisodic from "../assets/icons/episodic.svg?raw";
import rawSemantic from "../assets/icons/semantic.svg?raw";
import rawProcedural from "../assets/icons/procedural.svg?raw";
import rawHot from "../assets/icons/hot.svg?raw";
import rawCold from "../assets/icons/cold.svg?raw";
import rawDelete from "../assets/icons/delete.svg?raw";
import rawClear from "../assets/icons/clear.svg?raw";
import rawRun from "../assets/icons/run.svg?raw";
import rawHistory from "../assets/icons/history.svg?raw";
import rawSun from "../assets/icons/sun.svg?raw";
import rawMoon from "../assets/icons/moon.svg?raw";
import rawBudget from "../assets/icons/budget.svg?raw";
import rawTimeline from "../assets/icons/timeline.svg?raw";

interface IconProps {
  size?: number;
  color?: string;
  title?: string;
}

/** 库 SVG → 染色 inline 组件(fill=currentColor + crispEdges + role)。 */
function PixelIcon({ raw, size = 20, color, title, label }: IconProps & { raw: string; label: string }) {
  const html = useMemo(() => {
    // 注入 fill 与 shape-rendering(库 SVG 无 fill 属性,顶层注入即可全局生效)
    const styled = raw
      .replace("<svg ", '<svg fill="currentColor" shape-rendering="crispEdges" ')
      .replace(/<!--.*?-->/g, "");
    return styled;
  }, [raw]);
  return (
    <span
      className="pixel-icon"
      title={title}
      style={{
        display: "inline-flex",
        width: size,
        height: size,
        color: color ?? "inherit",
        verticalAlign: "-3px",
        lineHeight: 0,
      }}
      role="img"
      aria-label={label}
      data-testid={`icon-${label}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

/** 会话:像素气泡(库:message-solid) */
export function IconSession(props: IconProps) {
  return <PixelIcon {...props} raw={rawSession} label="session" />;
}
/** 记忆:能量/trace(库:bolt-solid) */
export function IconMemory(props: IconProps) {
  return <PixelIcon {...props} raw={rawMemory} label="memory" />;
}
/** episodic:日记本(库:notebook-solid) */
export function IconEpisodic(props: IconProps) {
  return <PixelIcon {...props} raw={rawEpisodic} label="episodic" />;
}
/** semantic:字典(库:book-solid) */
export function IconSemantic(props: IconProps) {
  return <PixelIcon {...props} raw={rawSemantic} label="semantic" />;
}
/** procedural:齿轮(库:cog-solid) */
export function IconProcedural(props: IconProps) {
  return <PixelIcon {...props} raw={rawProcedural} label="procedural" />;
}
/** 热层:火焰(库:fire-solid) */
export function IconHot(props: IconProps) {
  return <PixelIcon {...props} raw={rawHot} label="hot" />;
}
/** 冷层:归档(库:archive-solid) */
export function IconCold(props: IconProps) {
  return <PixelIcon {...props} raw={rawCold} label="cold" />;
}
/** 删除(库:trash-solid) */
export function IconDelete(props: IconProps) {
  return <PixelIcon {...props} raw={rawDelete} label="delete" />;
}
/** 清除(库:broom-solid) */
export function IconClear(props: IconProps) {
  return <PixelIcon {...props} raw={rawClear} label="clear" />;
}
/** 运行:播放三角(库:play-solid) */
export function IconRun(props: IconProps) {
  return <PixelIcon {...props} raw={rawRun} label="run" />;
}
/** 运行历史:时钟(库:clock-solid) */
export function IconClock(props: IconProps) {
  return <PixelIcon {...props} raw={rawHistory} label="history" />;
}
/** 主题:太阳(切浅色;库:sun-solid) */
export function IconSun(props: IconProps) {
  return <PixelIcon {...props} raw={rawSun} label="sun" />;
}
/** 主题:月亮(切深色;库:moon-solid) */
export function IconMoon(props: IconProps) {
  return <PixelIcon {...props} raw={rawMoon} label="moon" />;
}
/** 事件时间线(库:analytics-solid) */
export function IconTimeline(props: IconProps) {
  return <PixelIcon {...props} raw={rawTimeline} label="timeline" />;
}
/** 上下文预算:硬币(库:coin-solid) */
export function IconCoinStack(props: IconProps) {
  return <PixelIcon {...props} raw={rawBudget} label="budget" />;
}

/** 执行态两帧 spinner(v5:沿用像素方块二帧,steps 切换)。 */
export function PixelSpinner({ size = 16, color }: { size?: number; color?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      shapeRendering="crispEdges"
      fill={color ?? "currentColor"}
      className="px-spinner"
      aria-label="loading"
      style={{ display: "inline-block", verticalAlign: "-3px" }}
    >
      <g className="px-spin-a"><rect x={4} y={4} width={8} height={8} /></g>
      <g className="px-spin-b">
        <rect x={2} y={2} width={4} height={4} /><rect x={10} y={2} width={4} height={4} />
        <rect x={2} y={10} width={4} height={4} /><rect x={10} y={10} width={4} height={4} />
      </g>
    </svg>
  );
}
