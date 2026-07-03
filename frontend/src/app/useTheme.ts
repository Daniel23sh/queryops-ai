import { createContext, useContext } from "react";

export type ThemeMode = "light" | "dark";

export type ThemeContextValue = {
  theme: ThemeMode;
  toggleTheme: () => void;
};

export const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useTheme(): ThemeContextValue {
  const value = useContext(ThemeContext);

  if (!value) {
    throw new Error("useTheme must be used within ThemeProvider.");
  }

  return value;
}
