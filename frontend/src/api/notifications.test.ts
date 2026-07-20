import { afterEach, describe, expect, it, vi } from "vitest";

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead
} from "./notifications";

afterEach(() => vi.unstubAllGlobals());

describe("notifications API client", () => {
  it("serializes filters, forwards AbortSignal, and URL-encodes notification IDs", async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(apiResponse()));
    vi.stubGlobal("fetch", fetchMock);
    const controller = new AbortController();

    await listNotifications({ isRead: false, limit: 10, offset: 20 }, controller.signal);
    await markNotificationRead("notification/id", "csrf");
    await markAllNotificationsRead("csrf");

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "http://localhost:8000/api/v1/notifications?limit=10&offset=20&is_read=false",
      expect.objectContaining({ method: "GET", signal: controller.signal })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "http://localhost:8000/api/v1/notifications/notification%2Fid/read",
      expect.objectContaining({
        method: "POST",
        headers: expect.objectContaining({ "X-CSRF-Token": "csrf" })
      })
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      "http://localhost:8000/api/v1/notifications/read-all",
      expect.objectContaining({ method: "POST" })
    );
  });
});

function apiResponse() {
  return new Response(JSON.stringify({ data: {} }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}
