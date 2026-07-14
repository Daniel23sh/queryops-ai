import type { QueryResultRow } from "../ask-data/types";

export type DashboardVisibilityScope = "personal" | "department" | "global";

export type DashboardCardType = "table";

export type DashboardJsonValue =
  | string
  | number
  | boolean
  | null
  | DashboardJsonValue[]
  | {
      [key: string]: DashboardJsonValue;
    };

export type DashboardCard = {
  id: string;
  dashboard_id: string;
  saved_query_id: string | null;
  title: string;
  description: string | null;
  card_type: DashboardCardType;
  position: number;
  layout?: DashboardJsonValue;
  config?: DashboardJsonValue;
  created_at: string;
  updated_at: string;
};

export type DashboardRelationship = "owned" | "shared";

export type DashboardOwner = {
  id: string;
  display_name: string;
};

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

export type DashboardDetail = Omit<DashboardLibraryItem, "preview_cards"> & {
  cards: DashboardCard[];
};

export type Dashboard = {
  id: string;
  title: string;
  description: string | null;
  visibility_scope: DashboardVisibilityScope;
  department_id: string | null;
  is_archived: boolean;
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

export type DashboardLayoutItem = {
  card_id: string;
  position: number;
};

export type UpdateDashboardLayoutRequest = {
  items: DashboardLayoutItem[];
};

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
