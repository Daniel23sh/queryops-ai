import { AppNavigation } from "./AppNavigation";
import type { NavItem } from "./navigation";

export function AppSidebar({
  activeNavId,
  items,
  onNavigate
}: {
  activeNavId: string;
  items: NavItem[];
  onNavigate: (navId: string) => void;
}) {
  return (
    <aside className="workspace-sidebar" aria-label="Workspace">
      <AppNavigation
        activeNavId={activeNavId}
        items={items}
        onNavigate={onNavigate}
      />
    </aside>
  );
}
