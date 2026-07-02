import type { PermissionKey } from "../../auth/types";

export type JsonPrimitive = string | number | boolean | null;

export type JsonValue =
  | JsonPrimitive
  | JsonValue[]
  | {
      [key: string]: JsonValue;
    };

export type QueryTemplateParameterValue = JsonPrimitive;

export type QueryTemplateParameter = {
  name: string;
  data_type: string;
  description: string;
  required: boolean;
  default: QueryTemplateParameterValue;
};

export type QueryTemplate = {
  id: string;
  title: string;
  description: string;
  domain: string;
  category: string;
  natural_language_question: string;
  parameters: QueryTemplateParameter[];
  scope_type: string | null;
  required_permission: PermissionKey | string;
};

export type QueryTemplateCategory = {
  category: string;
  templates: QueryTemplate[];
};

export type QueryTemplateCategoryMap = Record<string, QueryTemplate[]>;

export type EmptyQueryParameters = Record<string, never>;

export type QueryRunRequest = {
  question: string;
  template_id?: string | null;
  parameters?: EmptyQueryParameters | null;
};

export type QueryClarifyRequest = {
  question: string;
};

export type QueryStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "clarification_required";

export type QueryWarning = string;

export type QueryErrorCode = string;

export type QueryRowValue = JsonValue;

export type QueryResultRow = Record<string, QueryRowValue>;

export type QueryValidationMetadata = {
  valid: boolean | null;
  error_code: QueryErrorCode | null;
};

export type QueryExecutionMetadata = {
  status: QueryStatus | string | null;
  error_code: QueryErrorCode | null;
  row_count: number | null;
  duration_ms: number | null;
  truncated: boolean | null;
};

export type QuerySelfCorrectionMetadata = {
  attempted: boolean | null;
  succeeded: boolean | null;
  original_error_code: QueryErrorCode | null;
  final_error_code?: QueryErrorCode | null;
};

export type QueryMetadata = {
  provider?: string | null;
  model?: string | null;
  template_id?: string | null;
  referenced_tables?: string[];
  scope_type?: string | null;
  clarification_required?: boolean;
  clarified_from_query_run_id?: string;
  validation?: QueryValidationMetadata;
  execution?: QueryExecutionMetadata;
  self_correction?: QuerySelfCorrectionMetadata;
};

export type QueryRunResult = {
  query_run_id: string | null;
  status: QueryStatus;
  columns: string[];
  rows: QueryResultRow[];
  row_count: number;
  duration_ms: number;
  truncated: boolean;
  message: string;
  warnings: QueryWarning[];
  clarification_required: boolean;
  metadata: QueryMetadata;
  error_code?: QueryErrorCode;
  generated_sql?: string | null;
  executed_sql?: string | null;
};

export type QueryHistoryItem = {
  id: string;
  status: QueryStatus;
  natural_language_question: string;
  row_count: number;
  duration_ms: number;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  metadata: QueryMetadata;
  generated_sql?: string | null;
  executed_sql?: string | null;
};

export type QueryHistoryParams = {
  limit?: number;
  offset?: number;
};

export type ScopeQueryHistoryParams = QueryHistoryParams;
