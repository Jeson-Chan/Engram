/**
 * 16×16 像素图标系统 v3(web-pixel-flavor 反馈轮 3)。
 *
 * v2 问题:8×8 在 16px 展示时是 2px 粗块,不够精美。v3 全部重绘为
 * 16×16 网格(1px 细节),每枚独立造型:
 * 会话=气泡 · 记忆=芯片 · context=硬币叠 · 历史=时钟 ·
 * 时间线=节点轴 · 热=火焰 · 冷=雪花 · 主题=日/月。
 *
 * v4(web-pixel-flavor-a):记忆类型三徽章(episodic 日记本/
 * semantic 字典/procedural 齿轮)+ 两帧 PixelSpinner(steps 切换)。
 */

interface PixelIconProps {
  size?: number;
  color?: string;
  title?: string;
}

function PixelSvg({ size = 16, color, title, rects }: PixelIconProps & { rects: number[] }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      shapeRendering="crispEdges"
      fill={color ?? "currentColor"}
      role="img"
      aria-label={title}
      style={{ display: "inline-block", verticalAlign: "-2px" }}
    >
      {title ? <title>{title}</title> : null}
      {Array.from({ length: rects.length / 4 }, (_, i) => (
        <rect key={i} x={rects[i * 4]} y={rects[i * 4 + 1]} width={rects[i * 4 + 2]} height={rects[i * 4 + 3]} />
      ))}
    </svg>
  );
}

const R = (...nums: number[]) => nums;

/** 会话:空心气泡(双线描边 + 尾巴) */
export function IconSession(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "会话"} rects={R(
      2, 2, 12, 2, 2, 10, 12, 2, 2, 4, 2, 6, 12, 4, 2, 6, 4, 12, 2, 1, 4, 13, 1, 1,
    )} />
  );
}

/** 记忆:芯片(外框 + 内芯 + 八只引脚) */
export function IconMemory(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "记忆"} rects={R(
      4, 4, 8, 2, 4, 10, 8, 2, 4, 6, 2, 4, 10, 6, 2, 4,
      7, 7, 2, 2,
      1, 6, 3, 1, 1, 9, 3, 1, 12, 6, 3, 1, 12, 9, 3, 1,
      6, 1, 1, 3, 9, 1, 1, 3, 6, 12, 1, 3, 9, 12, 1, 3,
    )} />
  );
}

/** context:一叠硬币(三枚椭圆侧视) */
export function IconCoinStack(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "context"} rects={R(
      3, 1, 10, 1, 2, 2, 12, 2,
      3, 5, 10, 1, 2, 6, 12, 2,
      3, 9, 10, 1, 2, 10, 12, 2,
      3, 13, 10, 1, 2, 14, 12, 1,
    )} />
  );
}

/** 运行历史:时钟(圆盘描边 + 时分针) */
export function IconClock(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "运行历史"} rects={R(
      5, 1, 6, 1, 3, 2, 2, 1, 11, 2, 2, 1, 2, 3, 1, 2, 13, 3, 1, 2,
      1, 5, 1, 6, 14, 5, 1, 6, 2, 11, 1, 2, 13, 11, 1, 2,
      3, 13, 2, 1, 11, 13, 2, 1, 5, 14, 6, 1,
      7, 4, 2, 4, 8, 8, 4, 2,
    )} />
  );
}

/** 事件时间线:轴 + 双节点 */
export function IconTimeline(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "时间线"} rects={R(
      0, 7, 16, 2, 2, 5, 4, 6, 10, 5, 4, 6,
    )} />
  );
}

/** 热:火焰(左右舔焰舞) */
export function IconHot(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "热"} rects={R(
      7, 0, 2, 1, 6, 1, 2, 1, 9, 1, 1, 1,
      5, 2, 2, 1, 8, 2, 2, 1,
      5, 3, 2, 1, 8, 3, 2, 1,
      4, 4, 2, 1, 7, 4, 3, 1,
      4, 5, 2, 1, 9, 5, 2, 1,
      3, 6, 3, 1, 9, 6, 2, 1,
      3, 7, 10, 1, 2, 8, 12, 1,
      2, 9, 12, 1, 2, 10, 12, 1,
      3, 11, 10, 1, 3, 12, 9, 1,
      4, 13, 8, 1, 5, 14, 6, 1, 6, 15, 4, 1,
    )} />
  );
}

/** 冷:雪花(十字 + 斜粒) */
export function IconCold(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "冷"} rects={R(
      7, 0, 2, 16, 0, 7, 16, 2,
      2, 2, 1, 1, 3, 3, 1, 1, 4, 4, 1, 1, 5, 5, 1, 1,
      10, 10, 1, 1, 11, 11, 1, 1, 12, 12, 1, 1, 13, 13, 1, 1,
      13, 2, 1, 1, 12, 3, 1, 1, 11, 4, 1, 1, 10, 5, 1, 1,
      5, 10, 1, 1, 4, 11, 1, 1, 3, 12, 1, 1, 2, 13, 1, 1,
    )} />
  );
}

