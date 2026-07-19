import type { AuthScope } from "../../../auth/types";
import type { CurrentQueryResult } from "../../ask-data/types";
import type {
  ActionPreviewRequest,
  ActionResolution,
  ActionSelectorKind,
  SupportedActionType
} from "../types";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_TARGETS = 100;
const ACTION_SELECTOR: Record<SupportedActionType, ActionSelectorKind> = {
  reclaim_unused_license: "license_assignment",
  disable_inactive_user: "directory_user"
};

export function resolveActionSuggestion({
  canRequestAction,
  current,
  activeScope
}: {
  canRequestAction: boolean;
  current: CurrentQueryResult | null;
  activeScope: AuthScope | null;
}): ActionResolution {
  if (!canRequestAction || !current) return { status: "hidden" };
  const suggestions = current.result.suggested_actions ?? [];
  if (!suggestions.length) return { status: "hidden" };
  if (suggestions.length !== 1) return unavailable("This action recommendation is unavailable.");

  const suggestion = suggestions[0];
  if (
    current.result.status !== "succeeded" ||
    current.result.clarification_required ||
    current.result.truncated
  ) {
    return unavailable("Run the approved template again to create a current action preview.");
  }
  if (!isUuid(current.result.query_run_id) || !activeScope || !isUuid(activeScope.id)) {
    return unavailable("A current query and exact Scope are required to preview this action.");
  }
  if (
    ACTION_SELECTOR[suggestion.action_type] !== suggestion.selector_kind ||
    !suggestion.result_identifier_column
  ) {
    return unavailable("This action recommendation is unavailable.");
  }
  if (!current.result.rows.length) {
    return unavailable("No visible records are available for this action.");
  }

  const selectors: string[] = [];
  const seen = new Set<string>();
  for (const row of current.result.rows) {
    const value = row[suggestion.result_identifier_column];
    if (typeof value !== "string" || !isUuid(value)) {
      return unavailable("The result cannot be mapped safely to action targets.");
    }
    const normalized = value.toLowerCase();
    if (!seen.has(normalized)) {
      seen.add(normalized);
      selectors.push(value);
    }
  }
  if (!selectors.length || selectors.length > MAX_TARGETS) {
    return unavailable("The result exceeds the safe action preview limit.");
  }

  const base: ActionPreviewRequest = {
    action_type: suggestion.action_type,
    source_query_run_id: current.result.query_run_id,
    scope_id: activeScope.id,
    reason: defaultReason(suggestion.action_type)
  };
  if (activeScope.departmentId && isUuid(activeScope.departmentId)) {
    base.department_id = activeScope.departmentId;
  }
  if (suggestion.selector_kind === "license_assignment") {
    base.license_assignment_ids = selectors;
  } else {
    base.target_user_ids = selectors;
  }
  return { status: "available", suggestion, targetCount: selectors.length, previewRequest: base };
}

function defaultReason(actionType: SupportedActionType): string {
  return actionType === "reclaim_unused_license"
    ? "Request approval to reclaim unused licenses from this current governed result."
    : "Request approval to disable inactive users from this current governed result.";
}

function unavailable(reason: string): ActionResolution {
  return { status: "unavailable", reason };
}

function isUuid(value: string | null | undefined): value is string {
  return typeof value === "string" && UUID_PATTERN.test(value);
}
