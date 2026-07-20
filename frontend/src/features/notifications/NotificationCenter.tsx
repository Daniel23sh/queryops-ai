import { Bell, CheckCheck, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { Link } from "react-router-dom";

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead
} from "../../api/notifications";
import { AccessibleOverlay } from "../../components/ui/AccessibleOverlay";
import { formatActionDate } from "../actions/presentation";
import { useWorkflowActivity } from "../activity/WorkflowActivityProvider";
import type { NotificationList, WorkflowNotification } from "./types";

const PAGE_SIZE = 10;
type NotificationFilter = "all" | "unread";

export function NotificationCenter({ csrfToken }: { csrfToken: string | null }) {
  const activity = useWorkflowActivity();
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={triggerRef}
        aria-controls="notification-center"
        aria-expanded={open}
        aria-label={bellLabel(activity.unreadNotificationCount)}
        className="icon-button relative"
        onClick={() => setOpen(true)}
        type="button"
      >
        <Bell aria-hidden="true" size={20} />
        {activity.unreadNotificationCount !== null && activity.unreadNotificationCount > 0 ? (
          <span className="absolute -right-1 -top-1 inline-flex min-h-5 min-w-5 items-center justify-center rounded-full bg-status-danger px-1 text-[10px] font-bold text-white" aria-hidden="true">
            {activity.unreadNotificationCount > 99 ? "99+" : activity.unreadNotificationCount}
          </span>
        ) : null}
      </button>
      {open ? (
        <NotificationDrawer
          csrfToken={csrfToken}
          onClose={() => setOpen(false)}
          returnFocusRef={triggerRef}
        />
      ) : null}
    </>
  );
}

