import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

import type { QueryResultRow, QueryRowValue } from "../../ask-data/types";
import type { DashboardCardRefreshResult, DashboardCardType, VisualizationConfig, VisualizationMapping } from "../types";
import { formatVisualizationValue, inferVisualization, numericValue } from ".";

const MAX_CHART_ROWS = 24;
const SERIES_COLORS = [
  "var(--qops-chart-1)",
  "var(--qops-chart-2)",
  "var(--qops-chart-3)",
  "var(--qops-chart-4)",
  "var(--qops-chart-5)",
  "var(--qops-chart-6)"
];

export function DashboardVisualization({
  config,
  result,
  title
}: {
  config: VisualizationConfig;
  result: DashboardCardRefreshResult;
  title: string;
}) {
  const recommendation = inferVisualization({
    columns: result.columns,
    rows: result.rows,
    currentConfig: config
  });
  const mapping = validMapping(config.mapping, result.columns)
    ? config.mapping
    : recommendation.mapping;
  const rows = result.rows.slice(0, MAX_CHART_ROWS);
  const truncated = result.truncated || result.rows.length > rows.length;
  const primaryMeasure = mapping.value_columns[0];
  const summary = `${title}: ${visualizationLabel(recommendation.renderType)} visualization with ${result.row_count} ${result.row_count === 1 ? "row" : "rows"}${truncated ? "; visual data is truncated" : ""}.${primaryMeasure ? ` Primary measure: ${humanize(primaryMeasure)}.` : ""}`;

  if (result.rows.length === 0 || result.columns.length === 0) {
    return <VisualizationEmptyState />;
  }

  return (
    <div className="dashboard-visualization" data-visualization={recommendation.renderType}>
      <p className="qops-sr-only">{summary}</p>
      {recommendation.warning ? (
        <p className="dashboard-visualization__warning" role="status">
          {recommendation.warning}
        </p>
      ) : null}
      <VisualizationByType
        mapping={mapping}
        rows={rows}
        title={title}
        type={recommendation.renderType}
      />
      {truncated ? (
        <p className="dashboard-visualization__truncated">Showing a representative subset of the returned data.</p>
      ) : null}
    </div>
  );
}

function VisualizationByType({
  mapping,
  rows,
  title,
  type
}: {
  mapping: VisualizationMapping;
  rows: QueryResultRow[];
  title: string;
  type: DashboardCardType;
}) {
  switch (type) {
    case "kpi":
      return <KpiVisualization mapping={mapping} rows={rows} />;
    case "bar":
      return <BarVisualization mapping={mapping} rows={rows} />;
    case "line":
      return <LineVisualization mapping={mapping} rows={rows} />;
    case "area":
      return <AreaVisualization mapping={mapping} rows={rows} />;
    case "donut":
      return <DonutVisualization mapping={mapping} rows={rows} title={title} />;
    case "semicircle_gauge":
      return <SemicircleGaugeVisualization mapping={mapping} rows={rows} title={title} />;
    case "stacked_bar":
      return <StackedBarVisualization mapping={mapping} rows={rows} />;
    case "status_list":
      return <StatusListVisualization mapping={mapping} rows={rows} />;
    default:
      return <TableVisualization rows={rows} />;
  }
}

export function KpiVisualization({ mapping, rows }: VizProps) {
  const valueColumn = mapping.value_columns[0];
  const labelColumn = mapping.label_column;
  return (
    <div className="dashboard-viz-kpi">
      <strong>{formatVisualizationValue(valueColumn ? rows[0]?.[valueColumn] : undefined)}</strong>
      {labelColumn ? <span>{formatVisualizationValue(rows[0]?.[labelColumn])}</span> : null}
    </div>
  );
}

