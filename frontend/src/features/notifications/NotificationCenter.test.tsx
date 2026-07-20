import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  authenticatedRoutes,
  backendNotificationList,
  demoManager,
  errorResponse,
  installApiMock,
  renderAppAt,
  resetAppTestState,
  setCsrfCookie,
  successResponse
} from "../../test/appTestUtils";
import { notificationPath } from "./NotificationCenter";

afterEach(resetAppTestState);

describe("NotificationCenter", () => {
  it("shows the exact unread badge, filters, safe links, and restores focus", async () => {
    const notifications = [notification(), notification({ id: "00000000-0000-4000-8000-000000000902", type: "unexpected", relatedEntity: { type: "unknown", id: "unsafe" } })];
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/notifications": [
        successResponse(backendNotificationList([], 2)),
        successResponse(backendNotificationList(notifications, 2)),
        successResponse(backendNotificationList([], 2)),
        successResponse(backendNotificationList(notifications, 2)),
        successResponse(backendNotificationList([], 2))
      ],
      "GET /api/v1/dashboards/my": successResponse([])
    }));
    renderAppAt("/");

    const bell = await screen.findByRole("button", { name: "Open notifications, 2 unread" });
    expect(bell).toHaveAttribute("aria-expanded", "false");
    bell.focus();
    fireEvent.click(bell);
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    expect(bell).toHaveAttribute("aria-expanded", "true");
    expect(within(drawer).getByRole("tab", { name: "All" })).toHaveAttribute("aria-selected", "true");
    expect(within(drawer).getAllByRole("link", { name: "Open related item" })).toHaveLength(1);
    expect(within(drawer).getByRole("link", { name: "Open related item" })).toHaveAttribute("href", "/actions/00000000-0000-4000-8000-000000000501");
    fireEvent.click(within(drawer).getByRole("tab", { name: "Unread" }));
    expect(within(drawer).getByRole("tab", { name: "Unread" })).toHaveAttribute("aria-selected", "true");
    await waitFor(() => expect(fetchMockUrlCount("is_read=false")).toBeGreaterThan(0));
    fireEvent.keyDown(document, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument());
    await waitFor(() => expect(bell).toHaveFocus());
  });

  it("marks one notification read with CSRF and refreshes authoritative counts", async () => {
    setCsrfCookie("csrf-token");
    const unread = notification();
    const read = { ...unread, is_read: true, read_at: "2026-07-19T14:00:00Z" };
    const fetchMock = installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/notifications": [
        successResponse(backendNotificationList([], 1)),
        successResponse(backendNotificationList([unread], 1)),
        successResponse(backendNotificationList([], 1)),
        successResponse(backendNotificationList([read], 0)),
        successResponse(backendNotificationList([], 0))
      ],
      [`POST /api/v1/notifications/${unread.id}/read`]: successResponse(read),
      "GET /api/v1/dashboards/my": successResponse([])
    }));
    renderAppAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Open notifications, 1 unread" }));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    fireEvent.click(await within(drawer).findByRole("button", { name: "Mark as read" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Open notifications, 0 unread" })).toBeInTheDocument());
    const post = fetchMock.mock.calls.find(([input]) => String(input).includes(`/${unread.id}/read`));
    expect(post?.[1]).toEqual(expect.objectContaining({ method: "POST", headers: expect.objectContaining({ "X-CSRF-Token": "csrf-token" }) }));
    expect(within(drawer).getByText("Read")).toBeInTheDocument();
  });

  it("recovers safely when a mark-all mutation fails and uses fail-closed links", async () => {
    setCsrfCookie("csrf-token");
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/notifications": [
        successResponse(backendNotificationList([], 1)),
        successResponse(backendNotificationList([notification()], 1)),
        successResponse(backendNotificationList([], 1))
      ],
      "POST /api/v1/notifications/read-all": errorResponse("INTERNAL_ERROR", 500),
      "GET /api/v1/dashboards/my": successResponse([])
    }));
    renderAppAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Open notifications, 1 unread" }));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    fireEvent.click(await within(drawer).findByRole("button", { name: "Mark all as read" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("could not be marked as read");
    expect(within(drawer).getAllByText("Unread")).toHaveLength(2);

    expect(notificationPath(notification({ type: "action_pending_approval", relatedEntity: null }))).toBe("/approvals");
    expect(notificationPath(notification({ type: "role_request_decided", relatedEntity: null }))).toBe("/profile");
    expect(notificationPath(notification({ type: "unexpected", relatedEntity: { type: "action_request", id: "unsafe" } }))).toBeNull();
  });

  it("marks all notifications read and applies the authoritative empty unread filter", async () => {
    setCsrfCookie("csrf-token");
    const unread = notification();
    const read = { ...unread, is_read: true, read_at: "2026-07-19T14:00:00Z" };
    installApiMock(authenticatedRoutes(demoManager, {
      "GET /api/v1/notifications": [
        successResponse(backendNotificationList([], 1)),
        successResponse(backendNotificationList([unread], 1)),
        successResponse(backendNotificationList([], 1)),
        successResponse(backendNotificationList([read], 0)),
        successResponse(backendNotificationList([], 0)),
        successResponse(backendNotificationList([], 0)),
        successResponse(backendNotificationList([], 0))
      ],
      "POST /api/v1/notifications/read-all": successResponse({ affected_count: 1 }),
      "GET /api/v1/dashboards/my": successResponse([])
    }));
    renderAppAt("/");
    fireEvent.click(await screen.findByRole("button", { name: "Open notifications, 1 unread" }));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    fireEvent.click(await within(drawer).findByRole("button", { name: "Mark all as read" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Open notifications, 0 unread" })).toBeInTheDocument());
    fireEvent.click(within(drawer).getByRole("tab", { name: "Unread" }));
    expect(await within(drawer).findByText("You have no unread notifications.")).toBeInTheDocument();
  });
});

function fetchMockUrlCount(fragment: string): number {
  const fetchMock = globalThis.fetch as unknown as { mock: { calls: Array<[string | URL | Request]> } };
  return fetchMock.mock.calls.filter(([input]) => String(input).includes(fragment)).length;
}

function notification({
  id = "00000000-0000-4000-8000-000000000901",
  type = "action_completed",
  relatedEntity = { type: "action_request", id: "00000000-0000-4000-8000-000000000501" } as { type: string; id: string } | null
} = {}) {
  return {
    id,
    type,
    title: "Action workflow updated",
    body: "A governed action has a new status.",
    is_read: false,
    related_entity: relatedEntity,
    created_at: "2026-07-19T13:00:00Z",
    read_at: null
  };
}
