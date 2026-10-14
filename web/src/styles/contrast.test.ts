import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { contrast, over, parseTriplet, type Rgb } from "@/lib/contrast";

/** Reads tokens.css itself, so the test fails if anyone changes a token to an unreadable color. */
// vitest runs from web/ (jsdom has no file:// import.meta.url)
const css = readFileSync(resolve(process.cwd(), "src/styles/tokens.css"), "utf8");

function block(selector: string): Record<string, string> {
  const start = css.indexOf(selector);
  const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
  const out: Record<string, string> = {};
  for (const m of body.matchAll(/--([\w-]+):\s*([^;]+);/g)) out[m[1]!] = m[2]!.replace(/\/\*.*?\*\//g, "").trim();
  return out;
}

const THEMES = { dark: block('[data-theme="dark"]'), light: block('[data-theme="light"]') };
const TEXT = ["fg", "muted", "primary", "ok", "warn", "danger", "info", "ml"];

describe.each(Object.entries(THEMES))("%s theme meets WCAG AA (4.5:1) for text", (_name, t) => {
  const bg = parseTriplet(t.bg!);
  const surfaces: Record<string, Rgb> = {
    bg,
    surface: parseTriplet(t.surface!),
    "surface-2": parseTriplet(t["surface-2"]!),
    glass: over([255, 255, 255], Number(t["glass-alpha"]), bg), // glass composited over the page background
  };
  for (const token of TEXT) {
    for (const [sname, s] of Object.entries(surfaces)) {
      it(`--${token} on ${sname}`, () => {
        expect(contrast(parseTriplet(t[token]!), s)).toBeGreaterThanOrEqual(4.5);
      });
    }
  }
  // Regression (axe, Phase 3): white button text and badge text on its own 10 % tint were below AA.
  it.each(["primary-strong", "danger-strong"])("white text on filled %s buttons", (tok) => {
    expect(contrast([255, 255, 255], parseTriplet(t[tok]!))).toBeGreaterThanOrEqual(4.5);
  });
  it.each(["ok", "warn", "danger", "info", "ml"])("%s badge text on its 10%% tint over glass", (tok) => {
    const c = parseTriplet(t[tok]!);
    const tint = over(c, 0.1, surfaces.glass!);
    expect(contrast(c, tint)).toBeGreaterThanOrEqual(4.5);
  });
});

test("contrast math matches known WCAG values", () => {
  expect(contrast([0, 0, 0], [255, 255, 255])).toBeCloseTo(21, 5);
  expect(contrast([118, 118, 118], [255, 255, 255])).toBeCloseTo(4.54, 1);
});
