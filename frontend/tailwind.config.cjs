/** @type {import("tailwindcss").Config} */
module.exports = {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "var(--qops-color-background)",
          surface: "var(--qops-color-surface)",
          muted: "var(--qops-color-muted-surface)",
          border: "var(--qops-color-border)",
          text: "var(--qops-color-text)",
          subtle: "var(--qops-color-text-subtle)",
          faint: "var(--qops-color-text-faint)"
        },
        brand: {
          primary: "var(--qops-color-primary)",
          "primary-strong": "var(--qops-color-primary-strong)",
          accent: "var(--qops-color-accent)",
          "accent-strong": "var(--qops-color-accent-strong)"
        },
        state: {
          success: "var(--qops-color-success)",
          warning: "var(--qops-color-warning)",
          danger: "var(--qops-color-danger)"
        }
      },
      borderRadius: {
        control: "0.5rem",
        card: "0.5rem",
        panel: "0.75rem"
      },
      boxShadow: {
        card: "0 16px 36px rgb(15 23 42 / 0.1)",
        panel: "0 20px 48px rgb(15 23 42 / 0.12)",
        focus: "0 0 0 3px rgb(44 123 229 / 0.32)"
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "\"Segoe UI\"",
          "sans-serif"
        ],
        mono: [
          "\"SFMono-Regular\"",
          "Consolas",
          "\"Liberation Mono\"",
          "Menlo",
          "monospace"
        ]
      }
    }
  },
  plugins: []
};
