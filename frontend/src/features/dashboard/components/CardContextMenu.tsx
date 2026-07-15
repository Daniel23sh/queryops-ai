import { Copy, Download, Eye, MoreHorizontal, Pencil, RefreshCw, ScanLine, Shapes, Trash2 } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type CardMenuAction =
  | "refresh"
  | "export"
  | "source"
  | "visualization"
  | "resize"
  | "rename"
  | "duplicate"
  | "remove";

type MenuItem = { action: CardMenuAction; label: string; destructive?: boolean; icon: React.ReactNode };

export function CardContextMenu({
  canExport,
  canRefresh,
  canViewSource,
  cardTitle,
  editMode,
  onSelect
}: {
  canExport: boolean;
  canRefresh: boolean;
  canViewSource: boolean;
  cardTitle: string;
  editMode: boolean;
  onSelect: (action: CardMenuAction) => void;
}) {
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();
  const items: MenuItem[] = [
    ...(canRefresh ? [{ action: "refresh" as const, label: "Refresh", icon: <RefreshCw aria-hidden="true" size={16} /> }] : []),
    ...(canExport ? [{ action: "export" as const, label: "Export CSV", icon: <Download aria-hidden="true" size={16} /> }] : []),
    ...(canViewSource ? [{ action: "source" as const, label: "View source", icon: <Eye aria-hidden="true" size={16} /> }] : []),
    ...(editMode ? [
      { action: "visualization" as const, label: "Change visualization", icon: <Shapes aria-hidden="true" size={16} /> },
      { action: "resize" as const, label: "Resize", icon: <ScanLine aria-hidden="true" size={16} /> },
      { action: "rename" as const, label: "Rename", icon: <Pencil aria-hidden="true" size={16} /> },
      { action: "duplicate" as const, label: "Duplicate", icon: <Copy aria-hidden="true" size={16} /> },
      { action: "remove" as const, label: "Remove", destructive: true, icon: <Trash2 aria-hidden="true" size={16} /> }
    ] : [])
  ];

  useEffect(() => {
    if (!menu) return;
    const first = menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]');
    first?.focus();
    function closeOnOutside(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node) && !triggerRef.current?.contains(event.target as Node)) close(true);
    }
    document.addEventListener("mousedown", closeOnOutside);
    return () => document.removeEventListener("mousedown", closeOnOutside);
  }, [menu]);

  function close(restore = true) {
    setMenu(null);
    if (restore) requestAnimationFrame(() => triggerRef.current?.focus());
  }

  function open(x: number, y: number) {
    const maxX = Math.max(8, window.innerWidth - 230);
    const maxY = Math.max(8, window.innerHeight - Math.max(80, items.length * 44 + 16));
    setMenu({ x: Math.max(8, Math.min(x, maxX)), y: Math.max(8, Math.min(y, maxY)) });
  }

  return (
    <>
      <button
        aria-controls={menu ? menuId : undefined}
        aria-expanded={Boolean(menu)}
        aria-haspopup="menu"
        aria-label={`Card actions for ${cardTitle}`}
        className="dashboard-card-menu-trigger"
        data-card-menu-trigger
        onClick={() => {
          const rect = triggerRef.current?.getBoundingClientRect();
          open(rect?.right ?? 16, rect?.bottom ?? 16);
        }}
        onContextMenu={(event) => {
          event.preventDefault();
          open(event.clientX, event.clientY);
        }}
        ref={triggerRef}
        type="button"
      >
        <MoreHorizontal aria-hidden="true" size={20} />
      </button>
      {menu ? createPortal((
        <div
          className="dashboard-card-menu"
          id={menuId}
          onKeyDown={(event) => {
            const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'));
            const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
            if (event.key === "Escape") { event.preventDefault(); close(); }
            else if (event.key === "ArrowDown") { event.preventDefault(); buttons[(current + 1) % buttons.length]?.focus(); }
            else if (event.key === "ArrowUp") { event.preventDefault(); buttons[(current - 1 + buttons.length) % buttons.length]?.focus(); }
            else if (event.key === "Home") { event.preventDefault(); buttons[0]?.focus(); }
            else if (event.key === "End") { event.preventDefault(); buttons[buttons.length - 1]?.focus(); }
          }}
          ref={menuRef}
          role="menu"
          style={{ left: menu.x, top: menu.y }}
        >
          {items.length > 0 ? items.map((item) => (
            <button
              className={item.destructive ? "dashboard-card-menu__danger" : undefined}
              key={item.action}
              onClick={() => {
                triggerRef.current?.focus();
                close(false);
                onSelect(item.action);
              }}
              role="menuitem"
              type="button"
            >
              {item.icon}{item.label}
            </button>
          )) : <span className="dashboard-card-menu__empty">No actions available</span>}
        </div>
      ), document.body) : null}
    </>
  );
}
