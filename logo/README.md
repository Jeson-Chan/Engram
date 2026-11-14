# ENGRAM Logo

The ENGRAM wordmark, drawn as animated ASCII art with
[ascii.rest](https://ascii.rest). Two implementations of the same design:

- `standalone.html` - plain HTML, one script tag, zero build. Open it directly.
- `index.html` + `src/main.ts` - the TypeScript implementation
  (`npm install && npm run dev`), driving `banner()` + `mount()` from the
  `ascii.rest` npm package, with interactive variant controls.

## Design

An *engram* is the physical trace a memory leaves in the brain. The wordmark
leans into that: letters as memory cells, and a glint that sweeps across them
every few seconds - a memory being recalled.

Three curated variants (all uppercase ENGRAM):

| variant | font | shadow | color | effect | why |
|---------|------|--------|-------|--------|-----|
| **memory** (primary) | `tall` | `none` | `#7c6ff0` -> `#45c4b8` fade | glint, 0.8x | 7-row dot-matrix strokes read as memory cells; no shadow keeps the matrix clean; the glint is the recall |
| **banner** | `block` | `rounded` | `#7c6ff0` | glint | the classic ascii.rest banner look - solid block letters, soft drop shadow |
| **typewriter** | `slim` | `none` | `#45c4b8` | type, 1.6x | the memory being *written* - letter by letter |

The violet -> teal pair mirrors the README badge palette, so the wordmark and
the repo front page read as one system.

## Options reference

The design rides these `banner()` / `<ascii-banner>` options (full table in
the [ascii.rest banner docs](https://ascii.rest/docs/banners/)):

- `font`: block / slim / tall / bold / round / wide / mixed / italic
- `shadow`: double / single / heavy / rounded / ascii / none
- `color`: one `#rrggbb` or a list for a fade
- `shadowColor`, `effect` (glint / type / still), `speed`, `pixel`, `gap`, `pad`

## Run

```bash
npm install
npm run dev        # TypeScript version at http://localhost:5173
npm run build      # typecheck + production bundle
```

Or just open `standalone.html` in a browser - nothing to install.
