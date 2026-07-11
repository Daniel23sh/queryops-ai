import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiDownload, downloadBlob } from "./client";
import {
  exportDashboardCardCsv,
  exportQueryRunCsv
} from "./exports";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  document.body.replaceChildren();
});

describe("CSV export API client", () => {
  it("downloads query runs through the encoded endpoint with cookies and CSRF", async () => {
    const csvBlob = new Blob(["name,count\nLicenses,3\n"], {
      type: "text/csv"
    });
    const fetchMock = stubDownloadResponse(csvBlob, {
      "Content-Disposition": 'attachment; filename="query-run.csv"',
      "Content-Type": "text/csv; charset=utf-8"
    });

    const result = await exportQueryRunCsv(
      "folder/query run",
      "csrf-token",
      { include_headers: true }
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/query-runs/folder%2Fquery%20run/export-csv",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ include_headers: true })
      })
    );
    const requestHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(requestHeaders.get("Accept")).toBe("text/csv, application/json");
    expect(requestHeaders.get("Content-Type")).toBe("application/json");
    expect(requestHeaders.get("X-CSRF-Token")).toBe("csrf-token");
    expect(result).toEqual({
      blob: csvBlob,
      filename: "query-run.csv",
      contentType: "text/csv; charset=utf-8"
    });
  });

  it("downloads dashboard cards and defaults the request body to an empty object", async () => {
    const csvBlob = new Blob(["count\n2\n"], { type: "text/csv" });
    const fetchMock = stubDownloadResponse(csvBlob, {});

    const result = await exportDashboardCardCsv(
      "folder/card id",
      "csrf-token"
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/cards/folder%2Fcard%20id/export-csv",
      expect.objectContaining({
        body: "{}",
        credentials: "include"
      })
    );
    const requestHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(requestHeaders.get("Content-Type")).toBe("application/json");
    expect(requestHeaders.get("X-CSRF-Token")).toBe("csrf-token");
    expect(result.filename).toBe("dashboard-card.csv");
    expect(result.contentType).toBe("application/octet-stream");
  });

  it("falls back safely when Content-Disposition contains no usable filename", async () => {
    const csvBlob = new Blob(["count\n2\n"]);
    stubDownloadResponse(csvBlob, {
      "Content-Disposition": 'attachment; filename="../"'
    });

    const result = await exportQueryRunCsv("query-run-id", "csrf-token");

    expect(result.filename).toBe("query-result.csv");
  });

  it("converts JSON backend failures into ApiError", async () => {
    stubErrorResponse(
      403,
      "application/json",
      {
        error: {
          code: "CSV_EXPORT_NOT_ALLOWED",
          message: "CSV export is not allowed for this resource.",
          details: { reason: "policy" },
          request_id: "request-id"
        }
      }
    );

    await expect(
      exportQueryRunCsv("query-run-id", "csrf-token")
    ).rejects.toMatchObject({
      name: "ApiError",
      code: "CSV_EXPORT_NOT_ALLOWED",
      status: 403,
      requestId: "request-id"
    });
  });

  it("uses a generic safe error for non-JSON failures", async () => {
    stubErrorResponse(500, "text/plain", "private backend details");

    try {
      await exportQueryRunCsv("query-run-id", "csrf-token");
      throw new Error("Expected export to fail");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        code: "API_ERROR",
        message: "Download request failed.",
        status: 500
      });
      expect(String(error)).not.toContain("private backend details");
    }
  });

  it("preserves Headers instances and caller-provided Accept values", async () => {
    const fetchMock = stubDownloadResponse(new Blob(["count\n2\n"]), {});

    await apiDownload("/api/v1/download", {
      headers: new Headers({
        Accept: "application/vnd.queryops.csv",
        "X-Test": "value"
      })
    });

    const requestHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers);
    expect(requestHeaders.get("Accept")).toBe("application/vnd.queryops.csv");
    expect(requestHeaders.get("X-Test")).toBe("value");
  });
});

describe("downloadBlob", () => {
  it("creates and revokes an object URL and removes the temporary anchor", () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:queryops-export");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => undefined);
    const blob = new Blob(["count\n2\n"]);

    downloadBlob({
      blob,
      filename: "query-result.csv",
      contentType: "text/csv"
    });

    expect(createObjectURL).toHaveBeenCalledWith(blob);
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:queryops-export");
    expect(document.querySelector("a[download]")).toBeNull();
  });
});

function stubDownloadResponse(blob: Blob, headers: Record<string, string>) {
  const response = {
    ok: true,
    status: 200,
    headers: new Headers(headers),
    blob: vi.fn().mockResolvedValue(blob)
  };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function stubErrorResponse(
  status: number,
  contentType: string,
  payload: unknown
) {
  const response = {
    ok: false,
    status,
    headers: new Headers({ "Content-Type": contentType }),
    json: vi.fn().mockResolvedValue(payload)
  };
  const fetchMock = vi.fn().mockResolvedValue(response);
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
