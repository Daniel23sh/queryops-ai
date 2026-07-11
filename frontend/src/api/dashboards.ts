import { apiRequest } from "./client";
import type {
  CreateDashboardRequest,
  Dashboard,
  DashboardCard,
  DashboardCardRefreshResult,
  SaveCardRequest
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
