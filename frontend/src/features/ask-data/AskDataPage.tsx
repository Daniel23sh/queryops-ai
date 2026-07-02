import type { AuthUser } from "../../auth/types";

type AskDataPageProps = {
  user: AuthUser;
};

const TEMPLATE_EXAMPLES = [
  {
    category: "Licenses",
    title: "Unused licenses",
    summary: "Find reclaim opportunities from approved license templates."
  },
  {
    category: "Identity",
    title: "Inactive users",
    summary: "Review stale account patterns once template data loads."
  },
  {
    category: "Security",
    title: "Security events",
    summary: "Prepare security event reviews for scoped query integration."
  }
];

export function AskDataPage({ user }: AskDataPageProps) {
  const canRunFreeQuery = user.permissions.includes("can_run_free_query");
  const scopeLabel =
    user.role === "admin" ? "Global admin scope" : user.department?.name ?? "No scope";
  const modeLabel = canRunFreeQuery ? "Free-query shell" : "Template-only mode";
  const modeDescription = canRunFreeQuery
    ? "Free-query composer controls will appear here in a later checkpoint. This shell still does not run queries."
    : "Use approved templates when query integration arrives. Free-query access is not enabled for this role.";

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

      <div className="ask-data-workspace">
        <TemplatePanel />
        <section
          className="ask-data-workspace__main"
          aria-label="Ask Data workspace"
        >
          <RoleScopeNotice
            modeLabel={modeLabel}
            modeDescription={modeDescription}
            roleLabel={formatRole(user.role)}
            scopeLabel={scopeLabel}
          />
          <QuestionComposer />
          <ResultPlaceholder />
        </section>
        <InsightPanel />
      </div>
    </article>
  );
}

function TemplatePanel() {
  return (
    <section className="ask-data-panel" aria-label="Ask Data templates">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Left panel</p>
        <h2>Templates</h2>
      </div>

      <div className="ask-data-template-groups" aria-label="Categories placeholder">
        {["Licenses", "Identity", "Security"].map((category) => (
          <span key={category}>{category}</span>
        ))}
      </div>

      <ul className="ask-data-template-list" aria-label="Template list placeholder">
        {TEMPLATE_EXAMPLES.map((template) => (
          <li key={template.title}>
            <span>{template.category}</span>
            <strong>{template.title}</strong>
            <p>{template.summary}</p>
          </li>
        ))}
      </ul>

      <div className="ask-data-selected-template">
        <h3>Selected template</h3>
        <p>
          Choose a template here once the API is connected. These examples are
          static placeholders only.
        </p>
      </div>
    </section>
  );
}

function RoleScopeNotice({
  modeLabel,
  modeDescription,
  roleLabel,
  scopeLabel
}: {
  modeLabel: string;
  modeDescription: string;
  roleLabel: string;
  scopeLabel: string;
}) {
  return (
    <section className="ask-data-status-panel" aria-label="Ask Data shell status">
      <div>
        <h2>Role and scope</h2>
        <p>
          This page is a static shell only. It does not load templates, run
          queries, clarify questions, or call query history endpoints yet.
        </p>
      </div>
      <dl className="ask-data-status-grid" aria-label="Ask Data access summary">
        <div>
          <dt>Mode</dt>
          <dd>{modeLabel}</dd>
        </div>
        <div>
          <dt>Role</dt>
          <dd>{roleLabel}</dd>
        </div>
        <div>
          <dt>Scope</dt>
          <dd>{scopeLabel}</dd>
        </div>
      </dl>
      <p className="ask-data-mode-note">{modeDescription}</p>
    </section>
  );
}

function QuestionComposer() {
  return (
    <section className="ask-data-panel" aria-labelledby="question-composer-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Center panel</p>
        <h2 id="question-composer-title">Question composer</h2>
      </div>
      <label className="ask-data-question-shell" htmlFor="ask-data-question-draft">
        <span>Question draft</span>
        <textarea
          id="ask-data-question-draft"
          rows={4}
          disabled
          placeholder="Query integration comes in the next PR."
        />
      </label>
      <p className="ask-data-mode-note">
        The composer is disabled in this PR. It will call the Query API only after
        PR4 adds query integration.
      </p>
    </section>
  );
}

function ResultPlaceholder() {
  return (
    <section className="ask-data-panel" aria-labelledby="result-placeholder-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Static result</p>
        <h2 id="result-placeholder-title">Result placeholder</h2>
      </div>
      <div className="ask-data-result-shell" aria-label="Result table placeholder">
        <div>Column A</div>
        <div>Column B</div>
        <div>Value pending</div>
        <div>Query integration comes in the next PR.</div>
      </div>
    </section>
  );
}

function InsightPanel() {
  return (
    <section className="ask-data-panel" aria-label="Ask Data insights">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Right panel</p>
        <h2>Explanation</h2>
      </div>
      <p>
        Explanation placeholder for assumptions, scope, validation, and result
        interpretation once live queries are connected.
      </p>

      <div className="ask-data-insight-block">
        <h3>Suggested Action</h3>
        <p>
          Future action recommendations will appear here as disabled placeholders
          until the actions milestone begins.
        </p>
      </div>

      <div className="ask-data-insight-block">
        <h3>Future status</h3>
        <p>Loading, clarification, and no-row states will be wired in PR4.</p>
      </div>
    </section>
  );
}

function formatRole(role: AuthUser["role"]): string {
  if (!role) {
    return "Unassigned";
  }

  return role.charAt(0).toUpperCase() + role.slice(1);
}
