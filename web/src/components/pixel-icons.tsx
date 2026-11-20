/**
 * 8×8 像素图标系统 v2(web-pixel-flavor 反馈轮)。
 *
 * v1 问题:多数图标都是方块,标签间无法区分。v2 每枚独立造型:
 * 会话=气泡 · 记忆=芯片 · context=硬币叠 · 运行历史=时钟 ·
 * 事件时间线=节点线 · 热=火焰 · 冷=雪花 · 主题=日/月。
 */

interface PixelIconProps {
  size?: number;
  color?: string;
  title?: string;
}

function PixelSvg({ size = 16, color, title, children }: PixelIconProps & { children: React.ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 8 8"
      shapeRendering="crispEdges"
      fill={color ?? "currentColor"}
      role="img"
      aria-label={title}
      style={{ display: "inline-block", verticalAlign: "-2px" }}
    >
      {title ? <title>{title}</title> : null}
      {children}
    </svg>
  );
}

/** 会话:对话气泡(带尾巴) */
export function IconSession(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "会话"}>
      <rect x="1" y="1" width="6" height="4" />
      <rect x="2" y="5" width="2" height="1" />
      <rect x="1" y="6" width="1" height="1" />
    </PixelSvg>
  );
}

/** 记忆:芯片(中心块 + 四边引脚) */
export function IconMemory(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "记忆"}>
      <rect x="2" y="2" width="4" height="4" />
      <rect x="3" y="3" width="2" height="2" fill="var(--bg, #0e1012)" />
      <rect x="0" y="3" width="1" height="1" />
      <rect x="7" y="3" width="1" height="1" />
      <rect x="3" y="0" width="1" height="1" />
      <rect x="3" y="7" width="1" height="1" />
    </PixelSvg>
  );
}

/** context:一叠硬币(三枚椭圆侧视) */
export function IconCoinStack(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "context"}>
      <rect x="2" y="0" width="5" height="1" />
      <rect x="1" y="1" width="6" height="1" />
      <rect x="2" y="2" width="5" height="1" />
      <rect x="1" y="3" width="6" height="1" />
      <rect x="2" y="4" width="5" height="1" />
      <rect x="1" y="5" width="6" height="1" />
      <rect x="2" y="6" width="5" height="1" />
      <rect x="1" y="7" width="6" height="1" />
    </PixelSvg>
  );
}

/** 运行历史:时钟(圆盘 + 指针) */
export function IconClock(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "运行历史"}>
      <rect x="2" y="0" width="4" height="1" />
      <rect x="1" y="1" width="1" height="1" />
      <rect x="6" y="1" width="1" height="1" />
      <rect x="0" y="2" width="1" height="4" />
      <rect x="7" y="2" width="1" height="4" />
      <rect x="1" y="6" width="1" height="1" />
      <rect x="6" y="6" width="1" height="1" />
      <rect x="2" y="7" width="4" height="1" />
      <rect x="4" y="2" width="1" height="2" />
      <rect x="4" y="4" width="1" height="1" />
      <rect x="5" y="5" width="1" height="1" />
    </PixelSvg>
  );
}

/** 事件时间线:横轴 + 两个节点 */
export function IconTimeline(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "时间线"}>
      <rect x="0" y="3" width="8" height="2" />
      <rect x="1" y="1" width="3" height="6" fill="var(--bg, #0e1012)" />
      <rect x="2" y="1" width="3" height="6" fill="currentColor" />
      <rect x="5" y="1" width="3" height="6" fill="var(--bg, #0e1012)" />
      <rect x="6" y="1" width="2" height="6" fill="currentColor" />
      <rect x="0" y="3" width="1" height="2" fill="var(--bg, #0e1012)" />
      <rect x="7" y="3" width="1" height="2" fill="var(--bg, #0e1012)" />
    </PixelSvg>
  );
}

