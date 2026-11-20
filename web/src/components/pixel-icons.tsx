/**
 * 8×8 像素图标系统(web-pixel-flavor)——手绘 rect 网格,零外部依赖。
 *
 * 语义:会话/记忆用导航位,热/冷用于记忆层标记,删除/清除用于操作,运行/CRT 用于状态。
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

/** 会话:对话气泡双格 */
export function IconSession(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "会话"}>
      <rect x="0" y="1" width="7" height="4" />
      <rect x="1" y="5" width="2" height="1" />
      <rect x="2" y="6" width="2" height="1" />
    </PixelSvg>
  );
}

/** 记忆:点阵细胞(4 格子块 + 缺角 = 记忆痕迹) */
export function IconMemory(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "记忆"}>
      <rect x="1" y="1" width="2" height="2" />
      <rect x="4" y="1" width="2" height="2" />
      <rect x="1" y="4" width="2" height="2" />
      <rect x="4" y="4" width="2" height="2" />
      <rect x="6" y="6" width="1" height="1" />
    </PixelSvg>
  );
}

/** 热:实心方块(满格 = 热) */
export function IconHot(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "热"}>
      <rect x="1" y="1" width="6" height="6" />
    </PixelSvg>
  );
}

/** 冷:空心方块(空格 = 冷) */
export function IconCold(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "冷"}>
      <rect x="1" y="1" width="6" height="6" fill="none" stroke="currentColor" strokeWidth="1" />
    </PixelSvg>
  );
}

/** 删除:叉 */
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

/** 清除:方块递减(逐格消失) */
export function IconClear(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "清除"}>
      <rect x="1" y="1" width="6" height="1" />
      <rect x="2" y="3" width="4" height="1" />
      <rect x="3" y="5" width="2" height="1" />
    </PixelSvg>
  );
}

/** 运行:播放三角(像素阶梯) */
export function IconRun(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "运行"}>
      <rect x="2" y="1" width="1" height="6" />
      <rect x="3" y="2" width="1" height="4" />
      <rect x="4" y="3" width="1" height="2" />
    </PixelSvg>
  );
}

/** CRT:扫描线屏幕 */
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