function NotificationDrawer({ csrfToken, onClose, returnFocusRef }: { csrfToken: string | null; onClose: () => void; returnFocusRef: RefObject<HTMLElement> }) {
  const activity = useWorkflowActivity();
  const [filter, setFilter] = useState<NotificationFilter>("all");
  const [page, setPage] = useState(0);
  const [data, setData] = useState<NotificationList | null>(null);
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [mutationId, setMutationId] = useState<string | "all" | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const requestRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestRef.current?.abort();
    const controller = new AbortController();
    requestRef.current = controller;
    setStatus("loading");
    try {
      const result = await listNotifications(
        { isRead: filter === "unread" ? false : undefined, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
        controller.signal
      );
      if (controller.signal.aborted) return;
      setData(result);
      setStatus("success");
    } catch {
      if (controller.signal.aborted) return;
      setStatus("error");
    }
  }, [filter, page]);

  useEffect(() => {
    void Promise.allSettled([load(), activity.refreshNotifications()]);
    return () => requestRef.current?.abort();
  }, [load]);

  async function markOne(notification: WorkflowNotification) {
    if (mutationId || notification.is_read) return;
    if (!csrfToken) {
      setMutationError("Your session is missing a CSRF token. Sign in again, then retry.");
      return;
    }
    setMutationId(notification.id);
    setMutationError(null);
    try {
      await markNotificationRead(notification.id, csrfToken);
      await Promise.allSettled([load(), activity.refreshNotifications()]);
    } catch {
      setMutationError("The notification could not be marked as read. Try again.");
    } finally {
      setMutationId(null);
    }
  }

  async function markAll() {
    if (mutationId) return;
    if (!csrfToken) {
      setMutationError("Your session is missing a CSRF token. Sign in again, then retry.");
      return;
    }
    setMutationId("all");
    setMutationError(null);
    try {
      await markAllNotificationsRead(csrfToken);
      setPage(0);
      await Promise.allSettled([load(), activity.refreshNotifications()]);
    } catch {
      setMutationError("Notifications could not be marked as read. Try again.");
    } finally {
      setMutationId(null);
    }
  }

  const total = data?.pagination.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <div id="notification-center">
      <AccessibleOverlay description="Database notifications for your authenticated account." kind="drawer" onClose={onClose} returnFocusRef={returnFocusRef} title="Notifications">
        <div className="grid gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="inline-flex rounded-control bg-app-muted p-1" role="tablist" aria-label="Notification filter">
              {(["all", "unread"] as const).map((value) => (
                <button aria-selected={filter === value} className={filter === value ? "qops-tab qops-tab-active" : "qops-tab"} key={value} onClick={() => { setFilter(value); setPage(0); }} role="tab" type="button">{value === "all" ? "All" : "Unread"}</button>
              ))}
            </div>
            <button className="qops-button-secondary" disabled={mutationId !== null || (data?.unread_count ?? 0) === 0} onClick={() => void markAll()} type="button">
              <CheckCheck aria-hidden="true" size={16} /> {mutationId === "all" ? "Marking all…" : "Mark all as read"}
            </button>
          </div>

          {mutationError ? <p className="m-0 rounded-control border border-status-danger/40 bg-status-danger/10 p-3 text-sm text-app-text" role="alert">{mutationError}</p> : null}
          {status === "loading" ? <p className="m-0 text-sm text-app-subtle" role="status">Loading notifications…</p> : null}
          {status === "error" ? <div className="grid gap-3" role="alert"><p className="m-0 text-sm">Notifications could not be loaded safely.</p><button className="qops-button-secondary justify-self-start" onClick={() => void Promise.allSettled([load(), activity.refreshNotifications()])} type="button"><RefreshCw aria-hidden="true" size={16} /> Try again</button></div> : null}
          {status === "success" && data?.items.length === 0 ? <p className="m-0 rounded-control bg-app-muted p-4 text-sm text-app-subtle">{filter === "unread" ? "You have no unread notifications." : "You have no notifications."}</p> : null}
          {status === "success" && data?.items.length ? (
            <ul className="m-0 grid list-none divide-y divide-app-border p-0">{data.items.map((notification) => (
              <li className="grid gap-2 py-4 first:pt-0" key={notification.id}>
                <div className="flex items-start justify-between gap-3"><strong className="text-sm text-app-text">{notification.title}</strong><span className="text-xs font-bold text-app-subtle">{notification.is_read ? "Read" : "Unread"}</span></div>
                {notification.body ? <p className="m-0 text-sm leading-6 text-app-subtle">{notification.body}</p> : null}
                <p className="m-0 text-xs text-app-faint">{formatActionDate(notification.created_at)}</p>
                <div className="flex flex-wrap items-center gap-3">
                  <NotificationLink notification={notification} onNavigate={onClose} />
                  {!notification.is_read ? <button className="text-sm font-bold text-brand-primary disabled:opacity-60" disabled={mutationId !== null} onClick={() => void markOne(notification)} type="button">{mutationId === notification.id ? "Marking…" : "Mark as read"}</button> : null}
                </div>
              </li>
            ))}</ul>
          ) : null}
          {data && total > PAGE_SIZE ? <nav aria-label="Notification pagination" className="flex items-center justify-between gap-3"><button className="qops-button-secondary" disabled={page === 0 || status === "loading"} onClick={() => setPage((value) => Math.max(0, value - 1))} type="button">Previous</button><span className="text-sm text-app-subtle">Page {page + 1} of {pageCount}</span><button className="qops-button-secondary" disabled={page + 1 >= pageCount || status === "loading"} onClick={() => setPage((value) => value + 1)} type="button">Next</button></nav> : null}
        </div>
      </AccessibleOverlay>
    </div>
  );
}

function NotificationLink({ notification, onNavigate }: { notification: WorkflowNotification; onNavigate: () => void }) {
  const path = notificationPath(notification);
  return path ? <Link className="text-sm font-bold text-brand-primary" onClick={onNavigate} to={path}>Open related item</Link> : null;
}

export function notificationPath(notification: WorkflowNotification): string | null {
  if (notification.type === "action_pending_approval") return "/approvals";
  if (notification.type.startsWith("action_") && notification.related_entity?.type === "action_request") {
    return `/actions/${encodeURIComponent(notification.related_entity.id)}`;
  }
  if (notification.type === "role_request_decided") return "/profile";
  return null;
}

function bellLabel(count: number | null): string {
  if (count === null) return "Open notifications";
  return count === 1 ? "Open notifications, 1 unread" : `Open notifications, ${count} unread`;
}
