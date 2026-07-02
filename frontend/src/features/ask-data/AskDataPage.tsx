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

const FUTURE_OPERATION_PLACEHOLDERS = [
  {
    label: "Save as Card",
    milestone: "Later dashboards/cards milestone",
    summary: "Saving query results as dashboard cards is intentionally unavailable in this shell."
  },
  {
    label: "CSV Export",
    milestone: "Later export milestone",
    summary: "Export controls stay disabled until a dedicated export milestone defines the behavior."
  },
  {
    label: "Preview Action",
    milestone: "Later actions milestone",
    summary: "Action previews require future deterministic action and approval flows before activation."
  }
];

export function AskDataPage({ user }: AskDataPageProps) {
  const canRunFreeQuery = user.permissions.includes("can_run_free_query");
  const canViewTechnicalDetails = user.permissions.includes("can_view_sql");
  const isAdmin = user.role === "admin";
  const scopeLabel =
    isAdmin ? "Global admin scope" : user.department?.name ?? "No scope";
  const modeLabel = canRunFreeQuery ? "Free-query shell" : "Template-only mode";
  const modeDescription = canRunFreeQuery
    ? "Free-query composer controls are static in this PR. Query execution comes in PR4."
    : "Approved templates will be available in PR4. Free-query access is not enabled for this role.";

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
            showAdminGlobalIndicator={isAdmin}
          />
          <QuestionComposer
            canRunFreeQuery={canRunFreeQuery}
            canViewTechnicalDetails={canViewTechnicalDetails}
          />
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
  scopeLabel,
  showAdminGlobalIndicator
}: {
  modeLabel: string;
  modeDescription: string;
  roleLabel: string;
  scopeLabel: string;
  showAdminGlobalIndicator: boolean;
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
      {showAdminGlobalIndicator ? (
        <p className="ask-data-admin-note">
          <strong>Admin global shell</strong>
          <span>Global scope indicator only. No backend query is connected in this PR.</span>
        </p>
      ) : null}
    </section>
  );
}

function QuestionComposer({
  canRunFreeQuery,
  canViewTechnicalDetails
}: {
  canRunFreeQuery: boolean;
  canViewTechnicalDetails: boolean;
}) {
  return (
    <section className="ask-data-panel" aria-labelledby="question-composer-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Center panel</p>
        <h2 id="question-composer-title">Question composer</h2>
      </div>
      {canRunFreeQuery ? (
        <>
          <label className="ask-data-question-shell" htmlFor="ask-data-free-query-draft">
            <span>Free query draft</span>
            <textarea
              id="ask-data-free-query-draft"
              rows={4}
              disabled
              placeholder="Query execution comes in PR4."
            />
          </label>
          <div className="ask-data-composer-actions">
            <button type="button" className="primary-action-button" disabled>
              Available in next PR
            </button>
          </div>
          <p className="ask-data-mode-note">
            The composer is disabled in this PR. It will call the Query API only
            after PR4 adds query integration.
          </p>
          {canViewTechnicalDetails ? <TechnicalCapabilityPlaceholder /> : null}
        </>
      ) : (
        <div className="ask-data-template-only-shell">
          <h3>Template-only mode</h3>
          <p>
            Approved templates will be available in PR4. This role does not receive
            a free-query input in the shell.
          </p>
        </div>
      )}
    </section>
  );
}

function TechnicalCapabilityPlaceholder() {
  return (
    <div className="ask-data-technical-placeholder">
      <h3>Technical capability</h3>
      <p>
        SQL and correction details will appear in PR5 as static role-aware tabs.
        No live SQL tab is available in this shell.
      </p>
    </div>
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

      <div className="ask-data-disabled-actions" aria-label="Future operational actions">
        {FUTURE_OPERATION_PLACEHOLDERS.map((placeholder) => (
          <div className="ask-data-disabled-action" key={placeholder.label}>
            <button type="button" disabled>
              {placeholder.label}
            </button>
            <div>
              <strong>{placeholder.milestone}</strong>
              <p>{placeholder.summary}</p>
            </div>
          </div>
        ))}
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