/** 删除:厚叉 */
export function IconDelete(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "删除"} rects={R(
      2, 2, 3, 3, 11, 2, 3, 3, 2, 11, 3, 3, 11, 11, 3, 3,
      5, 5, 2, 2, 9, 5, 2, 2, 5, 9, 2, 2, 9, 9, 2, 2,
      7, 7, 2, 2,
    )} />
  );
}

/** 清除:方块递减 */
export function IconClear(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "清除"} rects={R(
      2, 2, 12, 3, 4, 7, 8, 3, 6, 12, 4, 2,
    )} />
  );
}

/** 运行:播放三角 */
export function IconRun(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "运行"} rects={R(
      4, 2, 2, 12, 6, 3, 2, 10, 8, 4, 2, 8, 10, 5, 2, 6, 12, 6, 2, 4,
    )} />
  );
}

/** CRT:扫描线显示器 */
export function IconCrt(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "CRT"} rects={R(
      1, 2, 14, 2, 1, 10, 14, 2, 1, 4, 2, 6, 13, 4, 2, 6,
      3, 5, 10, 1, 3, 7, 10, 1, 3, 9, 10, 1,
      6, 12, 4, 2, 5, 14, 6, 1,
    )} />
  );
}

/** 主题:太阳(切浅色) */
export function IconSun(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "浅色"} rects={R(
      5, 5, 6, 6,
      6, 0, 4, 2, 6, 14, 4, 2, 0, 6, 2, 4, 14, 6, 2, 4,
      1, 1, 2, 2, 13, 1, 2, 2, 1, 13, 2, 2, 13, 13, 2, 2,
    )} />
  );
}

/** 主题:月亮(切深色;fill-rule 式月牙用背景色咬口) */
export function IconMoon(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "深色"} rects={R(
      6, 1, 5, 1, 4, 2, 3, 1, 9, 2, 4, 1,
      3, 3, 2, 1, 11, 3, 3, 1,
      2, 4, 2, 1, 12, 4, 2, 1,
      2, 5, 1, 5, 13, 5, 1, 4,
      2, 10, 2, 1, 12, 10, 2, 1,
      3, 11, 2, 1, 11, 11, 3, 1,
      4, 12, 3, 1, 9, 12, 4, 1,
      6, 13, 5, 1,
      4, 3, 2, 8,
    )} />
  );
}

/** 记忆类型:episodic(日记本:双竖环 + 页) */
export function IconEpisodic(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "episodic"} rects={R(
      2, 1, 2, 14, 12, 1, 2, 14,
      4, 3, 8, 1, 4, 5, 8, 1, 4, 7, 8, 1, 4, 9, 8, 1, 4, 11, 8, 1,
      5, 13, 6, 1,
    )} />
  );
}

/** 记忆类型:semantic(字典:厚书 + 书签) */
export function IconSemantic(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "semantic"} rects={R(
      2, 2, 12, 2, 2, 12, 12, 2,
      4, 5, 8, 1, 4, 7, 5, 1, 4, 9, 8, 1,
      10, 4, 2, 5,
      4, 14, 12, 1,
    )} />
  );
}

/** 记忆类型:procedural(齿轮:方块齿 + 芯) */
export function IconProcedural(props: PixelIconProps) {
  return (
    <PixelSvg {...props} title={props.title ?? "procedural"} rects={R(
      6, 1, 4, 2, 2, 4, 3, 1, 11, 4, 3, 1, 2, 11, 3, 1, 11, 11, 3, 1,
      4, 5, 8, 6,
      6, 7, 4, 2,
    )} />
  );
}

/** 执行态:两帧方块 spinner(步进交替,CSS 类切 frame) */
export function PixelSpinner({ size = 16, color }: { size?: number; color?: string }) {
  const frame = (x: number, y: number, w: number, h: number) => ({ x, y, width: w, height: h });
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      shapeRendering="crispEdges"
      fill={color ?? "currentColor"}
      className="px-spinner"
      aria-label="loading"
      style={{ display: "inline-block", verticalAlign: "-2px" }}
    >
      {/* 两帧:实心方块 / 四角方块,由 CSS steps 切换 visibility */}
      <g className="px-spin-a">
        <rect {...frame(4, 4, 8, 8)} />
      </g>
      <g className="px-spin-b">
        <rect {...frame(2, 2, 4, 4)} />
        <rect {...frame(10, 2, 4, 4)} />
        <rect {...frame(2, 10, 4, 4)} />
        <rect {...frame(10, 10, 4, 4)} />
      </g>
    </svg>
  );
}
