import type { ThemeMode } from "../../app/useTheme";

export function ThemeToggle({
  theme,
  onToggle
}: {
  theme: ThemeMode;
  onToggle: () => void;
}) {
  const isDark = theme === "dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={isDark}
      onClick={onToggle}
    >
      <span className="theme-toggle__track" aria-hidden="true">
        <span className="theme-toggle__thumb" />
      </span>
      <span className="theme-toggle__label">{isDark ? "Dark" : "Light"}</span>
    </button>
  );
}