/** 热:火焰 */
export function IconHot(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "热"}>
      <rect x="4" y="0" width="1" height="1" />
      <rect x="3" y="1" width="2" height="1" />
      <rect x="3" y="2" width="3" height="1" />
      <rect x="2" y="3" width="4" height="1" />
      <rect x="2" y="4" width="4" height="1" />
      <rect x="3" y="5" width="3" height="1" />
      <rect x="3" y="6" width="2" height="1" />
      <rect x="3" y="7" width="1" height="1" />
    </PixelSvg>
  );
}

/** 冷:雪花(十字 + 斜粒) */
export function IconCold(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "冷"}>
      <rect x="3" y="0" width="2" height="8" />
      <rect x="0" y="3" width="8" height="2" />
      <rect x="1" y="1" width="1" height="1" />
      <rect x="2" y="2" width="1" height="1" />
      <rect x="5" y="5" width="1" height="1" />
      <rect x="6" y="6" width="1" height="1" />
      <rect x="6" y="1" width="1" height="1" />
      <rect x="5" y="2" width="1" height="1" />
      <rect x="2" y="5" width="1" height="1" />
      <rect x="1" y="6" width="1" height="1" />
    </PixelSvg>
  );
}

/** 删除:叉(v1 保留,辨警度已够) */
export function IconDelete(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "删除"}>
      <rect x="1" y="1" width="1" height="1" />
      <rect x="2" y="2" width="1" height="1" />
      <rect x="3" y="3" width="2" height="2" />
      <rect x="5" y="5" width="1" height="1" />
      <rect x="6" y="6" width="1" height="1" />
      <rect x="6" y="1" width="1" height="1" />
      <rect x="5" y="2" width="1" height="1" />
      <rect x="1" y="6" width="1" height="1" />
      <rect x="2" y="5" width="1" height="1" />
    </PixelSvg>
  );
}

/** 清除:方块递减(v1 保留) */
export function IconClear(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "清除"}>
      <rect x="1" y="1" width="6" height="1" />
      <rect x="2" y="3" width="4" height="1" />
      <rect x="3" y="5" width="2" height="1" />
    </PixelSvg>
  );
}

/** 运行:播放三角(v1 保留) */
export function IconRun(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "运行"}>
      <rect x="2" y="1" width="1" height="6" />
      <rect x="3" y="2" width="1" height="4" />
      <rect x="4" y="3" width="1" height="2" />
    </PixelSvg>
  );
}

/** CRT:扫描线屏幕(v1 保留) */
export function IconCrt(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "CRT"}>
      <rect x="0" y="1" width="8" height="5" fill="none" stroke="currentColor" strokeWidth="1" />
      <rect x="1" y="2" width="6" height="1" />
      <rect x="1" y="4" width="6" height="1" />
      <rect x="3" y="6" width="2" height="1" />
    </PixelSvg>
  );
}

/** 主题:太阳(切浅色) */
export function IconSun(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "浅色"}>
      <rect x="2" y="2" width="4" height="4" />
      <rect x="3" y="0" width="2" height="1" />
      <rect x="3" y="7" width="2" height="1" />
      <rect x="0" y="3" width="1" height="2" />
      <rect x="7" y="3" width="1" height="2" />
      <rect x="0" y="0" width="1" height="1" />
      <rect x="7" y="0" width="1" height="1" />
      <rect x="0" y="7" width="1" height="1" />
      <rect x="7" y="7" width="1" height="1" />
    </PixelSvg>
  );
}

/** 主题:月亮(切深色) */
export function IconMoon(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "深色"}>
      <rect x="3" y="0" width="3" height="1" />
      <rect x="2" y="1" width="2" height="1" />
      <rect x="5" y="1" width="2" height="1" />
      <rect x="1" y="2" width="2" height="1" />
      <rect x="6" y="2" width="1" height="4" />
      <rect x="0" y="3" width="1" height="3" />
      <rect x="2" y="3" width="1" height="3" />
      <rect x="3" y="2" width="1" height="1" fill="var(--bg, #0e1012)" />
      <rect x="2" y="6" width="2" height="1" />
      <rect x="5" y="6" width="2" height="1" />
      <rect x="3" y="7" width="3" height="1" />
    </PixelSvg>
  );
}
