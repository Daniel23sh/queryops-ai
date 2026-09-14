import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { CurrentQueryResult } from "../types";
import { ResultDetailsDisclosure } from "./ResultDetailsDisclosure";

describe("ResultDetailsDisclosure", () => {
  it("discloses safety-limited delivery even when truncated is false", () => {
    const current: CurrentQueryResult = {
      question: "Show all active assignments",
      originalQuestion: "Show all active assignments",
      clarificationResponse: null,
      generation: 1,
      result: {
        query_run_id: "run-1",
        status: "succeeded",
        columns: ["id"],
        rows: [{ id: "one" }],
        row_count: 100,
        duration_ms: 2,
        truncated: false,
        message: "Query completed successfully.",
        warnings: [],
        clarification_required: false,
        metadata: {
          execution: {
            status: "succeeded",
            error_code: null,
            row_count: 100,
            duration_ms: 2,
            truncated: false,
            delivery_completeness: "safety_limited",
          },
        },
        suggested_actions: [],
      },
    };

    const view = render(
      <ResultDetailsDisclosure canViewTechnicalDetails={false} current={current} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Result details" }));

    expect(
      screen.getByText(
        "Delivery is partial because the governed row limit may have applied.",
      ),
    ).toBeInTheDocument();

    view.unmount();
    current.result.metadata.execution = undefined;
    render(
      <ResultDetailsDisclosure canViewTechnicalDetails={false} current={current} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Result details" }));
    expect(
      screen.getByText("Delivery completeness could not be established."),
    ).toBeInTheDocument();
  });
});