export function TableVisualization({ rows }: { rows: QueryResultRow[] }) {
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  return (
    <div className="dashboard-viz-table">
      <table aria-label="Dashboard card results">
        <thead><tr>{columns.map((column) => <th scope="col" key={column}>{humanize(column)}</th>)}</tr></thead>
        <tbody>
          {rows.slice(0, 10).map((row, index) => (
            <tr key={index}>{columns.map((column) => <td key={column}>{formatVisualizationValue(row[column])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function BarVisualization({ mapping, rows }: VizProps) {
  return (
    <ChartFrame>
      <BarChart data={rows} margin={CHART_MARGIN}>
        <CartesianGrid stroke="var(--qops-color-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={mapping.category_column ?? undefined} tick={AXIS_TICK} />
        <YAxis tick={AXIS_TICK} width={46} />
        <SafeTooltip />
        {mapping.value_columns.slice(0, 4).map((column, index) => (
          <Bar dataKey={column} fill={SERIES_COLORS[index]} key={column} radius={[4, 4, 0, 0]} />
        ))}
      </BarChart>
    </ChartFrame>
  );
}

export function LineVisualization({ mapping, rows }: VizProps) {
  return (
    <ChartFrame>
      <LineChart data={rows} margin={CHART_MARGIN}>
        <CartesianGrid stroke="var(--qops-color-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={mapping.category_column ?? undefined} tick={AXIS_TICK} />
        <YAxis tick={AXIS_TICK} width={46} />
        <SafeTooltip />
        {mapping.value_columns.slice(0, 4).map((column, index) => (
          <Line dataKey={column} dot={rows.length <= 12} key={column} stroke={SERIES_COLORS[index]} strokeWidth={2} type="monotone" />
        ))}
      </LineChart>
    </ChartFrame>
  );
}

export function AreaVisualization({ mapping, rows }: VizProps) {
  return (
    <ChartFrame>
      <AreaChart data={rows} margin={CHART_MARGIN}>
        <CartesianGrid stroke="var(--qops-color-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey={mapping.category_column ?? undefined} tick={AXIS_TICK} />
        <YAxis tick={AXIS_TICK} width={46} />
        <SafeTooltip />
        {mapping.value_columns.slice(0, 4).map((column, index) => (
          <Area dataKey={column} fill={SERIES_COLORS[index]} fillOpacity={0.18} key={column} stroke={SERIES_COLORS[index]} strokeWidth={2} type="monotone" />
        ))}
      </AreaChart>
    </ChartFrame>
  );
}

export function DonutVisualization({ mapping, rows, title }: VizProps & { title: string }) {
  const category = mapping.category_column;
  const value = mapping.value_columns[0];
  const data = category && value
    ? rows.map((row) => ({ name: formatVisualizationValue(row[category]), value: numericValue(row[value]) ?? 0 }))
    : [];
  return (
    <ChartFrame>
      <PieChart accessibilityLayer aria-label={`${title} donut chart`}>
        <Pie data={data} dataKey="value" innerRadius="52%" nameKey="name" outerRadius="78%" paddingAngle={2}>
          {data.map((entry, index) => <Cell fill={SERIES_COLORS[index % SERIES_COLORS.length]} key={`${entry.name}-${index}`} />)}
        </Pie>
        <SafeTooltip />
        <Legend wrapperStyle={{ color: "var(--qops-color-text-subtle)", fontSize: 12 }} />
      </PieChart>
    </ChartFrame>
  );
}

export function SemicircleGaugeVisualization({ mapping, rows, title }: VizProps & { title: string }) {
  const value = numericValue(rows[0]?.[mapping.value_columns[0]]) ?? 0;
  const targetValue = mapping.target_column ? numericValue(rows[0]?.[mapping.target_column]) : null;
  const target = targetValue && targetValue > 0 ? targetValue : 100;
  const bounded = Math.max(0, Math.min(value, target));
  const data = [{ name: "Current", value: bounded }, { name: "Remaining", value: Math.max(0, target - bounded) }];
  return (
    <div className="dashboard-viz-gauge">
      <ChartFrame>
        <PieChart accessibilityLayer aria-label={`${title} semicircle gauge`}>
          <Pie data={data} dataKey="value" cx="50%" cy="82%" endAngle={0} innerRadius="66%" outerRadius="90%" startAngle={180}>
            <Cell fill="var(--qops-chart-1)" />
            <Cell fill="var(--qops-color-muted-surface)" />
          </Pie>
        </PieChart>
      </ChartFrame>
      <strong>{formatVisualizationValue(value)}</strong>
      <span>of {formatVisualizationValue(target)}</span>
    </div>
  );
}

export function StackedBarVisualization({ mapping, rows }: VizProps) {
  const category = mapping.category_column;
  const series = mapping.series_column;
  const value = mapping.value_columns[0];
  const { data, keys } = pivotRows(rows, category, series, value);
  return (
    <ChartFrame>
      <BarChart data={data} margin={CHART_MARGIN}>
        <CartesianGrid stroke="var(--qops-color-border)" strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="category" tick={AXIS_TICK} />
        <YAxis tick={AXIS_TICK} width={46} />
        <SafeTooltip />
        <Legend wrapperStyle={{ color: "var(--qops-color-text-subtle)", fontSize: 12 }} />
        {keys.map((key, index) => <Bar dataKey={key} fill={SERIES_COLORS[index % SERIES_COLORS.length]} key={key} stackId="values" />)}
      </BarChart>
    </ChartFrame>
  );
}

export function StatusListVisualization({ mapping, rows }: VizProps) {
  const label = mapping.label_column ?? Object.keys(rows[0] ?? {})[0];
  const supporting = Object.keys(rows[0] ?? {}).filter((column) => column !== label).slice(0, 2);
  return (
    <ul className="dashboard-viz-status-list">
      {rows.slice(0, 12).map((row, index) => (
        <li key={index}>
          <span className="dashboard-viz-status-list__dot" aria-hidden="true" />
          <strong>{formatVisualizationValue(row[label])}</strong>
          {supporting.map((column) => <span key={column}>{formatVisualizationValue(row[column])}</span>)}
        </li>
      ))}
    </ul>
  );
}

export function VisualizationEmptyState() {
  return <p className="dashboard-visualization__empty">No result rows are available for this card.</p>;
}

type VizProps = { mapping: VisualizationMapping; rows: QueryResultRow[] };
const CHART_MARGIN = { top: 8, right: 8, bottom: 4, left: 0 };
const AXIS_TICK = { fill: "var(--qops-color-text-faint)", fontSize: 11 };

function ChartFrame({ children }: { children: React.ReactElement }) {
  return <div className="dashboard-viz-chart"><ResponsiveContainer height="100%" minHeight={180} width="100%">{children}</ResponsiveContainer></div>;
}

function SafeTooltip() {
  return <Tooltip contentStyle={{ background: "var(--qops-color-elevated-surface)", border: "1px solid var(--qops-color-border)", borderRadius: 8, color: "var(--qops-color-text)" }} formatter={(value) => formatVisualizationValue(value as QueryRowValue)} />;
}

function validMapping(mapping: VisualizationMapping, columns: string[]): boolean {
  const candidates = [mapping.category_column, mapping.series_column, mapping.label_column, mapping.target_column, ...mapping.value_columns].filter((value): value is string => value !== null);
  return candidates.length > 0 && candidates.every((column) => columns.includes(column));
}

function pivotRows(rows: QueryResultRow[], category: string | null, series: string | null, value: string | undefined) {
  if (!category || !series || !value) return { data: [], keys: [] };
  const groups = new Map<string, Record<string, string | number>>();
  const keys = new Set<string>();
  for (const row of rows) {
    const categoryValue = formatVisualizationValue(row[category]);
    const seriesValue = formatVisualizationValue(row[series]);
    const numeric = numericValue(row[value]);
    if (numeric === null) continue;
    keys.add(seriesValue);
    const group = groups.get(categoryValue) ?? { category: categoryValue };
    group[seriesValue] = numeric;
    groups.set(categoryValue, group);
  }
  return { data: [...groups.values()], keys: [...keys].slice(0, 8) };
}

function humanize(value: string): string {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function visualizationLabel(type: DashboardCardType): string {
  return type.replace(/_/g, " ");
}
