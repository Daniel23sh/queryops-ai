import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Responsive,
  verticalCompactor,
  type Layout,
  type ResponsiveLayouts
} from "react-grid-layout";
import "react-grid-layout/css/styles.css";

import type {
  DashboardBreakpoint,
  DashboardCardLayout,
  DashboardCardRefreshResult,
  EditorDashboardCard,
  GridItemLayout
} from "../types";
import { nearestAllowedSize } from "../visualization";
import type { CardMenuAction } from "./CardContextMenu";
import { DashboardEditorCard } from "./DashboardEditorCard";

const BREAKPOINTS = { desktop: 1024, tablet: 600, mobile: 0 };
const COLUMNS = { desktop: 12, tablet: 6, mobile: 1 };

type ActiveLayoutUpdate =
  | { kind: "position"; layout: Layout }
  | {
      kind: "resize";
      cardId: string;
      item: Layout[number];
      size: { w: number; h: number };
    };

type PendingResize = {
  breakpoint: DashboardBreakpoint;
  cardTitle: string;
  changed: boolean;
  nextLayouts: Record<string, DashboardCardLayout>;
  snappedSize: { w: number; h: number };
};

type ResizeSync = PendingResize & {
  rawLayouts: ResponsiveLayouts<DashboardBreakpoint>;
};

