import { useEffect, useRef, useState } from "react";

import type { DashboardCardLayout, DashboardDetail, UpdateEditorLayoutResponse } from "../types";

type Layouts = Record<string, DashboardCardLayout>;
type Draft = { id: string; version: number; server: Layouts; layouts: Layouts; conflict: boolean };
const BREAKPOINTS = ["desktop", "tablet", "mobile"] as const;

export function useDashboardLayoutDraft(dashboard: DashboardDetail | null) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const expectedMutationVersion = useRef<number | null>(null);
  const versionRef = useRef(1);

  useEffect(() => {
    if (!dashboard) return;
    const expected = expectedMutationVersion.current;
    expectedMutationVersion.current = null;
    versionRef.current = dashboard.layout_version;
    setDraft((current) => {
      const latest = snapshot(dashboard);
      if (!current || current.id !== dashboard.id || !isDirty(current)) return latest;
      const knownMutation = dashboard.layout_version === expected;
      const conflict = current.conflict || (dashboard.layout_version !== current.version && !knownMutation);
      const layouts: Layouts = {};
      for (const card of dashboard.cards) {
        layouts[card.id] = current.layouts[card.id] ?? card.layout;
        if (!current.layouts[card.id]) {
          layouts[card.id] = { ...card.layout };
          for (const breakpoint of BREAKPOINTS) {
            const bottom = Math.max(0, ...Object.values(layouts).filter((layout) => layout !== layouts[card.id])
              .map((layout) => layout[breakpoint].y + layout[breakpoint].h));
            // New cards must not occupy an existing draft's unsaved position.
            const retainedBottom = Math.max(bottom, ...dashboard.cards.filter((item) => current.layouts[item.id])
              .map((item) => current.layouts[item.id][breakpoint].y + current.layouts[item.id][breakpoint].h));
            layouts[card.id][breakpoint] = { ...card.layout[breakpoint], y: retainedBottom };
          }
        }
      }
      let invalidSize = false;
      for (const card of dashboard.cards) {
        for (const breakpoint of BREAKPOINTS) {
          const local = layouts[card.id][breakpoint];
          if (card.allowed_sizes[breakpoint].some((size) => size.w === local.w && size.h === local.h)) continue;
          const previous = current.server[card.id]?.[breakpoint];
          if (previous && previous.w === local.w && previous.h === local.h && knownMutation) {
            const incoming = card.layout[breakpoint];
            const columns = breakpoint === "desktop" ? 12 : breakpoint === "tablet" ? 6 : 1;
            layouts[card.id] = { ...layouts[card.id], [breakpoint]: { ...local, w: incoming.w, h: incoming.h, x: Math.min(local.x, columns - incoming.w) } };
          } else invalidSize = true;
        }
      }
      const collision = BREAKPOINTS.some((breakpoint) => Object.values(layouts).some((left, index, all) =>
        all.slice(index + 1).some((right) => {
          const a = left[breakpoint]; const b = right[breakpoint];
          return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
        })));
      return {
        id: current.id,
        version: conflict ? current.version : latest.version,
        server: conflict ? current.server : latest.server,
        layouts,
        conflict: conflict || invalidSize || collision
      };
    });
  }, [dashboard]);

  const active = draft?.id === dashboard?.id ? draft : null;
  const layouts = Object.fromEntries((dashboard?.cards ?? []).map((card) => [card.id, active?.layouts[card.id] ?? card.layout]));
  return {
    layouts,
    dirty: active ? isDirty(active) : false,
    conflict: active?.conflict ?? false,
    version: active?.version ?? dashboard?.layout_version ?? 1,
    update(layouts: Layouts) { setDraft((current) => current ? { ...current, layouts } : current); },
    markConflict() { setDraft((current) => current ? { ...current, conflict: true } : current); },
    expectMutation(increment: number, actualVersion?: number) {
      const expected = (expectedMutationVersion.current ?? versionRef.current) + increment;
      expectedMutationVersion.current = actualVersion === undefined || actualVersion === expected ? expected : null;
    },
    reset(latest = dashboard) { if (latest) setDraft(snapshot(latest)); },
    saved(response: UpdateEditorLayoutResponse) {
      const savedLayouts = response.items.length ? Object.fromEntries(response.items.map((item) => [item.card_id, {
        version: 1 as const, desktop: item.desktop, tablet: item.tablet, mobile: item.mobile
      }])) : layouts;
      setDraft((current) => current ? { ...current, version: response.layout_version, server: savedLayouts, layouts: savedLayouts, conflict: false } : current);
    }
  };
}

function snapshot(dashboard: DashboardDetail): Draft {
  const layouts = Object.fromEntries(dashboard.cards.map((card) => [card.id, card.layout]));
  return { id: dashboard.id, version: dashboard.layout_version, server: layouts, layouts, conflict: false };
}
function isDirty(draft: Draft): boolean { return fingerprint(draft.layouts) !== fingerprint(draft.server); }
function fingerprint(layouts: Layouts): string {
  return JSON.stringify(Object.entries(layouts).sort(([left], [right]) => left.localeCompare(right)));
}
