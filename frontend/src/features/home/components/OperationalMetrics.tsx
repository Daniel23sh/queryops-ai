import {
  BadgeDollarSign,
  CircleOff,
  Laptop,
  ShieldAlert,
  TicketCheck,
  UsersRound
} from "lucide-react";

import type { HomeScope, OperationalMetrics as Metrics } from "../types";

export function OperationalMetrics({
  metrics,
  scope
}: {
  metrics: Metrics;
  scope: HomeScope;
}) {
  const tiles = [
    {
      icon: UsersRound,
      label: "Active users",
      value: integer(metrics.active_human_users)
    },
    {
      icon: Laptop,
      label: "Device compliance",
      value: percentage(metrics.device_compliance_rate),
      secondary:
        metrics.device_total === null
          ? undefined
          : `${integer(metrics.compliant_device_count)} of ${integer(metrics.device_total)} devices`
    },
    {
      icon: BadgeDollarSign,
      label: "Monthly license cost",
      value: currency(metrics.monthly_license_cost_usd)
    },
    {
      icon: CircleOff,
      label: "Unused licenses",
      value: integer(metrics.unused_license_assignments)
    },
    {
      icon: TicketCheck,
      label: "Open support tickets",
      value: integer(metrics.open_support_tickets)
    },
    {
      icon: ShieldAlert,
      label: "Security events · 30 days",
      value: integer(metrics.security_events_last_30_days)
    }
  ];

  return (
    <section className="home-section" aria-labelledby="operational-metrics-title">
      <div className="home-section__heading home-section__heading--split">
        <div>
          <p className="eyebrow">Operational view</p>
          <h2 id="operational-metrics-title">Operational metrics</h2>
        </div>
        <span className="home-scope-pill">{scope.display_name}</span>
      </div>
      <div className="home-metric-grid">
        {tiles.map((tile) => (
          <article className="home-metric-card" key={tile.label}>
            <div className="home-metric-card__icon">
              <tile.icon aria-hidden="true" size={19} />
            </div>
            <p>{tile.label}</p>
            <strong>{tile.value}</strong>
            {tile.secondary ? <span>{tile.secondary}</span> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function integer(value: number | null): string {
  return value === null ? "Unavailable" : new Intl.NumberFormat("en-US").format(value);
}

function percentage(value: number | null): string {
  return value === null
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: 1,
        minimumFractionDigits: 0,
        style: "percent"
      }).format(value / 100);
}

function currency(value: number | null): string {
  return value === null
    ? "Unavailable"
    : new Intl.NumberFormat("en-US", {
        currency: "USD",
        maximumFractionDigits: 2,
        style: "currency"
      }).format(value);
}
