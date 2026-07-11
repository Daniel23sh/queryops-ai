import type { AuthUser } from "../../auth/types";
import { formatRole } from "../../lib/format";
import { AskDataHeader } from "./components/AskDataHeader";
import { InsightsPanel } from "./components/InsightsPanel";
import { QuestionComposer } from "./components/QuestionComposer";
import { QueryResultExportButton } from "./components/QueryResultExportButton";
import { ResultWorkspace } from "./components/ResultWorkspace";
import { SaveAsCardPanel } from "./components/SaveAsCardPanel";
import { TemplateCatalog } from "./components/TemplateCatalog";
import { useAskDataRun } from "./hooks/useAskDataRun";
import { useQueryTemplates } from "./hooks/useQueryTemplates";
import { clarificationDisabledReason } from "./utils/resultSummary";

type AskDataPageProps = {
  user: AuthUser;
  csrfToken: string | null;
};

export function AskDataPage({ user, csrfToken }: AskDataPageProps) {
  const canRunFreeQuery = user.permissions.includes("can_run_free_query");
  const canViewTechnicalDetails = user.permissions.includes("can_view_sql");
  const isAdmin = user.role === "admin";
  const {
    selectedTemplate,
    selectedTemplateId,
    setSelectedTemplateId,
    templateCategories,
    templateLoadError,
    templateLoadStatus
  } = useQueryTemplates();
  const {
    clarificationQuestion,
    freeQuestion,
    handleRunFreeQuery,
    handleRunSelectedTemplate,
    handleSubmitClarification,
    queryRunState,
    setClarificationQuestion,
    setFreeQuestion
  } = useAskDataRun({ csrfToken, selectedTemplate });
  const scopeLabel =
    isAdmin ? "Global admin scope" : user.department?.name ?? "No scope";
  const modeLabel = canRunFreeQuery ? "Free query enabled" : "Template-only mode";
  const modeDescription = canRunFreeQuery
    ? "Ask governed questions with backend authorization applied to every run."
    : "Use approved templates only; free-query access is not enabled for this role.";

  return (
    <article
      className="grid min-h-[420px] gap-5"
      aria-labelledby="workspace-title"
    >
      <AskDataHeader
        modeDescription={modeDescription}
        modeLabel={modeLabel}
        roleLabel={formatRole(user.role)}
        scopeLabel={scopeLabel}
        showAdminGlobalIndicator={isAdmin}
      />

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(280px,0.34fr)_minmax(0,1fr)] 2xl:grid-cols-[minmax(300px,0.32fr)_minmax(0,1fr)]">
        <TemplateCatalog
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
          aria-label="Ask Data command workspace"
        >
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
          <ResultWorkspace
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
          <QueryResultExportButton
            csrfToken={csrfToken}
            queryRunState={queryRunState}
            user={user}
          />
          <SaveAsCardPanel
            csrfToken={csrfToken}
            queryRunState={queryRunState}
            user={user}
          />
          <InsightsPanel />
        </section>
      </div>
    </article>
  );
}
