import type { ReactNode } from "react";

import { AppHeader } from "./AppHeader";
import { ThemeProvider } from "./ThemeProvider";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <div className="app-shell">
        <AppHeader />
        {children}
      </div>
    </ThemeProvider>
  );
}
