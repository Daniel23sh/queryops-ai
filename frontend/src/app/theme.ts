import type { ThemeMode } from "./useTheme";

export const THEME_STORAGE_KEY = "queryops-theme";
export const DEFAULT_THEME: ThemeMode = "dark";

export function getInitialTheme(): ThemeMode {
  return getStoredTheme() ?? DEFAULT_THEME;
}

export function initializeTheme(): ThemeMode {
  const theme = getInitialTheme();
  applyTheme(theme, false);
  return theme;
}

export function applyTheme(theme: ThemeMode, persist = true) {
  if (typeof document !== "undefined") {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.dataset.theme = theme;
  }

  if (!persist || typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Theme persistence is optional; the active DOM theme remains authoritative.
  }
}

function getStoredTheme(): ThemeMode | null {
  if (typeof window === "undefined") {
    return null;
  }

  try {
    const storedTheme = window.localStorage.getItem(THEME_STORAGE_KEY);
    return storedTheme === "light" || storedTheme === "dark" ? storedTheme : null;
  } catch {
    return null;
  }
}
