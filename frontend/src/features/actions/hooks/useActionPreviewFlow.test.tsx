import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createActionPreview, submitActionRequest } from "../../../api/actions";
import { backendActionDetail } from "../../../test/appTestUtils";
import type { ActionResolution } from "../types";
import { useActionPreviewFlow } from "./useActionPreviewFlow";

vi.mock("../../../api/actions", () => ({ createActionPreview: vi.fn(), submitActionRequest: vi.fn() }));
afterEach(() => vi.clearAllMocks());

describe("useActionPreviewFlow", () => {
  it("shows a safe session error without starting a preview request", async () => {
    render(<MemoryRouter><Harness csrfToken={null} /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: "Open" }));

    expect(await screen.findByText("preview-error")).toBeInTheDocument();
    expect(screen.getByText(/refresh your session/i)).toBeInTheDocument();
    expect(createActionPreview).not.toHaveBeenCalled();
  });

  it("prevents duplicate previews and ignores a stale response after the query generation changes", async () => {
    const deferred = promiseController<ReturnType<typeof backendActionDetail>>();
    vi.mocked(createActionPreview).mockReturnValue(deferred.promise as never);
    render(<MemoryRouter><Harness /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    expect(createActionPreview).toHaveBeenCalledOnce();
    expect(screen.getByText("creating")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "New query" }));
    await waitFor(() => expect(screen.getByText("closed")).toBeInTheDocument());
    deferred.resolve(backendActionDetail({ status: "draft_preview" }));
    await Promise.resolve();
    expect(screen.getByText("closed")).toBeInTheDocument();
  });

  it("prevents duplicate submits and does not navigate when a newer query wins", async () => {
    vi.mocked(createActionPreview).mockResolvedValue(backendActionDetail({ status: "draft_preview" }) as never);
    const deferred = promiseController<ReturnType<typeof backendActionDetail>>();
    vi.mocked(submitActionRequest).mockReturnValue(deferred.promise as never);
    render(<MemoryRouter initialEntries={["/ask"]}><Harness /></MemoryRouter>);

    fireEvent.click(screen.getByRole("button", { name: "Open" }));
    await screen.findByText("ready");
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    expect(submitActionRequest).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: "New query" }));
    deferred.resolve(backendActionDetail());
    await Promise.resolve();
    expect(screen.getByTestId("path")).toHaveTextContent("/ask");
  });
});

function Harness({ csrfToken = "csrf" }: { csrfToken?: string | null }) {
  const [generation, setGeneration] = useState(1);
  const flow = useActionPreviewFlow({ csrfToken, sourceGeneration: generation });
  const location = useLocation();
  return <><button onClick={() => void flow.openPreview(resolution)} type="button">Open</button><button onClick={() => setGeneration((value) => value + 1)} type="button">New query</button><button onClick={() => void flow.submit()} type="button">Submit</button><span>{flow.flow?.phase ?? "closed"}</span>{flow.flow?.error ? <span>{flow.flow.error}</span> : null}<span data-testid="path">{location.pathname}</span></>;
}

const resolution: Extract<ActionResolution, { status: "available" }> = {
  status: "available",
  suggestion: {
    action_type: "reclaim_unused_license",
    label: "Preview license reclaim",
    selector_kind: "license_assignment",
    result_identifier_column: "id"
  },
  targetCount: 1,
  previewRequest: {
    action_type: "reclaim_unused_license",
    source_query_run_id: "00000000-0000-4000-8000-000000000401",
    scope_id: "00000000-0000-4000-8000-000000000202",
    reason: "Request approval safely.",
    license_assignment_ids: ["00000000-0000-4000-8000-000000000601"]
  }
};

function promiseController<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((complete) => { resolve = complete; });
  return { promise, resolve };
}