export function DashboardEditorGrid({
  canExport,
  canRefresh,
  canViewSource,
  cards,
  csrfToken,
  editMode,
  layouts,
  onAction,
  onLayoutsChange,
  onResult
}: {
  canExport: boolean;
  canRefresh: boolean;
  canViewSource: boolean;
  cards: EditorDashboardCard[];
  csrfToken: string | null;
  editMode: boolean;
  layouts: Record<string, DashboardCardLayout>;
  onAction: (action: CardMenuAction, card: EditorDashboardCard, breakpoint: DashboardBreakpoint) => void;
  onLayoutsChange: (layouts: Record<string, DashboardCardLayout>) => void;
  onResult: (cardId: string, result: DashboardCardRefreshResult) => void;
}) {
  const [breakpoint, setBreakpoint] = useState<DashboardBreakpoint>("desktop");
  const breakpointRef = useRef<DashboardBreakpoint>("desktop");
  const [moveAnnouncement, setMoveAnnouncement] = useState("");
  const announcementFrameRef = useRef<number | null>(null);
  const pendingPointerDragRef = useRef(false);
  const pendingResizeRef = useRef<PendingResize | null>(null);
  const suppressGridChangesRef = useRef(false);
  const [resizeSync, setResizeSync] = useState<ResizeSync | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1120);
  const announceMove = useCallback((message: string) => {
    if (announcementFrameRef.current !== null) {
      window.cancelAnimationFrame(announcementFrameRef.current);
    }
    setMoveAnnouncement("");
    announcementFrameRef.current = window.requestAnimationFrame(() => {
      announcementFrameRef.current = null;
      setMoveAnnouncement(message);
    });
  }, []);
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const measure = () => setWidth(Math.max(320, node.getBoundingClientRect().width || 1120));
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    window.addEventListener("resize", measure);
    return () => {
      observer?.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);
  useEffect(() => () => {
    if (announcementFrameRef.current !== null) {
      window.cancelAnimationFrame(announcementFrameRef.current);
    }
  }, []);
  const legalGridLayouts = useMemo(() => toResponsiveLayouts(cards, layouts), [cards, layouts]);
  const gridLayouts = resizeSync?.rawLayouts ?? legalGridLayouts;
  const orderedMobileCards = [...cards].sort((left, right) => layouts[left.id].mobile.y - layouts[right.id].mobile.y);

  useEffect(() => {
    if (!resizeSync) {
      suppressGridChangesRef.current = false;
      return;
    }
    if (resizeSync.changed) {
      onLayoutsChange(resizeSync.nextLayouts);
      announceMove(
        `${resizeSync.cardTitle} resized to ${resizeSync.snappedSize.w} by ${resizeSync.snappedSize.h}. Save changes to persist.`
      );
    }
    setResizeSync(null);
  }, [announceMove, onLayoutsChange, resizeSync]);

  function updateFromGrid(currentLayout: Layout) {
    if (!editMode) return;
    const pendingResize = pendingResizeRef.current;
    if (pendingResize) {
      pendingResizeRef.current = null;
      suppressGridChangesRef.current = true;
      setResizeSync({
        ...pendingResize,
        rawLayouts: {
          ...legalGridLayouts,
          [pendingResize.breakpoint]: cloneGridLayout(currentLayout)
        }
      });
      return;
    }
    if (suppressGridChangesRef.current) return;
    if (!pendingPointerDragRef.current) return;
    pendingPointerDragRef.current = false;

    const update = buildActiveLayoutUpdate(
      cards,
      layouts,
      breakpointRef.current,
      { kind: "position", layout: currentLayout }
    );
    if (update.changed) onLayoutsChange(update.layouts);
  }

  function snapResize(
    _layout: Layout,
    oldItem: Layout[number] | null,
    newItem: Layout[number] | null
  ) {
    pendingResizeRef.current = null;
    if (
      !editMode ||
      !oldItem ||
      !newItem ||
      (oldItem.x === newItem.x &&
        oldItem.y === newItem.y &&
        oldItem.w === newItem.w &&
        oldItem.h === newItem.h)
    ) return;

    const card = cards.find((candidate) => candidate.id === newItem.i);
    if (!card) return;
    const activeBreakpoint = breakpointRef.current;
    const snappedSize = nearestAllowedSize(
      card.allowed_sizes[activeBreakpoint],
      { w: newItem.w, h: newItem.h },
      { w: oldItem.w, h: oldItem.h }
    );
    const update = buildActiveLayoutUpdate(
      cards,
      layouts,
      activeBreakpoint,
      { kind: "resize", cardId: card.id, item: newItem, size: snappedSize }
    );
    pendingResizeRef.current = {
      breakpoint: activeBreakpoint,
      cardTitle: card.title,
      changed: update.changed,
      nextLayouts: update.layouts,
      snappedSize
    };
  }

  function moveMobile(cardId: string, direction: -1 | 1) {
    const index = orderedMobileCards.findIndex((card) => card.id === cardId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= orderedMobileCards.length) return;
    const order = [...orderedMobileCards];
    [order[index], order[target]] = [order[target], order[index]];
    let y = 0;
    const next = { ...layouts };
    for (const card of order) {
      next[card.id] = { ...next[card.id], mobile: { ...next[card.id].mobile, y } };
      y += next[card.id].mobile.h;
    }
    onLayoutsChange(next);
  }

  function moveWithKeyboard(
    card: EditorDashboardCard,
    direction: "down" | "left" | "right" | "up"
  ) {
    if (!editMode || breakpoint === "mobile") return;
    const current = layouts[card.id][breakpoint];
    const columns = COLUMNS[breakpoint];
    const candidate = {
      ...current,
      x:
        direction === "left"
          ? Math.max(0, current.x - current.w)
          : direction === "right"
            ? Math.min(columns - current.w, current.x + current.w)
            : current.x,
      y:
        direction === "up"
          ? Math.max(0, current.y - current.h)
          : direction === "down"
            ? current.y + current.h
            : current.y
    };
    if (candidate.x === current.x && candidate.y === current.y) {
      announceMove(`${card.title} cannot move farther ${direction}.`);
      return;
    }

    const collidingCards = cards.filter(
      (other) =>
        other.id !== card.id &&
        overlaps(candidate, layouts[other.id][breakpoint])
    );
    if (collidingCards.length > 1) {
      announceMove(`${card.title} cannot move ${direction} without overlapping multiple cards.`);
      return;
    }
    const collidingCard = collidingCards[0];
    const next = { ...layouts, [card.id]: { ...layouts[card.id], [breakpoint]: candidate } };
    if (collidingCard) {
      const otherLayout = layouts[collidingCard.id][breakpoint];
      const swapped = { ...otherLayout, x: current.x, y: current.y };
      const swapOutOfBounds = swapped.x + swapped.w > columns;
      const swapCollides = cards.some(
        (other) =>
          other.id !== card.id &&
          other.id !== collidingCard.id &&
          overlaps(swapped, layouts[other.id][breakpoint])
      );
      if (swapOutOfBounds || overlaps(candidate, swapped) || swapCollides) {
        announceMove(`${card.title} cannot move ${direction} without overlapping another card.`);
        return;
      }
      next[collidingCard.id] = { ...layouts[collidingCard.id], [breakpoint]: swapped };
    }
    onLayoutsChange(next);
    announceMove(`${card.title} moved ${direction}. Save changes to persist the new position.`);
  }

  function announcePointerMove(
    previous: Layout[number] | null,
    current: Layout[number] | null
  ) {
    pendingPointerDragRef.current = false;
    if (
      !previous ||
      !current ||
      (previous.x === current.x && previous.y === current.y)
    ) return;
    const card = cards.find((candidate) => candidate.id === current.i);
    if (!card) return;
    pendingPointerDragRef.current = true;
    announceMove(`${card.title} moved. Save changes to persist the new position.`);
  }

  if (cards.length === 0) return <p className="dashboard-detail__empty">No cards are in this dashboard yet.</p>;

  return (
    <div className="dashboard-editor-grid" data-breakpoint={breakpoint} data-editing={editMode} ref={containerRef}>
      <Responsive<DashboardBreakpoint>
        breakpoints={BREAKPOINTS}
        className="dashboard-responsive-grid"
        cols={COLUMNS}
        compactor={verticalCompactor}
        dragConfig={{
          enabled: editMode && breakpoint !== "mobile",
          bounded: true,
          handle: ".dashboard-card-drag-handle",
          cancel: "button:not(.dashboard-card-drag-handle), input, textarea, select, a"
        }}
        layouts={gridLayouts}
        margin={[14, 14]}
        onBreakpointChange={(value) => {
          breakpointRef.current = value;
          setBreakpoint(value);
        }}
        onDragStop={(_layout, previous, current) => announcePointerMove(previous, current)}
        onLayoutChange={(current) => updateFromGrid(current)}
        onResizeStop={snapResize}
        resizeConfig={{ enabled: editMode && breakpoint !== "mobile", handles: ["se"] }}
        rowHeight={112}
        width={width}
      >
        {cards.map((card) => {
          const mobileIndex = orderedMobileCards.findIndex((candidate) => candidate.id === card.id);
          return (
            <div key={card.id}>
              <DashboardEditorCard
                breakpoint={breakpoint}
                canExport={canExport}
                canRefresh={canRefresh}
                canViewSource={canViewSource}
                card={card}
                csrfToken={csrfToken}
                editMode={editMode}
                isFirst={mobileIndex === 0}
                isLast={mobileIndex === orderedMobileCards.length - 1}
                onAction={(action, selectedCard) => onAction(action, selectedCard, breakpoint)}
                onKeyboardMove={(direction) => moveWithKeyboard(card, direction)}
                onMove={(direction) => moveMobile(card.id, direction)}
                onResult={onResult}
              />
            </div>
          );
        })}
      </Responsive>
      <p className="qops-sr-only" aria-live="polite">{moveAnnouncement}</p>
    </div>
  );
}

