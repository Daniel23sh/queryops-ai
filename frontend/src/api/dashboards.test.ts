import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createDashboard,
  getDashboardCatalog,
  getMyDashboards,
  refreshDashboardCard,
  saveQueryRunAsCard,
  updateMyDashboardLayout
} from "./dashboards";
import type {
  CreateDashboardRequest,
  Dashboard,
  DashboardCard,
  SaveCardRequest,
  UpdateDashboardLayoutRequest
} from "../features/dashboard/types";

const backendCard = {
  id: "card-id",
  dashboard_id: "dashboard-id",
  saved_query_id: "saved-query-id",
  title: "Unused licenses",
  description: "Saved card description",
  card_type: "table",
  position: 1,
  layout: { w: 4 },
  config: { columns: ["product_name"] },
  created_at: "2026-07-04T12:00:00Z",
  updated_at: "2026-07-04T12:00:00Z"
} satisfies DashboardCard;

const backendDashboard = {
  id: "dashboard-id",
  title: "IT Operations",
  description: "Department dashboard",
  visibility_scope: "department",
  department_id: "department-id",
  is_archived: false,
  created_at: "2026-07-04T12:00:00Z",
  updated_at: "2026-07-04T12:00:00Z",
  cards: [backendCard]
} satisfies Dashboard;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("dashboards API client", () => {
  it("gets the dashboard catalog with cookies included", async () => {
    const fetchMock = stubFetch({
      data: [backendDashboard],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    const result = await getDashboardCatalog();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards/catalog",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toEqual([backendDashboard]);
  });

  it("gets my dashboards with cookies included", async () => {
    const fetchMock = stubFetch({
      data: [backendDashboard],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    const result = await getMyDashboards();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards/my",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toEqual([backendDashboard]);
  });

  it("creates dashboards with a JSON body and CSRF header", async () => {
    const fetchMock = stubFetch({
      data: backendDashboard,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    const result = await createDashboard(
      {
        title: " IT Operations ",
        description: "Department dashboard",
        visibility_scope: "department",
        department_id: "department-id"
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          title: "IT Operations",
          description: "Department dashboard",
          visibility_scope: "department",
          department_id: "department-id"
        })
      }
    );
    expect(result).toEqual(backendDashboard);
  });

  it("does not send undefined optional dashboard fields", async () => {
    const fetchMock = stubFetch({
      data: backendDashboard,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    await createDashboard(
      {
        title: "Personal dashboard",
        description: undefined,
        visibility_scope: undefined,
        department_id: undefined
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards",
      expect.objectContaining({
        body: JSON.stringify({
          title: "Personal dashboard"
        })
      })
    );
  });

  it("saves query runs as cards with an encoded query run id and CSRF header", async () => {
    const fetchMock = stubFetch({
      data: backendCard,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    const result = await saveQueryRunAsCard(
      "folder/query run id",
      {
        dashboard_id: "dashboard-id",
        title: " Saved insight ",
        description: "Card description",
        card_type: "table"
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-runs/folder%2Fquery%20run%20id/save-card",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          dashboard_id: "dashboard-id",
          title: "Saved insight",
          description: "Card description",
          card_type: "table"
        })
      }
    );
    expect(result).toEqual(backendCard);
  });

  it("does not send undefined optional save-card fields", async () => {
    const fetchMock = stubFetch({
      data: backendCard,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-04T12:00:00Z"
      }
    });

    await saveQueryRunAsCard(
      "query-run-id",
      {
        dashboard_id: "dashboard-id",
        title: undefined,
        description: undefined,
        card_type: undefined
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-runs/query-run-id/save-card",
      expect.objectContaining({
        body: JSON.stringify({
          dashboard_id: "dashboard-id"
        })
      })
    );
  });

  it("refreshes an encoded dashboard card with CSRF and an empty JSON body", async () => {
    const refreshResult = {
      card_id: "card-id",
      dashboard_id: "dashboard-id",
      saved_query_id: "saved-query-id",
      query_run_id: "refresh-run-id",
      status: "succeeded" as const,
      columns: ["product_name"],
      rows: [{ product_name: "Jira" }],
      row_count: 1,
      duration_ms: 8,
      truncated: false,
      refreshed_at: "2026-07-11T15:00:00Z",
      message: "Dashboard card refreshed successfully.",
      warnings: []
    };
    const fetchMock = stubFetch({ data: refreshResult });

    const result = await refreshDashboardCard("folder/card id", "csrf-token");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/cards/folder%2Fcard%20id/refresh",
      {
        method: "POST",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: "{}"
      }
    );
    expect(result).toEqual(refreshResult);
  });

  it("persists a full zero-based card order with PATCH and CSRF", async () => {
    const updatedDashboard = {
      ...backendDashboard,
      cards: [
        { ...backendCard, id: "second-card", position: 0 },
        { ...backendCard, id: "first-card", position: 1 }
      ]
    };
    const fetchMock = stubFetch({ data: updatedDashboard });

    const result = await updateMyDashboardLayout(
      {
        items: [
          { card_id: "second-card", position: 0 },
          { card_id: "first-card", position: 1 }
        ]
      },
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/dashboards/my/layout",
      {
        method: "PATCH",
        credentials: "include",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": "csrf-token"
        },
        body: JSON.stringify({
          items: [
            { card_id: "second-card", position: 0 },
            { card_id: "first-card", position: 1 }
          ]
        })
      }
    );
    expect(result).toEqual(updatedDashboard);
  });

  it("preserves the dashboard layout conflict code", async () => {
    stubFetch(
      {
        error: {
          code: "DASHBOARD_LAYOUT_CONFLICT",
          message: "Dashboard cards changed. Reload the dashboard and try again."
        }
      },
      { ok: false, status: 409 }
    );

    await expect(
      updateMyDashboardLayout(
        { items: [{ card_id: "card-id", position: 0 }] },
        "csrf-token"
      )
    ).rejects.toMatchObject({
      code: "DASHBOARD_LAYOUT_CONFLICT",
      status: 409
    });
  });

  it("exports dashboard request types that compile with backend field names", () => {
    const createPayload: CreateDashboardRequest = {
      title: "Personal dashboard",
      visibility_scope: "personal"
    };
    const savePayload: SaveCardRequest = {
      dashboard_id: "dashboard-id",
      card_type: "table"
    };
    const layoutPayload: UpdateDashboardLayoutRequest = {
      items: [{ card_id: "card-id", position: 0 }]
    };

    expect(createPayload.visibility_scope).toBe("personal");
    expect(savePayload.card_type).toBe("table");
    expect(layoutPayload.items[0].position).toBe(0);
  });
});

function stubFetch(
  payload: unknown,
  options: { ok?: boolean; status?: number } = {}
) {
  const response = {
    ok: options.ok ?? true,
    status: options.status ?? 200,
    json: vi.fn().mockResolvedValue(payload)
  };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
