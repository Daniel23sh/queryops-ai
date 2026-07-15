import type { QueryResultRow } from "../ask-data/types";

export type DashboardVisibilityScope = "personal" | "department" | "global";
export type DashboardRelationship = "owned" | "shared";
export type DashboardBreakpoint = "desktop" | "tablet" | "mobile";
export type VisualizationMode = "auto" | "manual";
export type DashboardCardType =
  | "kpi"
  | "table"
  | "bar"
  | "line"
  | "area"
  | "donut"
  | "semicircle_gauge"
  | "stacked_bar"
  | "status_list";

export type DashboardJsonValue =
  | string
  | number
  | boolean
  | null
  | DashboardJsonValue[]
  | { [key: string]: DashboardJsonValue };

export type GridItemLayout = { x: number; y: number; w: number; h: number };
export type DashboardCardLayout = {
  version: 1;
  desktop: GridItemLayout;
  tablet: GridItemLayout;
  mobile: GridItemLayout;
};
export type VisualizationMapping = {
  category_column: string | null;
  value_columns: string[];
  series_column: string | null;
  label_column: string | null;
  target_column: string | null;
};
export type VisualizationConfig = {
  mode: VisualizationMode;
  type: DashboardCardType;
  recommended_type: DashboardCardType;
  mapping: VisualizationMapping;
};
export type GridSize = { w: number; h: number };
export type AllowedCardSizes = Record<DashboardBreakpoint, GridSize[]>;

export type DashboardCard = {
  id: string;
  dashboard_id: string;
  saved_query_id: string | null;
  title: string;
  description: string | null;
  card_type: DashboardCardType;
  position: number;
  layout?: DashboardCardLayout | DashboardJsonValue;
  visualization?: VisualizationConfig;
  allowed_sizes?: AllowedCardSizes;
  config?: DashboardJsonValue;
  created_at: string;
  updated_at: string;
};

export type EditorDashboardCard = Omit<
  DashboardCard,
  "layout" | "visualization" | "allowed_sizes"
> & {
  layout: DashboardCardLayout;
  visualization: VisualizationConfig;
  allowed_sizes: AllowedCardSizes;
};

export type DashboardOwner = { id: string; display_name: string };
export type DashboardScope = {
  type: DashboardVisibilityScope;
  display_name: string;
};
export type DashboardPreviewCard = Pick<
  DashboardCard,
  "id" | "title" | "card_type" | "position"
>;
export type DashboardLibraryItem = {
  id: string;
  title: string;
  description: string | null;
  visibility_scope: DashboardVisibilityScope;
  relationship: DashboardRelationship;
  owner: DashboardOwner | null;
  scope: DashboardScope;
  card_count: number;
  preview_cards: DashboardPreviewCard[];
  created_at: string;
  updated_at: string;
};
export type DashboardCapabilities = {
  can_manage: boolean;
  can_duplicate: boolean;
  can_refresh_cards: boolean;
  can_export_cards: boolean;
  can_view_source: boolean;
  can_create_cards: boolean;
};
export type DashboardDetail = Omit<DashboardLibraryItem, "preview_cards"> & {
  layout_version: number;
  capabilities: DashboardCapabilities;
  cards: EditorDashboardCard[];
};

export type Dashboard = {
  id: string;
  title: string;
  description: string | null;
  visibility_scope: DashboardVisibilityScope;
  department_id: string | null;
  is_archived: boolean;
  layout_version?: number;
  created_at: string;
  updated_at: string;
  cards: DashboardCard[];
};
export type CreateDashboardRequest = {
  title: string;
  description?: string | null;
  visibility_scope?: DashboardVisibilityScope;
  department_id?: string | null;
};
export type SaveCardRequest = {
  dashboard_id: string;
  title?: string;
  description?: string | null;
  card_type?: DashboardCardType;
};
export type DashboardLayoutItem = { card_id: string; position: number };
export type UpdateDashboardLayoutRequest = { items: DashboardLayoutItem[] };
export type EditorLayoutItem = {
  card_id: string;
  desktop: GridItemLayout;
  tablet: GridItemLayout;
  mobile: GridItemLayout;
};
export type UpdateEditorLayoutRequest = {
  expected_layout_version: number;
  items: EditorLayoutItem[];
};
export type UpdateEditorLayoutResponse = {
  layout_version: number;
  items: Array<EditorLayoutItem & { position: number }>;
};
export type UpdateDashboardRequest = { title?: string; description?: string | null };
export type DashboardMutationResult = {
  id: string;
  title: string;
  description: string | null;
  visibility_scope: DashboardVisibilityScope;
  is_archived: boolean;
  layout_version: number;
  created_at: string;
  updated_at: string;
};
export type DuplicateDashboardResult = DashboardMutationResult;
export type UpdateCardRequest = {
  title?: string;
  description?: string | null;
  visualization?: VisualizationConfig;
};
export type CardMutationResult = {
  card: EditorDashboardCard;
  layout_version: number;
};
export type RemoveCardResult = { id: string; layout_version: number };
export type CardSource = { question: string; sql: string };

export type DashboardCardRefreshResult = {
  card_id: string;
  dashboard_id: string;
  saved_query_id: string;
  query_run_id: string;
  status: "succeeded";
  columns: string[];
  rows: QueryResultRow[];
  row_count: number;
  duration_ms: number;
  truncated: boolean;
  refreshed_at: string;
  message: string;
  warnings: string[];
};
