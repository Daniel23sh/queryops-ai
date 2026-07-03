export function DashboardHero({
  departmentLabel,
  roleLabel
}: {
  departmentLabel: string;
  roleLabel: string;
}) {
  return (
    <section className="dashboard-hero" aria-labelledby="workspace-title">
      <div className="dashboard-hero__copy">
        <p className="eyebrow">My Dashboard</p>
        <h1 id="workspace-title">QueryOps Command Center</h1>
        <p className="subtitle">
          A role-aware overview of governed analytics access for this demo
          workspace. The dashboard summarizes current permissions without adding
          new backend behavior.
        </p>
      </div>
      <div className="dashboard-chip-row" aria-label="Workspace context">
        <span className="dashboard-chip">
          Role <strong>{roleLabel}</strong>
        </span>
        <span className="dashboard-chip">Scope: {departmentLabel}</span>
        <span className="dashboard-chip">Demo environment</span>
      </div>
    </section>
  );
}
