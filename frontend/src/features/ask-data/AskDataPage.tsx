import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { listQueryTemplates } from "../../api/queryTemplates";
import { runQuery } from "../../api/queries";
import type { AuthUser } from "../../auth/types";
import type { QueryRunResult, QueryTemplate, QueryTemplateCategory } from "./types";

type AskDataPageProps = {
  user: AuthUser;
  csrfToken: string | null;
};

type TemplateLoadStatus = "loading" | "loaded" | "error";

type TemplateRunState =
  | {
      status: "idle";
    }
  | {
      status: "running";
      question: string;
    }
  | {
      status: "success";
      question: string;
      result: QueryRunResult;
    }
  | {
      status: "error";
      message: string;
    };

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

export function AskDataPage({ user, csrfToken }: AskDataPageProps) {
  const canRunFreeQuery = user.permissions.includes("can_run_free_query");
  const canViewTechnicalDetails = user.permissions.includes("can_view_sql");
  const isAdmin = user.role === "admin";
  const [templates, setTemplates] = useState<QueryTemplate[]>([]);
  const [templateLoadStatus, setTemplateLoadStatus] =
    useState<TemplateLoadStatus>("loading");
  const [templateLoadError, setTemplateLoadError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [templateRunState, setTemplateRunState] = useState<TemplateRunState>({
    status: "idle"
  });
  const templateCategories = useMemo(
    () => groupTemplatesByCategory(templates),
    [templates]
  );
  const selectedTemplate =
    templates.find((template) => template.id === selectedTemplateId) ?? null;
  const scopeLabel =
    isAdmin ? "Global admin scope" : user.department?.name ?? "No scope";
  const modeLabel = canRunFreeQuery ? "Free-query shell" : "Template-only mode";
  const modeDescription = canRunFreeQuery
    ? "Free-query composer controls remain disabled until the free-query checkpoint."
    : "Selected templates can be used here; free-query access is not enabled for this role.";

  useEffect(() => {
    let isCurrent = true;

    setTemplateLoadStatus("loading");
    setTemplateLoadError(null);

    listQueryTemplates()
      .then((loadedTemplates) => {
        if (!isCurrent) {
          return;
        }

        setTemplates(loadedTemplates);
        setSelectedTemplateId((currentTemplateId) => {
          if (
            currentTemplateId &&
            loadedTemplates.some((template) => template.id === currentTemplateId)
          ) {
            return currentTemplateId;
          }

          return loadedTemplates[0]?.id ?? null;
        });
        setTemplateLoadStatus("loaded");
      })
      .catch((error: unknown) => {
        if (!isCurrent) {
          return;
        }

        setTemplates([]);
        setSelectedTemplateId(null);
        setTemplateLoadError(formatTemplateLoadError(error));
        setTemplateLoadStatus("error");
      });

    return () => {
      isCurrent = false;
    };
  }, []);

  async function handleRunSelectedTemplate() {
    if (templateRunState.status === "running" || selectedTemplate === null) {
      return;
    }

    if (!csrfToken) {
      setTemplateRunState({
        status: "error",
        message: "Refresh your session before running a template query."
      });
      return;
    }

    const question = selectedTemplate.natural_language_question;
    setTemplateRunState({
      status: "running",
      question
    });

    try {
      const result = await runQuery(
        {
          question,
          template_id: selectedTemplate.id
        },
        csrfToken
      );
      setTemplateRunState({
        status: "success",
        question,
        result
      });
    } catch (error: unknown) {
      setTemplateRunState({
        status: "error",
        message: formatQueryRunError(error)
      });
    }
  }

  return (
    <article className="ask-data-page" aria-labelledby="workspace-title">
      <div className="ask-data-page__header">
        <p className="eyebrow">Query integration</p>
        <h1 id="workspace-title">Ask Data</h1>
        <p className="subtitle">
          Prepare governed data questions in a dedicated workspace. Templates load
          from the Query API; query execution is wired in later PR4 checkpoints.
        </p>
      </div>

      <div className="ask-data-workspace">
        <TemplatePanel
          categories={templateCategories}
          error={templateLoadError}
          onSelectTemplate={setSelectedTemplateId}
          onRunSelectedTemplate={() => void handleRunSelectedTemplate()}
          runDisabledReason={
            selectedTemplate && !csrfToken
              ? "Refresh your session before running a template query."
              : null
          }
          running={templateRunState.status === "running"}
          selectedTemplate={selectedTemplate}
          selectedTemplateId={selectedTemplateId}
          status={templateLoadStatus}
        />
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
          <ResultPlaceholder templateRunState={templateRunState} />
        </section>
        <InsightPanel />
      </div>
    </article>
  );
}

function TemplatePanel({
  categories,
  error,
  onSelectTemplate,
  onRunSelectedTemplate,
  runDisabledReason,
  running,
  selectedTemplate,
  selectedTemplateId,
  status
}: {
  categories: QueryTemplateCategory[];
  error: string | null;
  onSelectTemplate: (templateId: string) => void;
  onRunSelectedTemplate: () => void;
  runDisabledReason: string | null;
  running: boolean;
  selectedTemplate: QueryTemplate | null;
  selectedTemplateId: string | null;
  status: TemplateLoadStatus;
}) {
  const hasTemplates = categories.length > 0;

  return (
    <section className="ask-data-panel" aria-label="Ask Data templates">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Left panel</p>
        <h2>Templates</h2>
      </div>

      {status === "loading" ? (
        <p className="ask-data-state-message" role="status">
          Loading query templates...
        </p>
      ) : null}

      {status === "error" ? (
        <p className="form-message form-message--error" role="alert">
          {error ?? "Query templates could not be loaded."}
        </p>
      ) : null}

      {status === "loaded" && !hasTemplates ? (
        <p className="ask-data-state-message">
          No query templates are available yet.
        </p>
      ) : null}

      {status === "loaded" && hasTemplates ? (
        <>
          <div className="ask-data-template-groups" aria-label="Query template categories">
            {categories.map((group) => (
              <button
                key={group.category}
                type="button"
                onClick={() => onSelectTemplate(group.templates[0].id)}
              >
                {group.category}
              </button>
            ))}
          </div>

          <ul className="ask-data-template-list" aria-label="Query templates">
            {categories.flatMap((group) =>
              group.templates.map((template) => (
                <li key={template.id}>
                  <button
                    type="button"
                    className="ask-data-template-card"
                    aria-pressed={template.id === selectedTemplateId}
                    data-selected={template.id === selectedTemplateId ? "true" : "false"}
                    onClick={() => onSelectTemplate(template.id)}
                  >
                    <strong>{template.title}</strong>
                    <p>{template.description}</p>
                  </button>
                </li>
              ))
            )}
          </ul>
        </>
      ) : null}

      <SelectedTemplateDetails
        disabledReason={runDisabledReason}
        onRunSelectedTemplate={onRunSelectedTemplate}
        running={running}
        template={selectedTemplate}
      />
    </section>
  );
}

function SelectedTemplateDetails({
  disabledReason,
  onRunSelectedTemplate,
  running,
  template
}: {
  disabledReason: string | null;
  onRunSelectedTemplate: () => void;
  running: boolean;
  template: QueryTemplate | null;
}) {
  const canRunTemplate = template !== null && disabledReason === null && !running;

  return (
    <div className="ask-data-selected-template" aria-label="Selected query template">
      <h3>Selected template</h3>
      {template ? (
        <>
          <strong>{template.title}</strong>
          <p>{template.description}</p>
          <p>{template.natural_language_question}</p>
          {template.parameters.length > 0 ? (
            <p className="ask-data-template-parameter-note">
              Custom parameters are not supported yet; backend template defaults
              will be used.
            </p>
          ) : null}
          <div className="ask-data-template-actions">
            <button
              type="button"
              className="primary-action-button"
              disabled={!canRunTemplate}
              onClick={onRunSelectedTemplate}
            >
              {running ? "Running template..." : "Run selected template"}
            </button>
          </div>
          {disabledReason ? (
            <p className="ask-data-session-message">{disabledReason}</p>
          ) : null}
        </>
      ) : (
        <p>Select a template to view its default question and scope.</p>
      )}
    </div>
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
          Templates load from the Query API in this checkpoint. Query execution
          is wired in later PR4 checkpoints, and history endpoints remain idle here.
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
          <span>Global scope indicator only. Template runs still use backend authorization.</span>
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
              placeholder="Query execution is wired in later PR4 checkpoints."
            />
          </label>
          <div className="ask-data-composer-actions">
            <button type="button" className="primary-action-button" disabled>
              Available in next PR
            </button>
          </div>
          <p className="ask-data-mode-note">
            The composer is disabled in this PR. It will call the Query API only
            after the free-query checkpoint adds query execution.
          </p>
          {canViewTechnicalDetails ? <TechnicalCapabilityPlaceholder /> : null}
        </>
      ) : (
        <div className="ask-data-template-only-shell">
          <h3>Template-only mode</h3>
          <p>
            Selected templates can be used here. This role does not receive a
            free-query input in the shell.
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

function ResultPlaceholder({
  templateRunState
}: {
  templateRunState: TemplateRunState;
}) {
  return (
    <section className="ask-data-panel" aria-labelledby="result-placeholder-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Template result</p>
        <h2 id="result-placeholder-title">Result placeholder</h2>
      </div>

      {templateRunState.status === "idle" ? (
        <div className="ask-data-result-shell" aria-label="Result table placeholder">
          <div>Column A</div>
          <div>Column B</div>
          <div>Value pending</div>
          <div>Run a selected template to preview the query result summary.</div>
        </div>
      ) : null}

      {templateRunState.status === "running" ? (
        <p className="ask-data-state-message" role="status">
          Running selected template...
        </p>
      ) : null}

      {templateRunState.status === "error" ? (
        <p className="form-message form-message--error" role="alert">
          {templateRunState.message}
        </p>
      ) : null}

      {templateRunState.status === "success" ? (
        <div className="ask-data-result-summary" aria-label="Query result summary">
          <h3>Query result</h3>
          <p>{templateRunState.result.message}</p>
          <dl className="ask-data-result-metadata">
            <div>
              <dt>Status</dt>
              <dd>Status: {templateRunState.result.status}</dd>
            </div>
            <div>
              <dt>Rows</dt>
              <dd>{templateRunState.result.row_count}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{templateRunState.result.duration_ms} ms</dd>
            </div>
          </dl>
        </div>
      ) : null}
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

function groupTemplatesByCategory(
  templates: QueryTemplate[]
): QueryTemplateCategory[] {
  const categoryMap = new Map<string, QueryTemplate[]>();

  for (const template of templates) {
    const category = template.category || "Uncategorized";
    const categoryTemplates = categoryMap.get(category) ?? [];
    categoryTemplates.push(template);
    categoryMap.set(category, categoryTemplates);
  }

  return Array.from(categoryMap, ([category, categoryTemplates]) => ({
    category,
    templates: categoryTemplates
  }));
}

function formatTemplateLoadError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Query templates could not be loaded.";
}

function formatQueryRunError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Template query could not be run.";
}
