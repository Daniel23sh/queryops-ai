import { ClipboardCheck, UserCog, Users } from "lucide-react";

import type { AdminMetrics as Metrics } from "../types";

export function AdminMetrics({ metrics }: { metrics: Metrics }) {
  const items = [
    { icon: Users, label: "Active QueryOps users", value: metrics.active_app_users },
    {
      icon: UserCog,
      label: "Pending role requests",
      value: metrics.pending_role_requests
    },
    {
      icon: ClipboardCheck,
      label: "Audit events · 7 days",
      value: metrics.app_audit_events_last_7_days
    }
  ].filter((item) => item.value !== null);

  if (items.length === 0) {
    return null;
  }

  return (
    <section className="home-section home-section--compact" aria-labelledby="admin-metrics-title">
      <div className="home-section__heading">
        <p className="eyebrow">QueryOps administration</p>
        <h2 id="admin-metrics-title">Administrative metrics</h2>
      </div>
      <div className="home-admin-grid">
        {items.map((item) => (
          <article className="home-admin-card" key={item.label}>
            <item.icon aria-hidden="true" size={18} />
            <span>{item.label}</span>
            <strong>{new Intl.NumberFormat("en-US").format(item.value ?? 0)}</strong>
          </article>
        ))}
      </div>
    </section>
  );
}
