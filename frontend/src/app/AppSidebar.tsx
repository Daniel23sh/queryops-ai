import { AppNavigation } from "./AppNavigation";
import type { NavItem } from "./navigation";

export function AppSidebar({
  items
}: {
  items: NavItem[];
}) {
  return (
    <aside className="workspace-sidebar" aria-label="Workspace">
      <AppNavigation items={items} />
    </aside>
  );
}
