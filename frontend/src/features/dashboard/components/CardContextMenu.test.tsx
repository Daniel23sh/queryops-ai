import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CardContextMenu } from "./CardContextMenu";
import { DashboardActionMenu } from "./DashboardActionMenu";

describe("editor context menus", () => {
  it("shows only permitted View actions and supports right-click positioning", () => {
    const onSelect = vi.fn();
    render(<CardContextMenu canExport canRefresh canViewSource cardTitle="Open tickets" editMode={false} onSelect={onSelect} />);
    const trigger = screen.getByRole("button", { name: "Card actions for Open tickets" });

    fireEvent.contextMenu(trigger, { clientX: 40, clientY: 60 });

    expect(screen.getByRole("menu").parentElement).toBe(document.body);
    expect(screen.getByRole("menuitem", { name: "Refresh" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Export CSV" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "View source" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Rename" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: "Refresh" }));
    expect(onSelect).toHaveBeenCalledWith("refresh");
    expect(trigger).toHaveFocus();
  });

  it("supports arrow navigation, Escape, focus restoration, and Edit-only actions", async () => {
    render(<CardContextMenu canExport={false} canRefresh canViewSource={false} cardTitle="Devices" editMode onSelect={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Card actions for Devices" });
    fireEvent.click(trigger);
    const refresh = screen.getByRole("menuitem", { name: "Refresh" });
    await waitFor(() => expect(refresh).toHaveFocus());
    fireEvent.keyDown(screen.getByRole("menu"), { key: "ArrowDown" });
    expect(screen.getByRole("menuitem", { name: "Change visualization" })).toHaveFocus();
    expect(screen.getByRole("menuitem", { name: "Remove" })).toHaveClass("dashboard-card-menu__danger");
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("provides keyboard navigation for the dashboard action menu", async () => {
    render(<DashboardActionMenu canDuplicate canManage onSelect={vi.fn()} />);
    const trigger = screen.getByRole("button", { name: "Dashboard actions" });
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.getByRole("menuitem", { name: "Rename dashboard" })).toHaveFocus());
    fireEvent.keyDown(screen.getByRole("menu"), { key: "End" });
    expect(screen.getByRole("menuitem", { name: "Archive dashboard" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
    expect(trigger).toHaveFocus();
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("menuitem", { name: "Rename dashboard" }));
    expect(trigger).toHaveFocus();
  });
});
