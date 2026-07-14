import { Archive, Copy, MoreHorizontal, Pencil } from "lucide-react";
import { useEffect, useRef, useState } from "react";

export type DashboardMenuAction = "rename" | "duplicate" | "archive";

export function DashboardActionMenu({
  canDuplicate,
  canManage,
  onSelect
}: {
  canDuplicate: boolean;
  canManage: boolean;
  onSelect: (action: DashboardMenuAction) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    rootRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    const outside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    return () => document.removeEventListener("mousedown", outside);
  }, [open]);
  if (!canManage && !canDuplicate) return null;
  return (
    <div className="dashboard-action-menu" ref={rootRef}>
      <button aria-expanded={open} aria-haspopup="menu" aria-label="Dashboard actions" onClick={() => setOpen((value) => !value)} ref={triggerRef} type="button"><MoreHorizontal aria-hidden="true" size={20} /></button>
      {open ? (
        <div onKeyDown={(event) => { if (event.key === "Escape") { setOpen(false); triggerRef.current?.focus(); } }} role="menu">
          {canManage ? <MenuButton action="rename" icon={<Pencil aria-hidden="true" size={16} />} label="Rename dashboard" /> : null}
          {canDuplicate ? <MenuButton action="duplicate" icon={<Copy aria-hidden="true" size={16} />} label="Duplicate dashboard" /> : null}
          {canManage ? <MenuButton action="archive" danger icon={<Archive aria-hidden="true" size={16} />} label="Archive dashboard" /> : null}
        </div>
      ) : null}
    </div>
  );

  function MenuButton({ action, danger = false, icon, label }: { action: DashboardMenuAction; danger?: boolean; icon: React.ReactNode; label: string }) {
    return <button className={danger ? "dashboard-action-menu__danger" : undefined} onClick={() => { setOpen(false); onSelect(action); }} role="menuitem" type="button">{icon}{label}</button>;
  }
}
