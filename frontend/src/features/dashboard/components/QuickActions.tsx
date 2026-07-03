import type { DashboardAction } from "../dashboardModel";

export function QuickActions({
  actions,
  onNavigate
}: {
  actions: DashboardAction[];
  onNavigate: (navId: string) => void;
}) {
  return (
    <section className="dashboard-section" aria-labelledby="dashboard-actions-title">
      <div className="dashboard-section__header">
        <p className="eyebrow">Recommended next steps</p>
        <h2 id="dashboard-actions-title">Move through the workspace</h2>
      </div>
      <div className="dashboard-actions-grid">
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            className="dashboard-action-button"
            aria-label={action.label}
            data-primary={action.isPrimary ? "true" : "false"}
            disabled={action.disabled}
            onClick={() => {
              if (action.navId) {
                onNavigate(action.navId);
              }
            }}
          >
            <span className="dashboard-action-button__label">{action.label}</span>
            <span className="dashboard-action-button__description">
              {action.description}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
