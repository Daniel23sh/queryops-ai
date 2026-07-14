import type { ReactNode } from "react";

import { AppHeader } from "./AppHeader";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell app-shell--public">
      <AppHeader />
      {children}
    </div>
  );
}
