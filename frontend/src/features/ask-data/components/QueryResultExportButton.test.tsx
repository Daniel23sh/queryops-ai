import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, downloadBlob } from "../../../api/client";
import { exportQueryRunCsv } from "../../../api/exports";
import type { AuthUser, PermissionKey, Role } from "../../../auth/types";
import type { QueryRunState } from "../types";
import { QueryResultExportButton } from "./QueryResultExportButton";

vi.mock("../../../api/exports", () => ({
  exportQueryRunCsv: vi.fn()
}));

vi.mock("../../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../../api/client")>();
  return {
    ...actual,
    downloadBlob: vi.fn()
  };
});

const exportQueryRunCsvMock = vi.mocked(exportQueryRunCsv);
const downloadBlobMock = vi.mocked(downloadBlob);

afterEach(() => {
  vi.clearAllMocks();
});

describe("QueryResultExportButton", () => {
  it.each([
    ["analyst", "Analyst"],
    ["admin", "Admin"]
  ] as const)("shows Export CSV for an authorized %s", (role, label) => {
    renderExport({ user: authUser(role, ["can_export_results"]) });

    expect(screen.getByRole("button", { name: "Export CSV" })).toBeEnabled();
    expect(screen.getByText(/current access scope/i)).toBeInTheDocument();
    expect(screen.getByText(/exports are audited/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Query result export")).toBeInTheDocument();
    expect(label).toBeTruthy();
  });

  it.each(["user", "manager"] as const)(
    "does not show export for a %s without export permission",
    (role) => {
      renderExport({ user: authUser(role, []) });

      expect(
        screen.queryByRole("button", { name: "Export CSV" })
      ).not.toBeInTheDocument();
    }
  );

  it("disables export when the CSRF token is missing", () => {
    renderExport({ csrfToken: null });

    expect(screen.getByRole("button", { name: "Export CSV" })).toBeDisabled();
    expect(screen.getByText(/refresh your session/i)).toBeInTheDocument();
  });

  it.each([
    [{ status: "error", message: "Query failed." } as QueryRunState],
    [successState({ clarification_required: true })],
    [successState({ query_run_id: null })],
    [successState({ status: "failed" })]
  ])("does not show export for a non-exportable query state", (queryRunState) => {
    renderExport({ queryRunState });

    expect(
      screen.queryByRole("button", { name: "Export CSV" })
    ).not.toBeInTheDocument();
  });

  it("downloads the successful query run with headers enabled", async () => {
    const download = {
      blob: new Blob(["count\n2\n"]),
      filename: "query-run.csv",
      contentType: "text/csv"
    };
    exportQueryRunCsvMock.mockResolvedValue(download);
    renderExport();

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(exportQueryRunCsvMock).toHaveBeenCalledWith(
      "query-run-id",
      "csrf-token",
      { include_headers: true }
    );
    await waitFor(() => expect(downloadBlobMock).toHaveBeenCalledWith(download));
    expect(screen.getByRole("status")).toHaveTextContent(
      "CSV export downloaded."
    );
  });

  it("shows loading state and blocks duplicate clicks", async () => {
    let resolveExport: (value: {
      blob: Blob;
      filename: string;
      contentType: string;
    }) => void = () => undefined;
    exportQueryRunCsvMock.mockReturnValue(
      new Promise((resolve) => {
        resolveExport = resolve;
      })
    );
    renderExport();

    const button = screen.getByRole("button", { name: "Export CSV" });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(
      screen.getByRole("button", { name: "Preparing CSV export..." })
    ).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent(
      "Preparing CSV export..."
    );
    expect(exportQueryRunCsvMock).toHaveBeenCalledTimes(1);

    resolveExport({
      blob: new Blob(["count\n2\n"]),
      filename: "query-run.csv",
      contentType: "text/csv"
    });
    await waitFor(() => expect(downloadBlobMock).toHaveBeenCalledOnce());
  });

  it("shows safe permission errors while leaving the result visible", async () => {
    exportQueryRunCsvMock.mockRejectedValue(
      new ApiError({
        code: "CSV_EXPORT_NOT_ALLOWED",
        message: "Internal policy details",
        status: 403
      })
    );
    render(
      <>
        <p>Existing successful result</p>
        <QueryResultExportButton
          csrfToken="csrf-token"
          queryRunState={successState()}
          user={authUser("analyst", ["can_export_results"])}
        />
      </>
    );

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This result cannot be exported with your current permissions."
    );
    expect(screen.queryByText("Internal policy details")).not.toBeInTheDocument();
    expect(screen.getByText("Existing successful result")).toBeInTheDocument();
    expect(screen.queryByText(/SELECT /i)).not.toBeInTheDocument();
  });

  it("shows a safe generic message for other failures", async () => {
    exportQueryRunCsvMock.mockRejectedValue(new Error("private network detail"));
    renderExport();

    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "CSV export could not be prepared. Try again."
    );
    expect(screen.queryByText("private network detail")).not.toBeInTheDocument();
  });
});

function renderExport({
  csrfToken = "csrf-token",
  queryRunState = successState(),
  user = authUser("analyst", ["can_export_results"])
}: {
  csrfToken?: string | null;
  queryRunState?: QueryRunState;
  user?: AuthUser;
} = {}) {
  return render(
    <QueryResultExportButton
      csrfToken={csrfToken}
      queryRunState={queryRunState}
      user={user}
    />
  );
}

function successState(
  overrides: Partial<Extract<QueryRunState, { status: "success" }>["result"]> = {}
): QueryRunState {
  return {
    status: "success",
    question: "Show unused licenses.",
    result: {
      query_run_id: "query-run-id",
      status: "succeeded",
      columns: ["count"],
      rows: [{ count: 2 }],
      row_count: 1,
      duration_ms: 8,
      truncated: false,
      message: "Query completed.",
      warnings: [],
      clarification_required: false,
      metadata: {},
      ...overrides
    }
  };
}

function authUser(role: Role, permissions: PermissionKey[]): AuthUser {
  return {
    id: `${role}-id`,
    email: `${role}@queryops.local`,
    fullName: role,
    role,
    departmentId: "department-id",
    department: { id: "department-id", name: "IT" },
    scopes: [],
    status: "active",
    permissions,
    authMode: "demo"
  };
}
