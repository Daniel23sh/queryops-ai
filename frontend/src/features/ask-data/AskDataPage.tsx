import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { listQueryTemplates } from "../../api/queryTemplates";
import { clarifyQuery, runQuery } from "../../api/queries";
import type { AuthUser } from "../../auth/types";
import type {
  QueryResultRow,
  QueryRowValue,
  QueryRunResult,
  QueryTemplate,
  QueryTemplateCategory
} from "./types";

type AskDataPageProps = {
  user: AuthUser;
  csrfToken: string | null;
};

type TemplateLoadStatus = "loading" | "loaded" | "error";

type QueryRunMode = "template" | "free" | "clarification";

type AskDataResultTab = "results" | "summary" | "sql" | "diagnostics";

type QueryRunState =
  | {
      status: "idle";
    }
  | {
      status: "running";
      mode: QueryRunMode;
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
  const [queryRunState, setQueryRunState] = useState<QueryRunState>({
    status: "idle"
  });
  const [freeQuestion, setFreeQuestion] = useState("");
  const [clarificationQuestion, setClarificationQuestion] = useState("");
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
    ? "Free-query composer is available for this role and still uses backend authorization."
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
    if (queryRunState.status === "running" || selectedTemplate === null) {
      return;
    }

    if (!csrfToken) {
      setQueryRunState({
        status: "error",
        message: "Refresh your session before running a template query."
      });
      return;
    }

    const question = selectedTemplate.natural_language_question;
    setClarificationQuestion("");
    setQueryRunState({
      status: "running",
      mode: "template",
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
      setQueryRunState({
        status: "success",
        question,
        result
      });
    } catch (error: unknown) {
      setQueryRunState({
        status: "error",
        message: formatQueryRunError(error)
      });
    }
  }

  async function handleRunFreeQuery() {
    const question = freeQuestion.trim();
    if (queryRunState.status === "running" || !question) {
      return;
    }

    if (!csrfToken) {
      setQueryRunState({
        status: "error",
        message: "Refresh your session before running a free query."
      });
      return;
    }

    setQueryRunState({
      status: "running",
      mode: "free",
      question
    });
    setClarificationQuestion("");

    try {
      const result = await runQuery(
        {
          question
        },
        csrfToken
      );
      setQueryRunState({
        status: "success",
        question,
        result
      });
    } catch (error: unknown) {
      setQueryRunState({
        status: "error",
        message: formatQueryRunError(error)
      });
    }
  }

  async function handleSubmitClarification() {
    const question = clarificationQuestion.trim();
    if (
      queryRunState.status === "running" ||
      queryRunState.status !== "success" ||
      !queryRunState.result.clarification_required ||
      !question
    ) {
      return;
    }

    const queryRunId = queryRunState.result.query_run_id;
    if (!queryRunId || !csrfToken) {
      return;
    }

    setQueryRunState({
      status: "running",
      mode: "clarification",
      question
    });

    try {
      const result = await clarifyQuery(queryRunId, question, csrfToken);
      setClarificationQuestion("");
      setQueryRunState({
        status: "success",
        question,
        result
      });
    } catch (error: unknown) {
      setQueryRunState({
        status: "error",
        message: formatClarificationError(error)
      });
    }
  }

  return (
    <article className="ask-data-page" aria-labelledby="workspace-title">
      <div className="ask-data-page__header">
        <p className="eyebrow">Query integration</p>
        <h1 id="workspace-title">Ask Data</h1>
        <p className="subtitle">
          Prepare governed data questions in a dedicated workspace. Templates,
          questions, result tables, and clarification states use the Query API.
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
          running={queryRunState.status === "running"}
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
            freeQuestion={freeQuestion}
            onFreeQuestionChange={setFreeQuestion}
            onRunFreeQuery={() => void handleRunFreeQuery()}
            runDisabledReason={
              canRunFreeQuery && !csrfToken
                ? "Refresh your session before running a free query."
                : null
            }
            running={queryRunState.status === "running"}
          />
          <ResultPlaceholder
            canClarify={canRunFreeQuery}
            canViewTechnicalDetails={canViewTechnicalDetails}
            clarificationDisabledReason={
              queryRunState.status === "success" &&
              queryRunState.result.clarification_required
                ? clarificationDisabledReason(queryRunState.result, csrfToken)
                : null
            }
            clarificationQuestion={clarificationQuestion}
            onClarificationQuestionChange={setClarificationQuestion}
            onSubmitClarification={() => void handleSubmitClarification()}
            queryRunState={queryRunState}
          />
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
          Templates and questions use the Query API in this checkpoint. History
          endpoints remain idle here.
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
  freeQuestion,
  onFreeQuestionChange,
  onRunFreeQuery,
  runDisabledReason,
  running
}: {
  canRunFreeQuery: boolean;
  freeQuestion: string;
  onFreeQuestionChange: (question: string) => void;
  onRunFreeQuery: () => void;
  runDisabledReason: string | null;
  running: boolean;
}) {
  const trimmedFreeQuestion = freeQuestion.trim();
  const canRunFreeQueryNow =
    trimmedFreeQuestion.length > 0 && runDisabledReason === null && !running;

  return (
    <section className="ask-data-panel" aria-labelledby="question-composer-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Center panel</p>
        <h2 id="question-composer-title">Question composer</h2>
      </div>
      {canRunFreeQuery ? (
        <>
          <label className="ask-data-question-shell" htmlFor="ask-data-free-question">
            <span>Free question</span>
            <textarea
              id="ask-data-free-question"
              rows={4}
              placeholder="Ask a governed data question."
              value={freeQuestion}
              disabled={running}
              onChange={(event) => onFreeQuestionChange(event.target.value)}
            />
          </label>
          <div className="ask-data-composer-actions">
            <button
              type="button"
              className="primary-action-button"
              disabled={!canRunFreeQueryNow}
              onClick={onRunFreeQuery}
            >
              {running ? "Running query..." : "Run free query"}
            </button>
          </div>
          <p className="ask-data-mode-note">
            Free questions are sent to the Query API using your current role and
            access scope.
          </p>
          {runDisabledReason ? (
            <p className="ask-data-session-message">{runDisabledReason}</p>
          ) : null}
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

function ResultPlaceholder({
  canClarify,
  canViewTechnicalDetails,
  clarificationDisabledReason,
  clarificationQuestion,
  onClarificationQuestionChange,
  onSubmitClarification,
  queryRunState
}: {
  canClarify: boolean;
  canViewTechnicalDetails: boolean;
  clarificationDisabledReason: string | null;
  clarificationQuestion: string;
  onClarificationQuestionChange: (question: string) => void;
  onSubmitClarification: () => void;
  queryRunState: QueryRunState;
}) {
  const [activeTab, setActiveTab] = useState<AskDataResultTab>("results");
  const activeVisibleTab =
    !canViewTechnicalDetails && (activeTab === "sql" || activeTab === "diagnostics")
      ? "results"
      : activeTab;

  useEffect(() => {
    if (activeVisibleTab !== activeTab) {
      setActiveTab(activeVisibleTab);
    }
  }, [activeTab, activeVisibleTab]);

  return (
    <section className="ask-data-panel" aria-labelledby="result-placeholder-title">
      <div className="ask-data-panel__header">
        <p className="eyebrow">Query result</p>
        <h2 id="result-placeholder-title">Result placeholder</h2>
      </div>

      <ResultTabs
        activeTab={activeVisibleTab}
        canViewTechnicalDetails={canViewTechnicalDetails}
        onSelectTab={setActiveTab}
      />

      <div
        className="ask-data-result-tab-panel"
        id={`ask-data-tab-panel-${activeVisibleTab}`}
        role="tabpanel"
        aria-labelledby={`ask-data-tab-${activeVisibleTab}`}
      >
        {activeVisibleTab === "results" ? (
          <ResultsTabContent
            canClarify={canClarify}
            clarificationDisabledReason={clarificationDisabledReason}
            clarificationQuestion={clarificationQuestion}
            onClarificationQuestionChange={onClarificationQuestionChange}
            onSubmitClarification={onSubmitClarification}
            queryRunState={queryRunState}
          />
        ) : null}

        {activeVisibleTab === "summary" ? (
          <SummaryTabContent queryRunState={queryRunState} />
        ) : null}

        {activeVisibleTab === "sql" && canViewTechnicalDetails ? (
          <SqlTabContent queryRunState={queryRunState} />
        ) : null}

        {activeVisibleTab === "diagnostics" && canViewTechnicalDetails ? (
          <DiagnosticsTabPlaceholder />
        ) : null}
      </div>
    </section>
  );
}

function ResultTabs({
  activeTab,
  canViewTechnicalDetails,
  onSelectTab
}: {
  activeTab: AskDataResultTab;
  canViewTechnicalDetails: boolean;
  onSelectTab: (tab: AskDataResultTab) => void;
}) {
  const tabs: { id: AskDataResultTab; label: string; technicalOnly?: boolean }[] = [
    { id: "results", label: "Results" },
    { id: "summary", label: "Summary" },
    { id: "sql", label: "SQL", technicalOnly: true },
    { id: "diagnostics", label: "Diagnostics", technicalOnly: true }
  ];

  return (
    <div className="ask-data-result-tabs" role="tablist" aria-label="Ask Data result views">
      {tabs
        .filter((tab) => !tab.technicalOnly || canViewTechnicalDetails)
        .map((tab) => (
          <button
            key={tab.id}
            id={`ask-data-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`ask-data-tab-panel-${tab.id}`}
            className="ask-data-result-tab"
            onClick={() => onSelectTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
    </div>
  );
}

function ResultsTabContent({
  canClarify,
  clarificationDisabledReason,
  clarificationQuestion,
  onClarificationQuestionChange,
  onSubmitClarification,
  queryRunState
}: {
  canClarify: boolean;
  clarificationDisabledReason: string | null;
  clarificationQuestion: string;
  onClarificationQuestionChange: (question: string) => void;
  onSubmitClarification: () => void;
  queryRunState: QueryRunState;
}) {
  return (
    <>
      {queryRunState.status === "idle" ? (
        <div className="ask-data-result-shell" aria-label="Result table placeholder">
          <div>Column A</div>
          <div>Column B</div>
          <div>Value pending</div>
          <div>Run a selected template or free question to preview the query result summary.</div>
        </div>
      ) : null}

      {queryRunState.status === "running" ? (
        <p className="ask-data-state-message" role="status">
          {runningQueryMessage(queryRunState.mode)}
        </p>
      ) : null}

      {queryRunState.status === "error" ? (
        <p className="form-message form-message--error" role="alert">
          {queryRunState.message}
        </p>
      ) : null}

      {queryRunState.status === "success" ? (
        <QueryResultSummary
          canClarify={canClarify}
          clarificationDisabledReason={clarificationDisabledReason}
          clarificationQuestion={clarificationQuestion}
          onClarificationQuestionChange={onClarificationQuestionChange}
          onSubmitClarification={onSubmitClarification}
          question={queryRunState.question}
          result={queryRunState.result}
        />
      ) : null}
    </>
  );
}

function SummaryTabContent({ queryRunState }: { queryRunState: QueryRunState }) {
  if (queryRunState.status === "success") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>Summary</h3>
        <p>{queryRunState.result.message}</p>
        <p>Question: {queryRunState.question}</p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>Summary</h3>
        <p>{runningQueryMessage(queryRunState.mode)}</p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>Summary</h3>
        <p>The latest request ended with a safe error state.</p>
      </div>
    );
  }

  return (
    <div className="ask-data-result-tab-placeholder">
      <h3>Summary</h3>
      <p>Run a selected template or free question to populate the result summary.</p>
    </div>
  );
}

function SqlTabContent({ queryRunState }: { queryRunState: QueryRunState }) {
  if (queryRunState.status === "idle") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>SQL</h3>
        <p>Run a query to inspect SQL for this role.</p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>SQL</h3>
        <p>SQL will be available after the query finishes, if the backend returns it.</p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>SQL</h3>
        <p>SQL is not available because the latest request ended with a safe error state.</p>
      </div>
    );
  }

  const generatedSql = safeSqlText(queryRunState.result.generated_sql);
  const executedSql = safeSqlText(queryRunState.result.executed_sql);

  if (!generatedSql && !executedSql) {
    return (
      <div className="ask-data-result-tab-placeholder">
        <h3>SQL</h3>
        <p>SQL is not available for this query result.</p>
      </div>
    );
  }

  return (
    <div className="ask-data-sql-tab-content">
      <h3>SQL</h3>
      <p>
        SQL is visible only for roles with SQL access. Generated SQL is the
        provider output; executed SQL is the validated SQL sent to the query
        executor.
      </p>
      {generatedSql ? <SqlBlock label="Generated SQL" sql={generatedSql} /> : null}
      {executedSql ? <SqlBlock label="Executed SQL" sql={executedSql} /> : null}
    </div>
  );
}

function SqlBlock({ label, sql }: { label: string; sql: string }) {
  return (
    <section className="ask-data-sql-block" aria-label={label}>
      <h4>{label}</h4>
      <pre className="ask-data-sql-code">
        <code>{sql}</code>
      </pre>
    </section>
  );
}

function DiagnosticsTabPlaceholder() {
  return (
    <div className="ask-data-result-tab-placeholder">
      <h3>Diagnostics</h3>
      <p>
        Safe validation, execution, and correction diagnostics will be added
        from query metadata in the next checkpoint.
      </p>
    </div>
  );
}

function safeSqlText(sql: string | null | undefined): string | null {
  if (typeof sql !== "string") {
    return null;
  }

  const trimmedSql = sql.trim();
  return trimmedSql.length > 0 ? trimmedSql : null;
}

function QueryResultSummary({
  canClarify,
  clarificationDisabledReason,
  clarificationQuestion,
  onClarificationQuestionChange,
  onSubmitClarification,
  question,
  result
}: {
  canClarify: boolean;
  clarificationDisabledReason: string | null;
  clarificationQuestion: string;
  onClarificationQuestionChange: (question: string) => void;
  onSubmitClarification: () => void;
  question: string;
  result: QueryRunResult;
}) {
  const columns = result.columns.length > 0 ? result.columns : firstRowColumns(result.rows);
  const hasRows = result.rows.length > 0 && columns.length > 0;

  if (result.clarification_required) {
    return (
      <ClarificationPanel
        canClarify={canClarify}
        disabledReason={clarificationDisabledReason}
        message={result.message}
        onQuestionChange={onClarificationQuestionChange}
        onSubmit={onSubmitClarification}
        question={clarificationQuestion}
      />
    );
  }

  return (
    <div className="ask-data-result-summary" aria-label="Query result summary">
      <h3>Query result</h3>
      <p>{result.message}</p>
      <p>Question: {question}</p>
      <dl className="ask-data-result-metadata">
        <div>
          <dt>Status</dt>
          <dd>Status: {result.status}</dd>
        </div>
        <div>
          <dt>Rows</dt>
          <dd>{result.row_count}</dd>
        </div>
        <div>
          <dt>Duration</dt>
          <dd>{result.duration_ms} ms</dd>
        </div>
      </dl>

      {result.truncated || result.warnings.length > 0 ? (
        <div className="ask-data-result-notices">
          {result.truncated ? (
            <p className="ask-data-truncated-notice">
              <strong>Results truncated</strong>
              <span>Only the returned rows are shown in this preview.</span>
            </p>
          ) : null}
          {result.warnings.length > 0 ? (
            <div className="ask-data-warning-list" aria-label="Query warnings">
              <h4>Warnings</h4>
              <ul>
                {result.warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      <VisualizationSuggestion columns={columns} rows={result.rows} />

      {hasRows ? (
        <QueryResultTable columns={columns} rows={result.rows} />
      ) : (
        <p className="ask-data-empty-result">No rows returned.</p>
      )}
    </div>
  );
}

function ClarificationPanel({
  canClarify,
  disabledReason,
  message,
  onQuestionChange,
  onSubmit,
  question
}: {
  canClarify: boolean;
  disabledReason: string | null;
  message: string;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
  question: string;
}) {
  const canSubmit =
    canClarify && question.trim().length > 0 && disabledReason === null;

  return (
    <div className="ask-data-clarification-panel" aria-label="Clarification required">
      <h3>Clarification required</h3>
      <p>{message}</p>
      {canClarify ? (
        <>
          <label className="ask-data-question-shell" htmlFor="ask-data-clarification-question">
            <span>Revised question</span>
            <textarea
              id="ask-data-clarification-question"
              rows={4}
              placeholder="Add the missing detail and submit again."
              value={question}
              onChange={(event) => onQuestionChange(event.target.value)}
            />
          </label>
          {disabledReason ? (
            <p className="ask-data-session-message">{disabledReason}</p>
          ) : null}
          <div className="ask-data-composer-actions">
            <button
              type="button"
              className="primary-action-button"
              disabled={!canSubmit}
              onClick={onSubmit}
            >
              Submit clarification
            </button>
          </div>
        </>
      ) : (
        <p className="ask-data-mode-note">
          This query needs refinement. Choose a different approved template or
          ask for a more specific template.
        </p>
      )}
    </div>
  );
}

function VisualizationSuggestion({
  columns,
  rows
}: {
  columns: string[];
  rows: QueryResultRow[];
}) {
  return (
    <div
      className="ask-data-visualization-suggestion"
      aria-label="Visualization suggestion"
    >
      <h4>Visualization suggestion</h4>
      <p>{buildVisualizationSuggestion(columns, rows)}</p>
    </div>
  );
}

function QueryResultTable({
  columns,
  rows
}: {
  columns: string[];
  rows: QueryResultRow[];
}) {
  return (
    <div className="ask-data-result-table-wrap">
      <table className="ask-data-result-table" aria-label="Query results">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>{formatResultValue(valueForColumn(row, column))}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function runningQueryMessage(mode: QueryRunMode): string {
  if (mode === "template") {
    return "Running selected template...";
  }

  if (mode === "clarification") {
    return "Submitting clarification...";
  }

  return "Running free query...";
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
        <p>
          Visualization suggestions now appear with completed results; fuller
          charts remain unavailable until a later visualization milestone.
        </p>
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

function firstRowColumns(rows: QueryResultRow[]): string[] {
  return rows[0] ? Object.keys(rows[0]) : [];
}

function valueForColumn(
  row: QueryResultRow,
  column: string
): QueryRowValue | undefined {
  return Object.prototype.hasOwnProperty.call(row, column)
    ? row[column]
    : undefined;
}

function formatResultValue(value: QueryRowValue | undefined): string {
  if (value === undefined || value === null) {
    return "null";
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }

  return JSON.stringify(value) ?? "";
}

function buildVisualizationSuggestion(
  columns: string[],
  rows: QueryResultRow[]
): string {
  if (columns.length === 0 || rows.length === 0) {
    return "Chart available later when rows are returned.";
  }

  const numericColumn = columns.find((column) =>
    rows.some((row) => {
      const value = valueForColumn(row, column);
      return typeof value === "number" && Number.isFinite(value);
    })
  );

  if (!numericColumn) {
    return "Chart available later: table view is the safest display for this result shape.";
  }

  const labelColumn = columns.find(
    (column) =>
      column !== numericColumn &&
      rows.some((row) => typeof valueForColumn(row, column) === "string")
  );

  if (!labelColumn) {
    return `Chart available later: summarize ${numericColumn}.`;
  }

  return `Chart available later: compare ${numericColumn} by ${labelColumn}.`;
}

function clarificationDisabledReason(
  result: QueryRunResult,
  csrfToken: string | null
): string | null {
  if (!result.query_run_id) {
    return "This clarification cannot be continued. Run a new query instead.";
  }

  if (!csrfToken) {
    return "Refresh your session before submitting clarification.";
  }

  return null;
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

  return "Query could not be run.";
}

function formatClarificationError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Clarification could not be run.";
}
