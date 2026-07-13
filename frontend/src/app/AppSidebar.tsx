import { DatabaseZap, X } from "lucide-react";

import { AppNavigation } from "./AppNavigation";
import type { NavItem } from "./navigation";

export function AppSidebar({
  collapsed,
  drawerOpen,
  isMobile,
  items,
  onClose,
  onNavigate
}: {
  collapsed: boolean;
  drawerOpen: boolean;
  isMobile: boolean;
  items: NavItem[];
  onClose: () => void;
  onNavigate: () => void;
}) {
  return (
    <aside
      id="primary-navigation"
      className="workspace-sidebar"
      aria-label="Workspace"
      aria-modal={isMobile ? true : undefined}
      data-collapsed={!isMobile && collapsed ? "true" : "false"}
      data-drawer={isMobile ? "true" : "false"}
      data-open={drawerOpen ? "true" : "false"}
      hidden={isMobile && !drawerOpen}
      role={isMobile ? "dialog" : undefined}
    >
      <div className="workspace-sidebar__brand">
        <span className="workspace-sidebar__mark" aria-hidden="true">
          <DatabaseZap size={20} />
        </span>
        <span className="workspace-sidebar__brand-copy">
          <strong>QueryOps AI</strong>
          <span>Governed data</span>
        </span>
        {isMobile ? (
          <button
            type="button"
            className="icon-button workspace-sidebar__close"
            aria-label="Close navigation"
            onClick={onClose}
          >
            <X aria-hidden="true" size={21} />
          </button>
        ) : null}
      </div>

      <AppNavigation items={items} onNavigate={onNavigate} />
    </aside>
  );
}
