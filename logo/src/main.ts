/**
 * ENGRAM wordmark - the TypeScript implementation.
 *
 * banner() from ascii.rest/banner turns "ENGRAM" into an animated ASCII-art
 * piece; mount() from ascii.rest plays it into a DOM element. All three
 * variants from the design doc (logo/README.md) are wired to buttons.
 */
import { mount } from "ascii.rest";
import { banner } from "ascii.rest/banner";

type BannerOptions = Parameters<typeof banner>[1];

interface Variant {
  readonly id: string;
  readonly label: string;
  readonly options: BannerOptions;
}

/**
 * The palette mirrors the README badge system: violet #7c6ff0 to teal #45c4b8.
 * The glint effect is the design's core idea - a recall sweep across the
 * letter cells, one memory flashing back.
 */
const VARIANTS: readonly Variant[] = [
  {
    id: "memory",
    label: "memory",
    options: {
      font: "tall",
      shadow: "none",
      color: ["#7c6ff0", "#45c4b8"],
      effect: "glint",
      speed: 0.8,
    },
  },
  {
    id: "banner",
    label: "banner",
    options: {
      font: "block",
      shadow: "rounded",
      color: "#7c6ff0",
      shadowColor: "#30363d",
    },
  },
  {
    id: "typewriter",
    label: "typewriter",
    options: {
      font: "slim",
      shadow: "none",
      color: "#45c4b8",
      effect: "type",
      speed: 1.6,
    },
  },
] as const;

function render(variant: Variant, stage: HTMLElement): void {
  stage.replaceChildren();

  // A <pre> keeps the rows tight; ascii.rest adds no CSS of its own.
  const pre = document.createElement("pre");
  pre.style.margin = "0";
  pre.style.lineHeight = "1.2";
  stage.append(pre);

  // banner() is cheap but stateful: create it fresh per switch so the
  // motion (glint sweep / typing) restarts from the top.
  const piece = banner("ENGRAM", variant.options);
  const stop = mount(pre, piece);
  stage.dataset.activeVariant = variant.id;

  // Wire the stopper so a re-render of the same node doesn't leak frames.
  const previous = stopFunctions.get(stage);
  if (previous) previous();
  stopFunctions.set(stage, stop);
}

const stopFunctions = new WeakMap<HTMLElement, () => void>();

function main(): void {
  const stage = document.getElementById("stage");
  const nav = document.getElementById("variants");
  if (!stage || !nav) return;

  for (const variant of VARIANTS) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = variant.label;
    button.addEventListener("click", () => {
      for (const b of nav.querySelectorAll("button")) {
        b.setAttribute("aria-current", b === button ? "true" : "false");
      }
      render(variant, stage);
    });
    nav.append(button);
  }

  // Primary variant on load: the memory wordmark.
  const [primary] = VARIANTS;
  const primaryButton = nav.querySelector("button");
  primaryButton?.setAttribute("aria-current", "true");
  if (primary) render(primary, stage);
}

main();
