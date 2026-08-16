/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        dark: {
          bg: "#0A0E17",
          panel: "#121A29",
          elevated: "#182235",
          card: "#151F30",
          hover: "#1D2B40",
          border: "#1E2B40",
          borderLighter: "#2A3A54",
          text: "#E2E8F0",
          muted: "#8B9BB4",
          subtle: "#5A6E8C",
        },
        brand: {
          primary: "#6366F1",
          primaryHover: "#4F46E5",
          secondary: "#8B5CF6",
          cyan: "#06B6D4",
          blue: "#3B82F6",
          emerald: "#10B981",
          amber: "#F59E0B",
          rose: "#F43F5E",
        },
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Roboto", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
    },
  },
  plugins: [],
};
