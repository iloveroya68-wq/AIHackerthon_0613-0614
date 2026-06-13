/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#040d1a",
          900: "#0a1628",
          800: "#0f2040",
          700: "#162a52",
          600: "#1e3a6e",
          500: "#264d8e",
        },
        cyan: {
          400: "#00d4ff",
          300: "#33ddff",
          200: "#66e8ff",
        },
        amber: {
          400: "#fbbf24",
        },
      },
      fontFamily: {
        sans: ["Inter", "Noto Sans KR", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(0, 212, 255, 0.3)",
        "glow-sm": "0 0 8px rgba(0, 212, 255, 0.25)",
      },
    },
  },
  plugins: [],
};
