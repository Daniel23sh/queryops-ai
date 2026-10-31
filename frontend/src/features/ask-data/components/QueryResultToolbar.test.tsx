import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { downloadBlob } from "../../../api/client";
import { exportQueryRunCsv } from "../../../api/exports";
import type { DeliveryCompleteness } from "../../../lib/resultDelivery";
import type { CurrentQueryResult } from "../types";
import { QueryResultToolbar } from "./QueryResultToolbar";

vi.mock("../../../api/exports", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../api/exports")>(),
  exportQueryRunCsv: vi.fn()
}));
vi.mock("../../../api/client", async (importOriginal) => ({
  ...await importOriginal<typeof import("../../../api/client")>(),
  downloadBlob: vi.fn()
}));
afterEach(() => { vi.clearAllMocks(); });

describe("QueryResultToolbar export delivery", () => {
  it.each([
    ["complete", "CSV export downloaded."],
    ["safety_limited", "Partial CSV downloaded."],
    ["unknown", "Delivery completeness could not be established."],
    [undefined, "Delivery completeness could not be established."]
  ] as const)("uses fresh export state (%s) rather than source completeness", async (state, message) => {
    const download = {
      blob: new Blob(["item\nDelivered\n"]), filename: "export.csv", contentType: "text/csv",
      deliveryCompleteness: state as DeliveryCompleteness | undefined
    };
    vi.mocked(exportQueryRunCsv).mockResolvedValue(download);
    render(<QueryResultToolbar canExport canSave={false} csrfToken="csrf" current={currentResult()} />);
    fireEvent.click(screen.getByRole("button", { name: "Export CSV" }));
    await waitFor(() => expect(screen.getByText(new RegExp(message))).toBeInTheDocument());
    expect(downloadBlob).toHaveBeenCalledWith(download);
  });
});

function currentResult(): CurrentQueryResult {
  return {
    question: "A bounded result", originalQuestion: "A bounded result", clarificationResponse: null,
    generation: 1,
    result: {
      query_run_id: "run", status: "succeeded", columns: ["item"], rows: [{ item: "Delivered" }],
      row_count: 1, duration_ms: 1, truncated: false, message: "Done", warnings: [],
      clarification_required: false, suggested_actions: [],
      metadata: { execution: { status: "succeeded", error_code: null, row_count: 1, duration_ms: 1, truncated: false, delivery_completeness: "complete" } }
    }
  };
}
