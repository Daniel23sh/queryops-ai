import type { AuthUser } from "../../auth/types";

type AskDataPageProps = {
  user: AuthUser;
};

export function AskDataPage({ user }: AskDataPageProps) {
  const scopeLabel =
    user.role === "admin" ? "Global admin scope" : user.department?.name ?? "No scope";

  return (
    <article className="ask-data-page" aria-labelledby="workspace-title">
      <div className="ask-data-page__header">
        <p className="eyebrow">Static UI shell</p>
        <h1 id="workspace-title">Ask Data</h1>
        <p className="subtitle">
          Prepare governed data questions in a dedicated workspace. Query integration
          comes in the next PR.
        </p>
      </div>

      <section className="ask-data-status-panel" aria-label="Ask Data shell status">
        <div>
          <h2>Shell ready for layout</h2>
          <p>
            This page is a static shell only. It does not load templates, run
            queries, clarify questions, or call query history endpoints yet.
          </p>
        </div>
        <dl className="ask-data-status-grid" aria-label="Ask Data access summary">
          <div>
            <dt>Mode</dt>
            <dd>Static shell</dd>
          </div>
          <div>
            <dt>Role</dt>
            <dd>{formatRole(user.role)}</dd>
          </div>
          <div>
            <dt>Scope</dt>
            <dd>{scopeLabel}</dd>
          </div>
        </dl>
      </section>
    </article>
  );
}

function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}
