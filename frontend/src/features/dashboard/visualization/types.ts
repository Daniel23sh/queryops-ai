import type { QueryResultRow } from "../../ask-data/types";
import type {
  DashboardCardType,
  VisualizationConfig,
  VisualizationMapping
} from "../types";

export type ColumnKind =
  | "numeric"
  | "temporal"
  | "categorical"
  | "status"
  | "unsupported";

export type ColumnProfile = {
  name: string;
  kind: ColumnKind;
  distinctCount: number;
  nonNullCount: number;
};

export type VisualizationInput = {
  columns: string[];
  rows: QueryResultRow[];
  currentConfig?: VisualizationConfig | null;
};

export type VisualizationRecommendation = {
  recommendedType: DashboardCardType;
  renderType: DashboardCardType;
  compatibleTypes: DashboardCardType[];
  mapping: VisualizationMapping;
  confidence: "high" | "medium" | "low";
  reason: string;
  warning: string | null;
  profiles: ColumnProfile[];
};
