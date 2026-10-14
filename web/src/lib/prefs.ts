import { create } from "zustand";

/** Per-viewer display preferences (theme, reduced motion, reduced transparency). Stored in localStorage only as a
 *  convenience: every access is guarded so private windows or blocked storage just fall back to defaults. */
export type Theme = "dark" | "light";

const read = (k: string): string | null => {
  try {
    return window.localStorage.getItem(k);
  } catch {
    return null;
  }
};
const write = (k: string, v: string): void => {
  try {
    window.localStorage.setItem(k, v);
  } catch {
    /* storage blocked */
  }
};

const root = (): HTMLElement => document.documentElement;

interface Prefs {
  theme: Theme;
  reducedMotion: boolean;
  reducedTransparency: boolean;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;
  setReducedMotion: (v: boolean) => void;
  setReducedTransparency: (v: boolean) => void;
}

export const usePrefs = create<Prefs>((set, get) => ({
  theme: (root().getAttribute("data-theme") as Theme) || "dark",
  reducedMotion: read("fg-motion") === "reduced",
  reducedTransparency: read("fg-transparency") === "reduced",
  setTheme(t) {
    root().setAttribute("data-theme", t);
    write("fg-theme", t);
    set({ theme: t });
  },
  toggleTheme() {
    get().setTheme(get().theme === "dark" ? "light" : "dark");
  },
  setReducedMotion(v) {
    if (v) root().setAttribute("data-motion", "reduced");
    else root().removeAttribute("data-motion");
    write("fg-motion", v ? "reduced" : "full");
    set({ reducedMotion: v });
  },
  setReducedTransparency(v) {
    if (v) root().setAttribute("data-transparency", "reduced");
    else root().removeAttribute("data-transparency");
    write("fg-transparency", v ? "reduced" : "full");
    set({ reducedTransparency: v });
  },
}));

/** Apply stored motion/transparency choices at startup (the theme is applied by index.html before first paint). */
export function applyStoredPrefs(): void {
  const p = usePrefs.getState();
  p.setReducedMotion(p.reducedMotion);
  p.setReducedTransparency(p.reducedTransparency);
}
