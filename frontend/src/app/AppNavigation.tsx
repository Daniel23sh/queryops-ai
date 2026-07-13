import { NavLink } from "react-router-dom";

import type { NavItem } from "./navigation";

export function AppNavigation({ items }: { items: NavItem[] }) {
  const workspaceItems = items.filter((item) => item.section === "workspace");
  const adminItems = items.filter((item) => item.section === "admin");

  return (
    <nav className="workspace-nav" aria-label="Workspace navigation">
      <NavigationGroup items={workspaceItems} />
      {adminItems.length > 0 ? (
        <NavigationGroup items={adminItems} label="Admin" />
      ) : null}
    </nav>
  );
}

function NavigationGroup({ items, label }: { items: NavItem[]; label?: string }) {
  return (
    <div className="workspace-nav__group">
      {label ? <p className="workspace-nav__section-label">{label}</p> : null}
      {items.map((item) => {
        const Icon = item.icon;

        return (
          <NavLink
            key={item.id}
            className="workspace-nav__item"
            to={item.path}
            end={item.path === "/"}
          >
            <Icon className="workspace-nav__icon" aria-hidden="true" size={19} />
            <span className="workspace-nav__label">{item.label}</span>
          </NavLink>
        );
      })}
    </div>
  );
}
