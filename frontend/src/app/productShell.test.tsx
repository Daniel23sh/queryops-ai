import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authenticatedRoutes,
  backendQueryTemplate,
  demoManager,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse
} from "../test/appTestUtils";

afterEach(resetAppTestState);

describe("responsive product shell", () => {
  it("collapses the desktop sidebar and restores the stored state", async () => {
    stubViewport(false);
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );
    const firstRender = renderAppAt("/");

    const collapseButton = await screen.findByRole("button", {
      name: "Collapse sidebar"
    });
    fireEvent.click(collapseButton);

    expect(screen.getByRole("button", { name: "Expand sidebar" })).toHaveAttribute(
      "aria-expanded",
      "false"
    );
    expect(document.querySelector(".product-shell")).toHaveAttribute(
      "data-sidebar-collapsed",
      "true"
    );
    expect(localStorage.getItem("queryops-sidebar-collapsed")).toBe("true");

    firstRender.unmount();
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );
    renderAppAt("/");
    expect(
      await screen.findByRole("button", { name: "Expand sidebar" })
    ).toBeInTheDocument();
  });

  it("opens an accessible mobile drawer, locks scroll, and restores focus on Escape", async () => {
    stubViewport(true);
    installHome();
    renderAppAt("/");

    const opener = await screen.findByRole("button", { name: "Open navigation" });
    expect(opener).toHaveAttribute("aria-controls", "primary-navigation");
    expect(opener).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("dialog", { name: "Workspace" })).not.toBeInTheDocument();

    fireEvent.click(opener);
    const drawer = await screen.findByRole("dialog", { name: "Workspace" });
    expect(opener).toHaveAttribute("aria-expanded", "true");
    expect(document.body.style.overflow).toBe("hidden");
    await waitFor(() => {
      expect(within(drawer).getByRole("link", { name: "My Dashboard" })).toHaveFocus();
    });

    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Workspace" })).not.toBeInTheDocument();
      expect(document.body.style.overflow).toBe("");
      expect(opener).toHaveFocus();
    });
  });

  it("closes the mobile drawer from its backdrop and close button", async () => {
    stubViewport(true);
    installHome();
    renderAppAt("/");

    const opener = await screen.findByRole("button", { name: "Open navigation" });
    fireEvent.click(opener);
    await screen.findByRole("dialog", { name: "Workspace" });
    const backdrop = document.querySelector<HTMLButtonElement>(".navigation-backdrop");
    expect(backdrop).not.toBeNull();
    fireEvent.click(backdrop as HTMLButtonElement);
    await waitFor(() => expect(opener).toHaveFocus());

    fireEvent.click(opener);
    const drawer = await screen.findByRole("dialog", { name: "Workspace" });
    fireEvent.click(within(drawer).getByRole("button", { name: "Close navigation" }));
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("closes the mobile drawer after route selection and focuses routed content", async () => {
    stubViewport(true);
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([]),
        "GET /api/v1/query-templates": successResponse([backendQueryTemplate()])
      })
    );
    renderAppAt("/");

    fireEvent.click(await screen.findByRole("button", { name: "Open navigation" }));
    const drawer = await screen.findByRole("dialog", { name: "Workspace" });
    fireEvent.click(within(drawer).getByRole("link", { name: "Ask Data" }));

    expect(await screen.findByRole("heading", { name: "Ask Data" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Workspace" })).not.toBeInTheDocument();
    expect(document.getElementById("main-content")).toHaveFocus();
    expect(window.location.pathname).toBe("/ask");
  });

  it("closes the user menu with Escape and returns focus to its trigger", async () => {
    stubViewport(false);
    installHome();
    renderAppAt("/");

    const menuButton = await screen.findByRole("button", {
      name: "Open user menu for Demo Manager"
    });
    fireEvent.click(menuButton);
    expect(screen.getByRole("menu")).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(menuButton).toHaveFocus();
  });
});

function installHome() {
  installApiMock(
    authenticatedRoutes(demoManager, {
      "GET /api/v1/dashboards/my": successResponse([])
    })
  );
}

function stubViewport(isMobile: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: query === "(max-width: 899px)" ? isMobile : false,
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn()
    }))
  );
}
