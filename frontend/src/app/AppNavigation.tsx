import { NavLink, useLocation } from "react-router-dom";

import type { NavItem } from "./navigation";

export function AppNavigation({
  items,
  onLinkSelect
}: {
  items: NavItem[];
  onLinkSelect: () => void;
}) {
  const workspaceItems = items.filter((item) => item.section === "workspace");
  const adminItems = items.filter((item) => item.section === "admin");

  return (
    <nav className="workspace-nav" aria-label="Workspace navigation">
      <NavigationGroup items={workspaceItems} onLinkSelect={onLinkSelect} />
      {adminItems.length > 0 ? (
        <NavigationGroup items={adminItems} label="Admin" onLinkSelect={onLinkSelect} />
      ) : null}
    </nav>
  );
}

function NavigationGroup({
  items,
  label,
  onLinkSelect
}: {
  items: NavItem[];
  label?: string;
  onLinkSelect: () => void;
}) {
  const location = useLocation();
  return (
    <div className="workspace-nav__group">
      {label ? <p className="workspace-nav__section-label">{label}</p> : null}
      {items.map((item) => {
        const Icon = item.icon;
        const isDashboardDetail =
          item.path === "/" && location.pathname.startsWith("/dashboards/");

        return (
          <NavLink
            key={item.id}
            className={({ isActive }) =>
              `workspace-nav__item${isActive || isDashboardDetail ? " workspace-nav__item--active" : ""}`
            }
            aria-current={isDashboardDetail ? "page" : undefined}
            to={item.path}
            end={item.path === "/"}
            onClick={onLinkSelect}
          >
            <Icon className="workspace-nav__icon" aria-hidden="true" size={19} />
            <span className="workspace-nav__label">{item.label}</span>
          </NavLink>
        );
      })}
    </div>
  );
}
