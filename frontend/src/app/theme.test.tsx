import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { initializeTheme } from "./theme";
import {
  authenticatedRoutes,
  demoManager,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  successResponse
} from "../test/appTestUtils";

afterEach(resetAppTestState);

describe("dark-first theme", () => {
  it("uses dark synchronously when no preference is stored", () => {
    stubSystemTheme(false);

    expect(initializeTheme()).toBe("dark");
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("queryops-theme")).toBeNull();
  });

  it.each(["light", "dark"] as const)(
    "uses a stored %s preference during bootstrap",
    (storedTheme) => {
      localStorage.setItem("queryops-theme", storedTheme);
      stubSystemTheme(storedTheme !== "dark");

      expect(initializeTheme()).toBe(storedTheme);
      expect(document.documentElement).toHaveAttribute("data-theme", storedTheme);
      if (storedTheme === "dark") {
        expect(document.documentElement).toHaveClass("dark");
      } else {
        expect(document.documentElement).not.toHaveClass("dark");
      }
    }
  );

  it("uses the same persisted theme and toggle on login", async () => {
    installApiMock({
      "GET /api/v1/auth/me": errorResponse("UNAUTHORIZED", 401)
    });

    renderAppAt("/login");
    await screen.findByRole("heading", { name: "Choose a demo profile" });
    await waitFor(() => {
      expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    });

    fireEvent.click(screen.getByRole("button", { name: "Switch to light mode" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "light");
    expect(document.documentElement).not.toHaveClass("dark");
    expect(localStorage.getItem("queryops-theme")).toBe("light");
  });

  it("keeps the workspace shortcut synchronized with storage and the DOM", async () => {
    localStorage.setItem("queryops-theme", "light");
    installApiMock(
      authenticatedRoutes(demoManager, {
        "GET /api/v1/dashboards/my": successResponse([])
      })
    );

    renderAppAt("/");
    await screen.findByRole("region", { name: "My Dashboard" });
    expect(document.documentElement).toHaveAttribute("data-theme", "light");

    fireEvent.click(screen.getByRole("button", { name: "Switch to dark mode" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    expect(document.documentElement).toHaveClass("dark");
    expect(localStorage.getItem("queryops-theme")).toBe("dark");
  });
});

function stubSystemTheme(prefersDark: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: prefersDark,
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
