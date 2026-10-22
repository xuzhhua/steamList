/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: "#0b0f14",
        panel: "#111820",
        "panel-2": "#0e141b",
        "panel-3": "#16202b",
        line: "#1e2a36",
        "line-strong": "#2a3a4a",
        ink: "#e6edf3",
        muted: "#8b9bb0",
        dim: "#5f7186",
        accent: "#66c0f4",
        "accent-strong": "#1a9fff",
        teal: "#2dd4bf",
        good: "#4ade80",
        warn: "#fbbf24",
        bad: "#f87171",
      },
      fontFamily: {
        sans: [
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "PingFang SC",
          "Hiragino Sans GB",
          "Microsoft YaHei",
          "Noto Sans SC",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "Cascadia Code",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.03) inset, 0 8px 24px -16px rgba(0,0,0,0.8)",
        glow: "0 0 0 1px rgba(102,192,244,0.35), 0 0 24px -6px rgba(26,159,255,0.35)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in": {
          from: { opacity: "0", transform: "translateX(12px)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-400px 0" },
          "100%": { backgroundPosition: "400px 0" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out both",
        "slide-in": "slide-in 180ms ease-out both",
        shimmer: "shimmer 1.4s linear infinite",
      },
    },
  },
  plugins: [],
};
