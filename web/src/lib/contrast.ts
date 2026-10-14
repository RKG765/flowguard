/** WCAG 2.x contrast helpers for "R G B" token triplets. */
export type Rgb = [number, number, number];

export const parseTriplet = (s: string): Rgb => {
  const parts = s.trim().split(/\s+/).map(Number);
  if (parts.length !== 3 || parts.some((n) => Number.isNaN(n))) throw new Error(`bad color triplet: ${s}`);
  return parts as Rgb;
};

const channel = (c: number): number => {
  const v = c / 255;
  return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
};

export const luminance = ([r, g, b]: Rgb): number => 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);

export const contrast = (a: Rgb, b: Rgb): number => {
  const [l1, l2] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (l1 + 0.05) / (l2 + 0.05);
};

/** Composite a translucent foreground (alpha 0..1) over an opaque background. */
export const over = (fg: Rgb, alpha: number, bg: Rgb): Rgb =>
  [0, 1, 2].map((i) => Math.round(fg[i]! * alpha + bg[i]! * (1 - alpha))) as Rgb;