function overlaps(left: GridItemLayout, right: GridItemLayout): boolean {
  return !(
    left.x + left.w <= right.x ||
    right.x + right.w <= left.x ||
    left.y + left.h <= right.y ||
    right.y + right.h <= left.y
  );
}

function toResponsiveLayouts(cards: EditorDashboardCard[], layouts: Record<string, DashboardCardLayout>): ResponsiveLayouts<DashboardBreakpoint> {
  return {
    desktop: cards.map((card) => toGridItem(card.id, layouts[card.id].desktop)),
    tablet: cards.map((card) => toGridItem(card.id, layouts[card.id].tablet)),
    mobile: cards.map((card) => toGridItem(card.id, layouts[card.id].mobile))
  };
}
function toGridItem(i: string, layout: GridItemLayout) { return { i, ...layout }; }
function cloneGridLayout(layout: Layout): Layout {
  return layout.map((item) => ({
    i: item.i,
    x: item.x,
    y: item.y,
    w: item.w,
    h: item.h
  }));
}

function buildActiveLayoutUpdate(
  cards: EditorDashboardCard[],
  layouts: Record<string, DashboardCardLayout>,
  breakpoint: DashboardBreakpoint,
  change: ActiveLayoutUpdate
): { changed: boolean; layouts: Record<string, DashboardCardLayout> } {
  const columns = COLUMNS[breakpoint];
  const gridItems = change.kind === "position"
    ? new Map(change.layout.map((item) => [item.i, item]))
    : null;
  const candidate = cards.map((card) => {
    const previous = layouts[card.id][breakpoint];
    const source = change.kind === "position"
      ? gridItems?.get(card.id) ?? previous
      : card.id === change.cardId
        ? change.item
        : previous;
    const size = change.kind === "resize" && card.id === change.cardId
      ? change.size
      : { w: previous.w, h: previous.h };
    return {
      i: card.id,
      x: breakpoint === "mobile"
        ? 0
        : Math.max(0, Math.min(source.x, columns - size.w)),
      y: Math.max(0, source.y),
      w: size.w,
      h: size.h
    };
  });
  const compacted = verticalCompactor.compact(candidate, columns);
  const compactedById = new Map(compacted.map((item) => [item.i, item]));
  const next = { ...layouts };
  let changed = false;
  for (const card of cards) {
    const previous = layouts[card.id][breakpoint];
    const item = compactedById.get(card.id);
    if (!item) continue;
    const activeLayout = { x: item.x, y: item.y, w: item.w, h: item.h };
    if (sameGridItem(previous, activeLayout)) continue;
    changed = true;
    next[card.id] = { ...layouts[card.id], [breakpoint]: activeLayout };
  }
  return { changed, layouts: next };
}

function sameGridItem(left: GridItemLayout, right: GridItemLayout): boolean {
  return left.x === right.x && left.y === right.y && left.w === right.w && left.h === right.h;
}
