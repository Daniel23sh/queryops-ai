import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./client";
import { getQueryTemplate, listQueryTemplates } from "./queryTemplates";

const backendTemplate = {
  id: "unused_licenses_by_department",
  title: "Unused licenses",
  description: "Find unused paid licenses.",
  domain: "it_operations",
  category: "Licenses",
  natural_language_question: "Show unused paid licenses in my department.",
  parameters: [
    {
      name: "unused_days",
      data_type: "integer",
      description: "Number of days without license usage.",
      required: false,
      default: 60
    }
  ],
  scope_type: "department",
  required_permission: "can_query_scoped_data"
};

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("query templates API client", () => {
  it("lists query templates with cookies included", async () => {
    const fetchMock = stubFetch({
      data: [backendTemplate],
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    const result = await listQueryTemplates();

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-templates",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toEqual([backendTemplate]);
  });

  it("gets query template details with an encoded template id", async () => {
    const fetchMock = stubFetch({
      data: backendTemplate,
      meta: {
        request_id: "request-id",
        timestamp: "2026-07-02T12:00:00Z"
      }
    });

    const result = await getQueryTemplate("folder/template id");

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-templates/folder%2Ftemplate%20id",
      {
        method: "GET",
        credentials: "include",
        headers: {
          Accept: "application/json"
        }
      }
    );
    expect(result).toEqual(backendTemplate);
  });

  it("surfaces API errors through the shared ApiError type", async () => {
    stubFetch(
      {
        error: {
          code: "QUERY_TEMPLATE_NOT_FOUND",
          message: "Query template was not found.",
          details: {},
          request_id: "request-id"
        }
      },
      { ok: false, status: 404 }
    );

    try {
      await getQueryTemplate("missing-template");
      throw new Error("Expected getQueryTemplate to reject");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        code: "QUERY_TEMPLATE_NOT_FOUND",
        message: "Query template was not found.",
        status: 404
      });
    }
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
