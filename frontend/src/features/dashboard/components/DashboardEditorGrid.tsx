import { useEffect, useMemo, useRef, useState } from "react";
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
  const [moveAnnouncement, setMoveAnnouncement] = useState("");
  const announcementFrameRef = useRef<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(1120);
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
  const gridLayouts = useMemo(() => toResponsiveLayouts(cards, layouts), [cards, layouts]);
  const orderedMobileCards = [...cards].sort((left, right) => layouts[left.id].mobile.y - layouts[right.id].mobile.y);

  function updateFromGrid(nextLayouts: ResponsiveLayouts<DashboardBreakpoint>) {
    if (!editMode) return;
    const next = { ...layouts };
    for (const card of cards) {
      const previous = layouts[card.id];
      next[card.id] = {
        version: 1,
        desktop: safeGridItem(card, "desktop", nextLayouts.desktop?.find((item) => item.i === card.id), previous.desktop),
        tablet: safeGridItem(card, "tablet", nextLayouts.tablet?.find((item) => item.i === card.id), previous.tablet),
        mobile: safeGridItem(card, "mobile", nextLayouts.mobile?.find((item) => item.i === card.id), previous.mobile)
      };
    }
    onLayoutsChange(next);
  }

  function snapResize(layout: Layout, _oldItem: Layout[number] | null, newItem: Layout[number] | null) {
    if (!newItem) return;
    const next = { ...layouts };
    for (const card of cards) {
      next[card.id] = {
        ...layouts[card.id],
        [breakpoint]: safeGridItem(
          card,
          breakpoint,
          layout.find((item) => item.i === card.id),
          layouts[card.id][breakpoint]
        )
      };
    }
    onLayoutsChange(next);
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

  function announceMove(message: string) {
    if (announcementFrameRef.current !== null) {
      window.cancelAnimationFrame(announcementFrameRef.current);
    }
    setMoveAnnouncement("");
    announcementFrameRef.current = window.requestAnimationFrame(() => {
      announcementFrameRef.current = null;
      setMoveAnnouncement(message);
    });
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
          handle: ".dashboard-card-drag-handle"
        }}
        layouts={gridLayouts}
        margin={[14, 14]}
        onBreakpointChange={(value) => setBreakpoint(value)}
        onLayoutChange={(_current, all) => updateFromGrid(all)}
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
function fromGridItem(item: Layout[number] | undefined, fallback: GridItemLayout): GridItemLayout {
  return item ? { x: item.x, y: item.y, w: item.w, h: item.h } : fallback;
}
function safeGridItem(
  card: EditorDashboardCard,
  breakpoint: DashboardBreakpoint,
  item: Layout[number] | undefined,
  fallback: GridItemLayout
): GridItemLayout {
  const candidate = fromGridItem(item, fallback);
  const size = nearestAllowedSize(card.visualization.type, breakpoint, candidate);
  const columns = COLUMNS[breakpoint];
  return {
    ...candidate,
    ...size,
    x: breakpoint === "mobile" ? 0 : Math.max(0, Math.min(candidate.x, columns - size.w)),
    y: Math.max(0, candidate.y)
  };
}
