import { apiRequest } from "./client";
import type {
  CreateDashboardRequest,
  CardMutationResult,
  CardSource,
  Dashboard,
  DashboardCard,
  DashboardCardRefreshResult,
  DashboardDetail,
  DashboardLibraryItem,
  DashboardMutationResult,
  DuplicateDashboardResult,
  RemoveCardResult,
  SaveCardRequest,
  UpdateCardRequest,
  UpdateDashboardRequest,
  UpdateEditorLayoutRequest,
  UpdateEditorLayoutResponse,
  UpdateDashboardLayoutRequest
} from "../features/dashboard/types";

export function getDashboardCatalog(): Promise<Dashboard[]> {
  return apiRequest<Dashboard[]>("/api/v1/dashboards/catalog", {
    method: "GET"
  });
}

export function getMyDashboards(): Promise<Dashboard[]> {
  return apiRequest<Dashboard[]>("/api/v1/dashboards/my", {
    method: "GET"
  });
}

export function getDashboardLibrary(
  signal?: AbortSignal
): Promise<DashboardLibraryItem[]> {
  return apiRequest<DashboardLibraryItem[]>("/api/v1/dashboards/library", {
    method: "GET",
    signal
  });
}

export function getDashboardDetail(
  dashboardId: string,
  signal?: AbortSignal
): Promise<DashboardDetail> {
  return apiRequest<DashboardDetail>(
    `/api/v1/dashboards/${encodeURIComponent(dashboardId)}`,
    { method: "GET", signal }
  );
}

export function createDashboard(
  payload: CreateDashboardRequest,
  csrfToken: string
): Promise<Dashboard> {
  return apiRequest<Dashboard>("/api/v1/dashboards", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify(createDashboardRequestBody(payload))
  });
}

export function saveQueryRunAsCard(
  queryRunId: string,
  payload: SaveCardRequest,
  csrfToken: string
): Promise<DashboardCard> {
  return apiRequest<DashboardCard>(
    `/api/v1/query-runs/${encodeURIComponent(queryRunId)}/save-card`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify(saveCardRequestBody(payload))
    }
  );
}

export function refreshDashboardCard(
  cardId: string,
  csrfToken: string
): Promise<DashboardCardRefreshResult> {
  return apiRequest<DashboardCardRefreshResult>(
    `/api/v1/cards/${encodeURIComponent(cardId)}/refresh`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: "{}"
    }
  );
}

export function updateMyDashboardLayout(
  payload: UpdateDashboardLayoutRequest,
  csrfToken: string
): Promise<Dashboard> {
  return apiRequest<Dashboard>("/api/v1/dashboards/my/layout", {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    body: JSON.stringify(dashboardLayoutRequestBody(payload))
  });
}

export function updateDashboard(
  dashboardId: string,
  payload: UpdateDashboardRequest,
  csrfToken: string
): Promise<DashboardMutationResult> {
  const body: UpdateDashboardRequest = {};
  if (payload.title !== undefined) body.title = payload.title.trim();
  if (payload.description !== undefined) body.description = payload.description;
  return editorMutation(`/api/v1/dashboards/${encodeURIComponent(dashboardId)}`, "PATCH", body, csrfToken);
}

export function duplicateDashboard(
  dashboardId: string,
  csrfToken: string
): Promise<DuplicateDashboardResult> {
  return editorMutation(`/api/v1/dashboards/${encodeURIComponent(dashboardId)}/duplicate`, "POST", {}, csrfToken);
}

export function archiveDashboard(
  dashboardId: string,
  csrfToken: string
): Promise<{ id: string; is_archived: true }> {
  return editorMutation(`/api/v1/dashboards/${encodeURIComponent(dashboardId)}`, "DELETE", undefined, csrfToken);
}

export function updateDashboardCard(
  cardId: string,
  payload: UpdateCardRequest,
  csrfToken: string
): Promise<CardMutationResult> {
  const body: UpdateCardRequest = {};
  if (payload.title !== undefined) body.title = payload.title.trim();
  if (payload.description !== undefined) body.description = payload.description;
  if (payload.visualization !== undefined) body.visualization = payload.visualization;
  return editorMutation(`/api/v1/cards/${encodeURIComponent(cardId)}`, "PATCH", body, csrfToken);
}

export function duplicateDashboardCard(
  cardId: string,
  csrfToken: string
): Promise<CardMutationResult> {
  return editorMutation(`/api/v1/cards/${encodeURIComponent(cardId)}/duplicate`, "POST", {}, csrfToken);
}

export function removeDashboardCard(
  cardId: string,
  csrfToken: string
): Promise<RemoveCardResult> {
  return editorMutation(`/api/v1/cards/${encodeURIComponent(cardId)}`, "DELETE", undefined, csrfToken);
}

export function getDashboardCardSource(
  cardId: string,
  signal?: AbortSignal
): Promise<CardSource> {
  return apiRequest<CardSource>(`/api/v1/cards/${encodeURIComponent(cardId)}/source`, {
    method: "GET",
    signal
  });
}

export function updateDashboardEditorLayout(
  dashboardId: string,
  payload: UpdateEditorLayoutRequest,
  csrfToken: string
): Promise<UpdateEditorLayoutResponse> {
  return editorMutation(`/api/v1/dashboards/${encodeURIComponent(dashboardId)}/layout`, "PATCH", {
    expected_layout_version: payload.expected_layout_version,
    items: payload.items.map((item) => ({
      card_id: item.card_id,
      desktop: { ...item.desktop },
      tablet: { ...item.tablet },
      mobile: { ...item.mobile }
    }))
  }, csrfToken);
}

function editorMutation<T>(
  path: string,
  method: "DELETE" | "PATCH" | "POST",
  body: object | undefined,
  csrfToken: string
): Promise<T> {
  return apiRequest<T>(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
}

function createDashboardRequestBody(
  payload: CreateDashboardRequest
): CreateDashboardRequest {
  const body: CreateDashboardRequest = {
    title: payload.title.trim()
  };

  if (payload.description !== undefined) {
    body.description = payload.description;
  }

  if (payload.visibility_scope !== undefined) {
    body.visibility_scope = payload.visibility_scope;
  }

  if (payload.department_id !== undefined) {
    body.department_id = payload.department_id;
  }

  return body;
}

function saveCardRequestBody(payload: SaveCardRequest): SaveCardRequest {
  const body: SaveCardRequest = {
    dashboard_id: payload.dashboard_id
  };

  if (payload.title !== undefined) {
    body.title = payload.title.trim();
  }

  if (payload.description !== undefined) {
    body.description = payload.description;
  }

  if (payload.card_type !== undefined) {
    body.card_type = payload.card_type;
  }

  return body;
}

function dashboardLayoutRequestBody(
  payload: UpdateDashboardLayoutRequest
): UpdateDashboardLayoutRequest {
  return {
    items: payload.items.map((item) => ({
      card_id: item.card_id,
      position: item.position
    }))
  };
}
