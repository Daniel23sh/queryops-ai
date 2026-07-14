import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { backendDashboardLibraryItem, resetAppTestState } from "../../../test/appTestUtils";
import type { DashboardLibraryItem } from "../types";
import { DashboardLibrary, filterAndSortDashboards } from "./DashboardLibrary";

afterEach(resetAppTestState);

describe("DashboardLibrary", () => {
  it("groups Owned and Shared dashboards, filters, searches, and sorts locally", () => {
    const dashboards = [
      item({ id: "z", title: "Zulu", updatedAt: "2026-07-10T00:00:00Z" }),
      item({
        id: "a",
        title: "Alpha",
        relationship: "shared",
        description: "Contains compliance detail",
        updatedAt: "2026-07-12T00:00:00Z"
      }),
      item({ id: "b", title: "Bravo", createdAt: "2026-07-13T00:00:00Z" })
    ];
    renderLibrary(dashboards);

    expect(screen.getByRole("region", { name: "Owned by me" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Shared with me" })).toBeInTheDocument();
    expect(screen.getByText("3 dashboards found")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter dashboards"), {
      target: { value: "shared" }
    });
    expect(screen.getByRole("button", { name: "Preview dashboard Alpha" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Preview dashboard Zulu" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter dashboards"), {
      target: { value: "all" }
    });
    fireEvent.change(screen.getByLabelText("Search dashboards"), {
      target: { value: "  compliance  " }
    });
    expect(screen.getByRole("button", { name: "Preview dashboard Alpha" })).toBeInTheDocument();
    expect(screen.getByText("1 dashboard found")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search dashboards"), {
      target: { value: "" }
    });
    fireEvent.change(screen.getByLabelText("Filter dashboards"), {
      target: { value: "owned" }
    });
    fireEvent.change(screen.getByLabelText("Sort dashboards"), {
      target: { value: "name" }
    });
    expect(previewNames()).toEqual(["Bravo", "Zulu"]);
  });

  it("shows one concise empty state and no fake metric values", () => {
    renderLibrary([]);

    expect(screen.getByText("No dashboards are available yet.")).toBeInTheDocument();
    expect(screen.queryByText(/42|93%|\$1/)).not.toBeInTheDocument();
  });

  it("does not pair an error alert with the empty-library state", () => {
    renderLibrary([], false, "error");

    expect(screen.getByRole("alert")).toHaveTextContent(
      "Dashboard library could not be loaded."
    );
    expect(
      screen.queryByText("No dashboards are available yet.")
    ).not.toBeInTheDocument();
  });

  it("opens a metadata-only modal, traps focus, closes, and navigates", () => {
    const dashboard = item({ id: "open-me", title: "Open me", cardCount: 6 });
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    renderLibrary([dashboard], true);
    const opener = screen.getByRole("button", { name: "Preview dashboard Open me" });
    opener.focus();
    fireEvent.click(opener);

    const dialog = screen.getByRole("dialog", { name: "Open me" });
    expect(dialog).toBeInTheDocument();
    expect(document.body.style.overflow).toBe("hidden");
    expect(within(dialog).getAllByRole("article")).toHaveLength(4);
    expect(within(dialog).queryByText(/SELECT|generated_sql|config/i)).not.toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    const closeButton = screen.getByRole("button", { name: "Close dashboard preview" });
    const openButton = screen.getByRole("button", { name: "Open dashboard" });
    expect(closeButton).toHaveFocus();
    openButton.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(closeButton).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(openButton).toHaveFocus();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");
    expect(opener).toHaveFocus();

    fireEvent.click(opener);
    fireEvent.click(screen.getByRole("button", { name: "Open dashboard" }));
    expect(screen.getByTestId("dashboard-location")).toHaveTextContent("open-me");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("closes from the backdrop and retains mobile dialog hooks", () => {
    renderLibrary([item({ title: "Backdrop" })]);
    fireEvent.click(screen.getByRole("button", { name: "Preview dashboard Backdrop" }));
    const dialog = screen.getByRole("dialog", { name: "Backdrop" });
    expect(dialog).toHaveClass("dashboard-preview-dialog");
    const backdrop = dialog.parentElement;
    expect(backdrop).toHaveClass("dashboard-dialog-backdrop");
    fireEvent.mouseDown(backdrop as HTMLElement);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});

describe("filterAndSortDashboards", () => {
  it("sorts Created newest first with stable title and id fallbacks", () => {
    const dashboards = [
      item({ id: "b", title: "Same", createdAt: "2026-07-12T00:00:00Z" }),
      item({ id: "a", title: "Same", createdAt: "2026-07-12T00:00:00Z" }),
      item({ id: "new", title: "Newest", createdAt: "2026-07-13T00:00:00Z" })
    ];
    expect(
      filterAndSortDashboards(dashboards, "all", "", "created").map(
        (dashboard) => dashboard.id
      )
    ).toEqual(["new", "a", "b"]);
  });
});

function renderLibrary(
  dashboards: DashboardLibraryItem[],
  withRoute = false,
  status: "error" | "success" = "success"
) {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route
          path="/"
          element={
            <DashboardLibrary
              canCreate={false}
              dashboards={dashboards}
              errorMessage="Dashboard library could not be loaded."
              onCreate={vi.fn()}
              onReload={vi.fn().mockResolvedValue(undefined)}
              status={status}
            />
          }
        />
        {withRoute ? (
          <Route
            path="/dashboards/:dashboardId"
            element={<span data-testid="dashboard-location">open-me</span>}
          />
        ) : null}
      </Routes>
    </MemoryRouter>
  );
}

function item(
  overrides: Parameters<typeof backendDashboardLibraryItem>[0] = {}
): DashboardLibraryItem {
  return backendDashboardLibraryItem(overrides) as DashboardLibraryItem;
}

function previewNames(): string[] {
  return screen
    .getAllByRole("button", { name: /Preview dashboard/ })
    .map((button) => button.getAttribute("aria-label")?.replace("Preview dashboard ", "") ?? "");
}
