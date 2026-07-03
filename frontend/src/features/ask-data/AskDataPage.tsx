import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { listQueryTemplates } from "../../api/queryTemplates";
import { clarifyQuery, runQuery } from "../../api/queries";
import type { AuthUser } from "../../auth/types";
import type {
  QueryResultRow,
  QueryRowValue,
  QueryRunResult,
  QuerySelfCorrectionMetadata,
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

type DiagnosticItem = {
  label: string;
  value: boolean | number | string | null | undefined;
};

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

const EYEBROW_CLASS = "m-0 text-xs font-bold uppercase tracking-normal text-brand-accent";
const PANEL_CLASS =
  "grid gap-4 rounded-card border border-app-border bg-app-surface p-5 shadow-sm ring-1 ring-white/70";
const PANEL_HEADER_CLASS = "grid gap-1";
const PANEL_TITLE_CLASS = "m-0 text-lg font-bold tracking-normal text-slate-950";
const SMALL_PANEL_TITLE_CLASS = "m-0 text-base font-bold tracking-normal text-slate-950";
const BODY_TEXT_CLASS = "m-0 text-sm leading-6 text-app-subtle";
const MUTED_CARD_CLASS =
  "grid gap-2 rounded-card border border-app-border bg-app-muted p-4 text-sm leading-6 text-app-subtle";
const INFO_CARD_CLASS =
  "grid gap-2 rounded-card border border-blue-200 bg-blue-50/80 p-4 text-sm leading-6 text-app-subtle";
const WARNING_CARD_CLASS =
  "rounded-card border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900";
const ERROR_CARD_CLASS =
  "m-0 rounded-card border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-800";
const SESSION_MESSAGE_CLASS = "m-0 text-sm leading-5 text-amber-700";
const INPUT_LABEL_CLASS = "grid gap-2 text-sm font-bold text-slate-700";
const TEXTAREA_CLASS =
  "min-h-28 w-full resize-y rounded-control border border-slate-300 bg-app-surface px-3.5 py-3 text-sm leading-6 text-app-text outline-none transition placeholder:text-app-faint hover:border-slate-400 focus:border-brand-primary focus:shadow-focus disabled:cursor-not-allowed disabled:opacity-60";
const PRIMARY_BUTTON_CLASS =
  "qops-button-primary qops-focus-ring transition hover:shadow-card active:translate-y-px";
const SECONDARY_BUTTON_CLASS =
  "qops-button-secondary qops-focus-ring transition hover:shadow-sm active:translate-y-px disabled:hover:border-app-border disabled:hover:text-app-text disabled:hover:shadow-none disabled:active:translate-y-0";
const STATUS_TILE_CLASS =
  "inline-flex min-h-9 items-center gap-1.5 rounded-control border border-app-border bg-white/80 px-3 text-xs font-bold text-app-text shadow-sm";

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
  const modeLabel = canRunFreeQuery ? "Free query enabled" : "Template-only mode";
  const modeDescription = canRunFreeQuery
    ? "Ask governed questions with backend authorization applied to every run."
    : "Use approved templates only; free-query access is not enabled for this role.";

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
    <article
      className="grid min-h-[420px] gap-5"
      aria-labelledby="workspace-title"
    >
      <header className="overflow-hidden rounded-card border border-app-border bg-app-surface/95 p-5 shadow-card ring-1 ring-white/80 sm:p-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-3xl">
            <p className={EYEBROW_CLASS}>Governed analytics</p>
            <h1
              id="workspace-title"
              className="mt-2 text-[clamp(2rem,4vw,3rem)] font-bold leading-tight tracking-normal text-slate-950"
            >
              Ask Data
            </h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-app-subtle">
              Ask approved operational questions, inspect results, and keep
              technical detail safely scoped to the right roles.
            </p>
          </div>
          <ContextChips
            modeDescription={modeDescription}
            modeLabel={modeLabel}
            roleLabel={formatRole(user.role)}
            scopeLabel={scopeLabel}
            showAdminGlobalIndicator={isAdmin}
          />
        </div>
      </header>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(250px,0.42fr)_minmax(0,1fr)] 2xl:grid-cols-[minmax(280px,0.38fr)_minmax(0,1fr)]">
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
          className="grid min-w-0 gap-4"
          aria-label="Ask Data workspace"
        >
          <section className={`${PANEL_CLASS} gap-5`} aria-labelledby="question-composer-title">
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
            <InsightPanel />
          </section>
        </section>
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
    <section
      className={`${PANEL_CLASS} gap-3 xl:sticky xl:top-6`}
      aria-label="Ask Data templates"
    >
      <div className={PANEL_HEADER_CLASS}>
        <p className={EYEBROW_CLASS}>Template catalog</p>
        <h2 className={PANEL_TITLE_CLASS}>Approved questions</h2>
        <p className={BODY_TEXT_CLASS}>
          Start from a governed template, then run it with your current scope.
        </p>
      </div>

      {status === "loading" ? (
        <p className={`${INFO_CARD_CLASS} py-3`} role="status">
          <span className="font-bold text-app-text">Loading query templates...</span>
          <span className="block text-app-subtle">
            The approved template catalog is being prepared for this role.
          </span>
        </p>
      ) : null}

      {status === "error" ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          <strong className="block text-red-900">Template catalog unavailable</strong>
          <span>{error ?? "Query templates could not be loaded."}</span>
        </p>
      ) : null}

      {status === "loaded" && !hasTemplates ? (
        <p className={MUTED_CARD_CLASS}>
          <strong className="text-app-text">No query templates are available yet.</strong>
          <span>Approved templates will appear here when they are published.</span>
        </p>
      ) : null}

      {status === "loaded" && hasTemplates ? (
        <>
          <div
            className="flex gap-2 overflow-x-auto pb-1"
            aria-label="Query template categories"
          >
            {categories.map((group) => (
              <button
                key={group.category}
                type="button"
                className="qops-focus-ring inline-flex min-h-9 shrink-0 items-center rounded-control border border-emerald-100 bg-emerald-50 px-3 text-xs font-bold text-emerald-800 transition hover:border-emerald-200 hover:bg-emerald-100"
                onClick={() => onSelectTemplate(group.templates[0].id)}
              >
                {group.category}
              </button>
            ))}
          </div>

          <ul
            className="grid max-h-[26rem] list-none gap-2 overflow-y-auto pr-1"
            aria-label="Query templates"
          >
            {categories.flatMap((group) =>
              group.templates.map((template) => (
                <li key={template.id}>
                  <button
                    type="button"
                    className={`qops-focus-ring grid w-full gap-1 rounded-card border p-3 text-left transition hover:border-brand-primary hover:bg-blue-50 hover:shadow-sm ${
                      template.id === selectedTemplateId
                        ? "border-brand-primary bg-blue-50 shadow-sm ring-1 ring-blue-100"
                        : "border-app-border bg-app-muted"
                    }`}
                    aria-pressed={template.id === selectedTemplateId}
                    data-selected={template.id === selectedTemplateId ? "true" : "false"}
                    onClick={() => onSelectTemplate(template.id)}
                  >
                    <strong
                      className={
                        template.id === selectedTemplateId
                          ? "text-brand-accent-strong"
                          : "text-app-text"
                      }
                    >
                      {template.title}
                    </strong>
                    <p className="m-0 line-clamp-2 text-xs leading-5 text-app-subtle">
                      {template.description}
                    </p>
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
    <div
      className="grid gap-3 rounded-card border border-app-border bg-app-surface p-3.5 text-sm leading-6 text-app-subtle shadow-sm"
      aria-label="Selected query template"
    >
      <h3 className="m-0 text-sm font-bold tracking-normal text-slate-950">
        Selected template
      </h3>
      {template ? (
        <>
          <div className="grid gap-1">
            <strong className="text-app-text">{template.title}</strong>
            <p className="m-0 text-xs leading-5 text-app-subtle">
              {template.description}
            </p>
          </div>
          <p className="m-0 rounded-card border border-blue-100 bg-blue-50/80 px-3 py-2 text-xs leading-5 text-app-subtle">
            {template.natural_language_question}
          </p>
          {template.parameters.length > 0 ? (
            <p className="m-0 border-l-4 border-brand-primary pl-3 text-xs leading-5 text-app-subtle">
              Custom parameters are not supported yet; backend template defaults
              will be used.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              className={`${PRIMARY_BUTTON_CLASS} w-full sm:w-auto xl:w-full`}
              disabled={!canRunTemplate}
              onClick={onRunSelectedTemplate}
            >
              {running ? "Running template..." : "Run selected template"}
            </button>
          </div>
          {disabledReason ? (
            <p className={SESSION_MESSAGE_CLASS}>{disabledReason}</p>
          ) : null}
        </>
      ) : (
        <p className={BODY_TEXT_CLASS}>
          Select a template to view its default question and scope.
        </p>
      )}
    </div>
  );
}

function ContextChips({
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
    <div className="grid gap-3 lg:max-w-[28rem]" aria-label="Ask Data access summary">
      <dl
        className="m-0 flex flex-wrap gap-2"
      >
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Mode</dt>
          <dd className="m-0">{modeLabel}</dd>
        </div>
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Role</dt>
          <dd className="m-0">{roleLabel}</dd>
        </div>
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Scope</dt>
          <dd className="m-0">{scopeLabel}</dd>
        </div>
      </dl>
      <p className="m-0 max-w-md text-sm leading-6 text-app-subtle">
        {modeDescription}
      </p>
      {showAdminGlobalIndicator ? (
        <p className="m-0 rounded-control border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs font-bold leading-5 text-emerald-800">
          Admin global scope indicator. Query runs still use backend authorization.
        </p>
      ) : null}
    </div>
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
    <section
      className="grid gap-3 border-b border-app-border pb-5"
      aria-labelledby="question-composer-title"
    >
      <div className="grid gap-1">
        <p className={EYEBROW_CLASS}>Ask a question</p>
        <h2 id="question-composer-title" className={PANEL_TITLE_CLASS}>
          Query workspace
        </h2>
        <p className={BODY_TEXT_CLASS}>
          Run a selected template or ask a free-form question if your role allows it.
        </p>
      </div>
      {canRunFreeQuery ? (
        <>
          <label className={INPUT_LABEL_CLASS} htmlFor="ask-data-free-question">
            <span>Free question</span>
            <textarea
              id="ask-data-free-question"
              className={TEXTAREA_CLASS}
              rows={4}
              placeholder="Ask a governed data question."
              value={freeQuestion}
              disabled={running}
              onChange={(event) => onFreeQuestionChange(event.target.value)}
            />
          </label>
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              disabled={!canRunFreeQueryNow}
              onClick={onRunFreeQuery}
            >
              {running ? "Running query..." : "Run free query"}
            </button>
          </div>
          <p className="m-0 border-l-4 border-brand-primary pl-3.5 text-sm leading-6 text-app-subtle">
            Free questions are sent to the Query API using your current role and
            access scope.
          </p>
          {runDisabledReason ? (
            <p className={SESSION_MESSAGE_CLASS}>{runDisabledReason}</p>
          ) : null}
        </>
      ) : (
        <div className="grid gap-2 rounded-card border border-blue-100 bg-blue-50/70 p-4 text-sm leading-6 text-app-subtle">
          <h3 className={SMALL_PANEL_TITLE_CLASS}>Template-only mode</h3>
          <p className={BODY_TEXT_CLASS}>
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
    <section className="grid gap-4" aria-labelledby="result-placeholder-title">
      <div className={PANEL_HEADER_CLASS}>
        <p className={EYEBROW_CLASS}>Result workspace</p>
        <h2 id="result-placeholder-title" className={PANEL_TITLE_CLASS}>
          Results and context
        </h2>
        <p className={BODY_TEXT_CLASS}>
          Results stay in focus. Summary, SQL, and diagnostics are available only
          where the active role allows them.
        </p>
      </div>

      <ResultTabs
        activeTab={activeVisibleTab}
        canViewTechnicalDetails={canViewTechnicalDetails}
        onSelectTab={setActiveTab}
      />

      <div
        className="grid gap-3"
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
          <DiagnosticsTabContent queryRunState={queryRunState} />
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
    <div
      className="grid grid-cols-2 gap-2 rounded-card bg-slate-100 p-1 sm:flex sm:flex-wrap"
      role="tablist"
      aria-label="Ask Data result views"
    >
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
            className={`qops-focus-ring inline-flex min-h-11 items-center justify-center rounded-control border px-3.5 text-sm font-bold transition sm:w-auto ${
              activeTab === tab.id
                ? "border-white bg-app-surface text-app-text shadow-sm"
                : "border-transparent bg-transparent text-app-subtle hover:bg-white/80 hover:text-brand-primary"
            }`}
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
        <div
          className="grid min-h-56 place-items-center rounded-card border border-dashed border-slate-300 bg-gradient-to-br from-white to-blue-50/50 p-6 text-center"
          aria-label="Result table placeholder"
        >
          <div className="max-w-md">
            <h3 className="m-0 text-base font-bold text-app-text">Ready for a query</h3>
            <p className="mt-2 text-sm leading-6 text-app-subtle">
              Choose an approved template or ask a governed question. Results,
              warnings, and clarification prompts will appear here.
            </p>
          </div>
        </div>
      ) : null}

      {queryRunState.status === "running" ? (
        <p className={`${INFO_CARD_CLASS} min-h-32 place-content-center border-blue-200`} role="status">
          <span className="font-bold text-app-text">
            {runningQueryMessage(queryRunState.mode)}
          </span>
          <span className="block text-app-subtle">
            Results will appear here when the query finishes.
          </span>
        </p>
      ) : null}

      {queryRunState.status === "error" ? (
        <p className={ERROR_CARD_CLASS} role="alert">
          <strong className="block text-red-900">Request failed</strong>
          <span>{queryRunState.message}</span>
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
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Summary</h3>
        <p className={BODY_TEXT_CLASS}>{queryRunState.result.message}</p>
        <p className={BODY_TEXT_CLASS}>Question: {queryRunState.question}</p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Summary</h3>
        <p className={BODY_TEXT_CLASS}>{runningQueryMessage(queryRunState.mode)}</p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Summary</h3>
        <p className={BODY_TEXT_CLASS}>
          The latest request ended with a safe error state.
        </p>
      </div>
    );
  }

  return (
    <div className={MUTED_CARD_CLASS}>
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Summary</h3>
      <p className={BODY_TEXT_CLASS}>
        Run a selected template or free question to populate the result summary.
      </p>
    </div>
  );
}

function SqlTabContent({ queryRunState }: { queryRunState: QueryRunState }) {
  if (queryRunState.status === "idle") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>Run a query to inspect SQL for this role.</p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>
          SQL will be available after the query finishes, if the backend returns it.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>
          SQL is not available because the latest request ended with a safe error state.
        </p>
      </div>
    );
  }

  const generatedSql = safeSqlText(queryRunState.result.generated_sql);
  const executedSql = safeSqlText(queryRunState.result.executed_sql);

  if (!generatedSql && !executedSql) {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
        <p className={BODY_TEXT_CLASS}>SQL is not available for this query result.</p>
      </div>
    );
  }

  return (
    <div className={MUTED_CARD_CLASS}>
      <h3 className={SMALL_PANEL_TITLE_CLASS}>SQL</h3>
      <p className={BODY_TEXT_CLASS}>
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
    <section className="grid gap-2" aria-label={label}>
      <h4 className="m-0 text-sm font-bold text-app-text">{label}</h4>
      <pre className="m-0 overflow-x-auto whitespace-pre-wrap rounded-card border border-slate-300 bg-app-surface p-3 font-mono text-xs leading-6 text-app-text">
        <code>{sql}</code>
      </pre>
    </section>
  );
}

function DiagnosticsTabContent({ queryRunState }: { queryRunState: QueryRunState }) {
  if (queryRunState.status === "idle") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Run a query to inspect diagnostics for this role.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Diagnostics will be available after the query finishes.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Diagnostics are not available because the latest request ended with a
          safe error state.
        </p>
      </div>
    );
  }

  const { result } = queryRunState;
  const metadata = result.metadata;
  const validation = metadata.validation;
  const execution = metadata.execution;
  const selfCorrection = metadata.self_correction;
  const safeWarnings = result.warnings
    .map(safeDiagnosticText)
    .filter((warning): warning is string => warning !== null);

  return (
    <div className={MUTED_CARD_CLASS}>
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
      <p className={BODY_TEXT_CLASS}>
        Technical diagnostics are built from safe query metadata. SQL text stays
        in the SQL tab.
      </p>

      <DiagnosticSection
        title="Run"
        items={[
          { label: "Query run ID", value: result.query_run_id },
          { label: "Status", value: result.status },
          { label: "Error code", value: result.error_code },
          {
            label: "Clarification required",
            value: result.clarification_required
          }
        ]}
      />

      <DiagnosticSection
        title="Generation"
        items={[
          { label: "Provider", value: metadata.provider },
          { label: "Model", value: metadata.model },
          { label: "Template", value: metadata.template_id },
          { label: "Scope", value: metadata.scope_type },
          {
            label: "Referenced tables",
            value: formatReferencedTables(metadata.referenced_tables)
          }
        ]}
      />

      {validation ? (
        <DiagnosticSection
          title="Validation"
          items={[
            {
              label: "Validation status",
              value: formatValidationStatus(validation.valid)
            },
            { label: "Validation error code", value: validation.error_code }
          ]}
        />
      ) : null}

      {execution ? (
        <DiagnosticSection
          title="Execution"
          items={[
            { label: "Execution status", value: execution.status },
            { label: "Execution error code", value: execution.error_code },
            { label: "Execution row count", value: execution.row_count },
            {
              label: "Execution duration",
              value:
                typeof execution.duration_ms === "number"
                  ? `${execution.duration_ms} ms`
                  : null
            },
            { label: "Execution truncated", value: execution.truncated }
          ]}
        />
      ) : null}

      {selfCorrection ? (
        <DiagnosticSection
          title="Self-correction"
          items={selfCorrectionItems(selfCorrection)}
        />
      ) : null}

      {safeWarnings.length > 0 ? (
        <section
          className="grid gap-2.5"
          aria-label="Diagnostic warnings"
        >
          <h4 className="m-0 text-sm font-bold text-app-text">Warnings</h4>
          <ul className="m-0 grid gap-1.5 rounded-card border border-amber-200 bg-amber-50 py-3 pl-8 pr-3.5 text-sm leading-6 text-amber-900">
            {safeWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function DiagnosticSection({
  items,
  title
}: {
  items: DiagnosticItem[];
  title: string;
}) {
  const visibleItems = items
    .map((item) => ({
      label: item.label,
      value: formatDiagnosticValue(item.value)
    }))
    .filter((item): item is { label: string; value: string } => item.value !== null);

  if (visibleItems.length === 0) {
    return null;
  }

  return (
    <section className="grid gap-2.5" aria-label={`${title} diagnostics`}>
      <h4 className="m-0 text-sm font-bold text-app-text">{title}</h4>
      <dl className="m-0 grid gap-2.5 md:grid-cols-2">
        {visibleItems.map((item) => (
          <div
            key={item.label}
            className="grid gap-1 rounded-card border border-app-border bg-app-surface px-3 py-2.5"
          >
            <dt className="text-xs font-bold uppercase text-app-faint">
              {item.label}
            </dt>
            <dd className="m-0 text-sm font-bold leading-6 text-app-text [overflow-wrap:anywhere]">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function safeSqlText(sql: string | null | undefined): string | null {
  if (typeof sql !== "string") {
    return null;
  }

  const trimmedSql = sql.trim();
  return trimmedSql.length > 0 ? trimmedSql : null;
}

function safeDiagnosticText(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }

  const trimmedValue = value.trim();
  if (!trimmedValue || containsSqlLikeText(trimmedValue)) {
    return null;
  }

  return trimmedValue;
}

function formatDiagnosticValue(
  value: boolean | number | string | null | undefined
): string | null {
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }

  if (typeof value === "number") {
    return String(value);
  }

  return safeDiagnosticText(value);
}

function formatReferencedTables(tables: string[] | undefined): string | null {
  if (!Array.isArray(tables)) {
    return null;
  }

  const safeTables = tables
    .map(safeDiagnosticText)
    .filter((table): table is string => table !== null);

  return safeTables.length > 0 ? safeTables.join(", ") : null;
}

function formatValidationStatus(valid: boolean | null): string | null {
  if (valid === true) {
    return "Valid";
  }

  if (valid === false) {
    return "Invalid";
  }

  return null;
}

function selfCorrectionItems(
  selfCorrection: QuerySelfCorrectionMetadata
): DiagnosticItem[] {
  return [
    {
      label: "Correction attempted",
      value: selfCorrection.attempted
    },
    {
      label: "Correction status",
      value: formatSelfCorrectionStatus(selfCorrection)
    },
    {
      label: "Original correction error code",
      value: selfCorrection.original_error_code
    },
    {
      label: "Final correction error code",
      value: selfCorrection.final_error_code
    }
  ];
}

function formatSelfCorrectionStatus(
  selfCorrection: QuerySelfCorrectionMetadata
): string | null {
  if (selfCorrection.attempted === false) {
    return "Not attempted";
  }

  if (selfCorrection.attempted !== true) {
    return null;
  }

  if (selfCorrection.succeeded === true) {
    return "Succeeded";
  }

  if (selfCorrection.succeeded === false) {
    return "Failed";
  }

  return "Attempted";
}

function containsSqlLikeText(value: string): boolean {
  return /\b(select|with|insert|update|delete|drop|alter|create|truncate)\b/i.test(
    value
  );
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
    <div
      className="grid gap-4 rounded-card border border-app-border bg-app-surface p-4 text-sm leading-6 text-app-subtle shadow-sm"
      aria-label="Query result summary"
    >
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Query result</h3>
      <p className={BODY_TEXT_CLASS}>{result.message}</p>
      <p className={BODY_TEXT_CLASS}>Question: {question}</p>
      <dl className="m-0 grid gap-2.5 md:grid-cols-3">
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Status</dt>
          <dd className="m-0 font-bold text-app-text">Status: {result.status}</dd>
        </div>
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Rows</dt>
          <dd className="m-0 font-bold text-app-text">{result.row_count}</dd>
        </div>
        <div className="grid gap-1 rounded-card border border-app-border bg-app-muted p-3">
          <dt className="text-xs font-bold uppercase text-app-faint">Duration</dt>
          <dd className="m-0 font-bold text-app-text">{result.duration_ms} ms</dd>
        </div>
      </dl>

      {result.truncated || result.warnings.length > 0 ? (
        <div className="grid gap-2.5">
          {result.truncated ? (
            <p className={`${WARNING_CARD_CLASS} grid gap-1`}>
              <strong className="text-sm text-amber-950">Results truncated</strong>
              <span>Only the returned rows are shown in this preview.</span>
            </p>
          ) : null}
          {result.warnings.length > 0 ? (
            <div
              className={`${WARNING_CARD_CLASS} grid gap-2`}
              aria-label="Query warnings"
            >
              <h4 className="m-0 text-sm font-bold text-amber-950">Warnings</h4>
              <ul className="m-0 grid gap-1.5 pl-5">
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
        <p className={`${WARNING_CARD_CLASS} m-0`}>No rows returned.</p>
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
    <div
      className={`${INFO_CARD_CLASS} border-blue-200 bg-blue-50`}
      aria-label="Clarification required"
    >
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Clarification required</h3>
      <p className={BODY_TEXT_CLASS}>{message}</p>
      {canClarify ? (
        <>
          <label
            className={INPUT_LABEL_CLASS}
            htmlFor="ask-data-clarification-question"
          >
            <span>Revised question</span>
            <textarea
              id="ask-data-clarification-question"
              className={TEXTAREA_CLASS}
              rows={4}
              placeholder="Add the missing detail and submit again."
              value={question}
              onChange={(event) => onQuestionChange(event.target.value)}
            />
          </label>
          {disabledReason ? (
            <p className={SESSION_MESSAGE_CLASS}>{disabledReason}</p>
          ) : null}
          <div className="flex flex-wrap gap-2.5">
            <button
              type="button"
              className={PRIMARY_BUTTON_CLASS}
              disabled={!canSubmit}
              onClick={onSubmit}
            >
              Submit clarification
            </button>
          </div>
        </>
      ) : (
        <p className="m-0 border-l-4 border-brand-primary pl-3.5 text-sm leading-6 text-app-subtle">
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
      className="grid gap-1.5 rounded-card border border-blue-200 bg-blue-50/80 px-3.5 py-3 text-sm leading-6 text-app-subtle"
      aria-label="Visualization suggestion"
    >
      <h4 className="m-0 text-sm font-bold text-app-text">
        Visualization suggestion
      </h4>
      <p className="m-0">{buildVisualizationSuggestion(columns, rows)}</p>
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
    <div className="overflow-x-auto rounded-card border border-app-border bg-app-surface shadow-sm">
      <table
        className="w-full min-w-[520px] border-collapse text-left text-sm tabular-nums text-app-text"
        aria-label="Query results"
      >
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className="sticky top-0 border-b border-app-border bg-blue-50 px-3 py-2.5 font-bold text-slate-700"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="even:bg-slate-50/70 hover:bg-blue-50/70 [&:last-child>td]:border-b-0"
            >
              {columns.map((column) => (
                <td
                  key={column}
                  className="whitespace-nowrap border-b border-app-border px-3 py-2.5 align-top text-app-subtle"
                >
                  {formatResultValue(valueForColumn(row, column))}
                </td>
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
    <section
      className="rounded-card border border-app-border bg-app-muted/80 p-1"
      aria-label="Ask Data insights"
    >
      <details className="group">
        <summary className="qops-focus-ring flex min-h-12 cursor-pointer list-none items-center justify-between gap-3 rounded-control px-3 py-2 text-sm font-bold text-app-text marker:hidden">
          <span>Insights & next steps</span>
          <span className="text-xs font-bold uppercase text-app-faint group-open:hidden">
            Open
          </span>
          <span className="hidden text-xs font-bold uppercase text-app-faint group-open:inline">
            Close
          </span>
        </summary>

        <div className="grid gap-3 px-3 pb-3 pt-1">
          <div className="grid gap-1 rounded-card border border-app-border bg-app-surface p-3">
            <h3 className="m-0 text-sm font-bold tracking-normal text-slate-950">
              Insights
            </h3>
            <p className={BODY_TEXT_CLASS}>
              Result interpretation, assumptions, and visualization guidance stay
              close to the result workspace without occupying a permanent column.
            </p>
          </div>

          <div className="grid gap-1 rounded-card border border-app-border bg-app-surface p-3">
            <h3 className="m-0 text-sm font-bold tracking-normal text-slate-950">
              Suggested Action
            </h3>
            <p className={BODY_TEXT_CLASS}>
              Operational recommendations remain disabled until the actions
              milestone defines preview, approval, and audit behavior.
            </p>
          </div>

          <div
            className="grid gap-2 sm:grid-cols-3"
            aria-label="Future operational actions"
          >
            {FUTURE_OPERATION_PLACEHOLDERS.map((placeholder) => (
              <div
                className="grid gap-2 rounded-card border border-app-border bg-app-surface p-3"
                key={placeholder.label}
              >
                <button
                  type="button"
                  className={`${SECONDARY_BUTTON_CLASS} w-full`}
                  disabled
                >
                  {placeholder.label}
                </button>
                <div>
                  <strong className="mb-1 block text-xs font-bold text-app-text">
                    {placeholder.milestone}
                  </strong>
                  <p className="m-0 text-xs leading-5 text-app-subtle">
                    {placeholder.summary}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </details>
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
