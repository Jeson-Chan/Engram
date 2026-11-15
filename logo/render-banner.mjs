// Render the ENGRAM wordmark (banner-classic variant) to text frames.
//   node render-banner.mjs            # static banner -> banner-classic.txt
//   node render-banner.mjs --gif      # 90 glint frames -> frames/fNNN.txt
// Compose the GIF afterwards with compose-gif.py.
import { banner } from "ascii.rest/banner";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";

const options = {
  font: "block",
  shadow: "rounded",
  color: "#7c6ff0",
  shadowColor: "#30363d",
};

const frame = banner("ENGRAM", { ...options, effect: "still" }).default();
if (process.argv.includes("--gif")) {
  const piece = banner("ENGRAM", { ...options, effect: "glint", speed: 1 });
  const at = piece.default();
  const N = 90, FPS = 25;
  rmSync("frames", { recursive: true, force: true });
  mkdirSync("frames", { recursive: true });
  for (let i = 0; i < N; i++) {
    writeFileSync(`frames/f${String(i).padStart(3, "0")}.txt`, at(i / FPS));
  }
  console.log(`rendered ${N} frames over ${N / FPS}s -> frames/`);
} else {
  writeFileSync("banner-classic.txt", frame(0));
  console.log(frame(0));
}
