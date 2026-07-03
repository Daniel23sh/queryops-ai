import type { NavItem } from "./navigation";

export function AppNavigation({
  activeNavId,
  items,
  onNavigate
}: {
  activeNavId: string;
  items: NavItem[];
  onNavigate: (navId: string) => void;
}) {
  return (
    <nav className="workspace-nav" aria-label="Workspace navigation">
      {items.map((item) => {
        const isActive = item.id === activeNavId;

        return (
          <button
            key={item.id}
            type="button"
            className="workspace-nav__item"
            aria-current={isActive ? "page" : undefined}
            data-active={isActive ? "true" : "false"}
            onClick={() => onNavigate(item.id)}
          >
            <span
              className="workspace-nav__icon"
              data-icon={item.icon}
              aria-hidden="true"
            />
            <span className="workspace-nav__label">{item.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
