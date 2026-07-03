import type { DashboardActivityRow } from "../dashboardModel";

export function DemoActivityPreview({ rows }: { rows: DashboardActivityRow[] }) {
  return (
    <section className="dashboard-section" aria-labelledby="dashboard-activity-title">
      <div className="dashboard-section__header">
        <p className="eyebrow">Workspace preview</p>
        <h2 id="dashboard-activity-title">Demo activity preview</h2>
      </div>
      <ul className="dashboard-activity-list">
        {rows.map((row) => (
          <li key={row.title} className="dashboard-activity-item">
            <div>
              <h3>{row.title}</h3>
              <p>{row.meta}</p>
            </div>
            <span className="dashboard-status-pill">{row.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
