import type {
  DashboardBreakpoint,
  DashboardCardType,
  GridSize
} from "../types";

export const VISUALIZATION_TYPES: DashboardCardType[] = [
  "kpi",
  "table",
  "bar",
  "line",
  "area",
  "donut",
  "semicircle_gauge",
  "stacked_bar",
  "status_list"
];

export const VISUALIZATION_LABELS: Record<DashboardCardType, string> = {
  kpi: "KPI",
  table: "Table",
  bar: "Bar",
  line: "Line",
  area: "Area",
  donut: "Donut",
  semicircle_gauge: "Semicircle gauge",
  stacked_bar: "Stacked bar",
  status_list: "Status list"
};

const CHART_SIZES: GridSize[] = [
  { w: 6, h: 2 }, { w: 8, h: 2 }, { w: 12, h: 2 },
  { w: 6, h: 3 }, { w: 8, h: 3 }, { w: 12, h: 3 }
];

export const SIZE_POLICY: Record<DashboardCardType, Record<DashboardBreakpoint, GridSize[]>> = {
  kpi: sizes([{ w: 3, h: 1 }, { w: 4, h: 1 }, { w: 6, h: 1 }], 1),
  donut: sizes([{ w: 3, h: 2 }, { w: 4, h: 2 }, { w: 6, h: 2 }], 2),
  semicircle_gauge: sizes([{ w: 3, h: 2 }, { w: 4, h: 2 }, { w: 6, h: 2 }], 2),
  bar: sizes(CHART_SIZES, 2),
  line: sizes(CHART_SIZES, 2),
  area: sizes(CHART_SIZES, 2),
  stacked_bar: sizes(CHART_SIZES, 2),
  table: sizes([
    { w: 6, h: 3 }, { w: 8, h: 3 }, { w: 12, h: 3 },
    { w: 6, h: 4 }, { w: 8, h: 4 }, { w: 12, h: 4 }
  ], 3),
  status_list: sizes([
    { w: 4, h: 2 }, { w: 6, h: 2 }, { w: 8, h: 2 }, { w: 6, h: 3 }
  ], 2)
};

function sizes(desktop: GridSize[], mobileHeight: number): Record<DashboardBreakpoint, GridSize[]> {
  const tablet = desktop
    .map(({ w, h }) => ({ w: Math.min(w, 6), h }))
    .filter((value, index, values) =>
      values.findIndex((candidate) => candidate.w === value.w && candidate.h === value.h) === index
    );
  return {
    desktop,
    tablet,
    mobile: [{ w: 1, h: mobileHeight }, { w: 1, h: mobileHeight + 1 }]
  };
}

export function nearestAllowedSize(
  type: DashboardCardType,
  breakpoint: DashboardBreakpoint,
  candidate: GridSize
): GridSize {
  const allowed = SIZE_POLICY[type][breakpoint];
  return allowed.reduce((nearest, size) => {
    const distance = Math.abs(size.w - candidate.w) + Math.abs(size.h - candidate.h);
    const nearestDistance = Math.abs(nearest.w - candidate.w) + Math.abs(nearest.h - candidate.h);
    return distance < nearestDistance ? size : nearest;
  }, allowed[0]);
}
