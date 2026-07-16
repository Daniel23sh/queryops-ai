import type {
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

export function nearestAllowedSize(
  allowed: readonly GridSize[],
  candidate: GridSize,
  origin: GridSize
): GridSize {
  if (allowed.length === 0) return origin;
  const exact = allowed.find((size) => size.w === candidate.w && size.h === candidate.h);
  if (exact) return exact;
  return allowed.reduce((nearest, size) => {
    const distance = Math.abs(size.w - candidate.w) + Math.abs(size.h - candidate.h);
    const nearestDistance = Math.abs(nearest.w - candidate.w) + Math.abs(nearest.h - candidate.h);
    if (distance < nearestDistance) return size;
    if (distance > nearestDistance) return nearest;
    return resizeDirectionScore(size, candidate, origin) > resizeDirectionScore(nearest, candidate, origin)
      ? size
      : nearest;
  }, allowed[0]);
}

function resizeDirectionScore(size: GridSize, candidate: GridSize, origin: GridSize): number {
  const widthDirection = Math.sign(candidate.w - origin.w);
  const heightDirection = Math.sign(candidate.h - origin.h);
  return (
    widthDirection * (size.w - origin.w) +
    heightDirection * (size.h - origin.h)
  );
}
