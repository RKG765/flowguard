import type { Config } from "tailwindcss";

// Every color is a CSS variable from src/styles/tokens.css, so the light/dark themes and the reduced-transparency mode
// switch by changing variables only. Semantic names (ok/warn/danger/info/ml) are the only colors components may use.
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"),
        rail: v("rail"),
        rail: v("rail"),
        "surface-2": v("surface-2"),
        line: v("line"),
        fg: v("fg"),
        muted: v("muted"),
        primary: v("primary"),
        "primary-strong": v("primary-strong"),
        "danger-strong": v("danger-strong"),
        ok: v("ok"),
        warn: v("warn"),
        danger: v("danger"),
        info: v("info"),
        ml: v("ml"),
      },
      fontFamily: {
        sans: ["Barlow", "system-ui", "sans-serif"],
        label: ['"Barlow Condensed"', "Barlow", "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      borderRadius: { glass: "4px", data: "3px" },
      boxShadow: {
        glass: "0 1px 0 0 rgb(0 0 0 / 0.25)",
      },
      transitionDuration: { fast: "150ms", base: "200ms", slow: "250ms" },
      keyframes: {
        pulseDot: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
      },
      animation: { "pulse-dot": "pulseDot 1.6s ease-in-out infinite" },
    },
  },
  plugins: [],
} satisfies Config;
