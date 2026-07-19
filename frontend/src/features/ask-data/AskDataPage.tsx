import { useRef, useState } from "react";

import { hasPermission } from "../../auth/permissions";
import type { AuthUser } from "../../auth/types";
import { ActionPreviewDrawer } from "../actions/components/ActionPreviewDrawer";
import { ActionRecommendationCard } from "../actions/components/ActionRecommendationCard";
import { useActionPreviewFlow } from "../actions/hooks/useActionPreviewFlow";
import { resolveActionSuggestion } from "../actions/utils/resolveActionSuggestion";
import { AskDataCommandBar } from "./components/AskDataCommandBar";
import { AskDataPageHeader } from "./components/AskDataPageHeader";
import { AskDataResultWorkspace } from "./components/AskDataResultWorkspace";
import { QueryHistoryDrawer } from "./components/QueryHistoryDrawer";
import { TemplateDrawer } from "./components/TemplateDrawer";
import { useAskDataRun } from "./hooks/useAskDataRun";
import { useQueryTemplates } from "./hooks/useQueryTemplates";
import { useRecentQueryHistory } from "./hooks/useRecentQueryHistory";

type AskDataPageProps = {
  user: AuthUser;
  csrfToken: string | null;
};

export function AskDataPage({ user, csrfToken }: AskDataPageProps) {
  const canRunFreeQuery = hasPermission(user, "can_run_free_query");
  const canViewTechnicalDetails = hasPermission(user, "can_view_sql");
  const canExport = hasPermission(user, "can_export_results");
  const canSave = hasPermission(user, "can_create_card");
  const canRequestAction = hasPermission(user, "can_request_action");
  const [templatesOpen, setTemplatesOpen] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const commandRef = useRef<HTMLDivElement>(null);
  const { templates, templateLoadError, templateLoadStatus } = useQueryTemplates();
  const ask = useAskDataRun({ canRunFreeQuery, csrfToken, templates });
  const history = useRecentQueryHistory({
    isOpen: historyOpen,
    refreshGeneration: ask.historyRefreshGeneration
  });
  const activeScope =
    user.scopes.find((scope) => scope.isDefault) ?? user.scopes[0] ?? null;
  const scopeLabel = activeScope?.displayName ?? user.department?.name ?? "No active scope";
  const modeLabel = canRunFreeQuery ? "Free and template questions" : "Template-only";
  const successfulActionResult =
    ask.currentResult?.result.status === "succeeded" &&
    ask.currentResult.result.clarification_required === false;
  const actionResolution = resolveActionSuggestion({
    canRequestAction,
    current: ask.currentResult,
    activeScope
  });
  const previewFlow = useActionPreviewFlow({
    csrfToken,
    sourceGeneration: ask.currentResult?.generation ?? null
  });

  return (
    <article className="mx-auto grid w-full max-w-[1120px] gap-5" aria-labelledby="workspace-title">
      <AskDataPageHeader
        modeLabel={modeLabel}
        onOpenHistory={() => setHistoryOpen(true)}
        onOpenTemplates={() => setTemplatesOpen(true)}
        scopeLabel={scopeLabel}
      />

      <AskDataCommandBar
        ref={commandRef}
        canRunFreeQuery={canRunFreeQuery}
        composerText={ask.composerText}
        csrfToken={csrfToken}
        onChange={ask.updateComposerText}
        onChooseTemplate={() => setTemplatesOpen(true)}
        onClearTemplate={ask.clearTemplate}
        onRun={() => void ask.runCurrentQuestion()}
        requestState={ask.requestState}
        selectedTemplate={ask.selectedTemplate}
      />

      <AskDataResultWorkspace
        actionRecommendation={
          actionResolution.status === "hidden" ? null : (
            <ActionRecommendationCard
              onPreview={(resolution) => void previewFlow.openPreview(resolution)}
              resolution={actionResolution}
              scopeLabel={scopeLabel}
            />
          )
        }
        canClarify={canRunFreeQuery}
        canExport={Boolean(successfulActionResult && canExport)}
        canSave={Boolean(successfulActionResult && canSave)}
        canViewTechnicalDetails={canViewTechnicalDetails}
        clarificationError={ask.clarificationError}
        clarificationText={ask.clarificationText}
        csrfToken={csrfToken}
        current={ask.currentResult}
        onClarificationChange={ask.setClarificationText}
        onDisplayModeChange={ask.setResultDisplayMode}
        onSubmitClarification={() => void ask.submitClarification()}
        requestState={ask.requestState}
        resultDisplayMode={ask.resultDisplayMode}
      />

      {previewFlow.flow ? (
        <ActionPreviewDrawer
          flow={previewFlow.flow}
          onClose={previewFlow.close}
          onReasonChange={previewFlow.setReason}
          onRecreate={previewFlow.recreate}
          onSubmit={() => void previewFlow.submit()}
          role={user.role}
        />
      ) : null}

      {templatesOpen ? (
        <TemplateDrawer
          error={templateLoadError}
          focusTargetRef={commandRef}
          onClose={() => setTemplatesOpen(false)}
          onSelect={ask.selectTemplate}
          selectedTemplateId={ask.selectedTemplateId}
          status={templateLoadStatus}
          templates={templates}
        />
      ) : null}

      {historyOpen ? (
        <QueryHistoryDrawer
          canRunFreeQuery={canRunFreeQuery}
          error={history.error}
          focusTargetRef={commandRef}
          items={history.items}
          onClose={() => setHistoryOpen(false)}
          onRunFreeQuestion={(question) => void ask.runFreeQuestion(question)}
          onRunTemplate={(template) => void ask.runTemplate(template)}
          onSelectTemplate={ask.selectTemplate}
          onUseQuestion={ask.useQuestion}
          running={ask.requestState.status === "running"}
          status={history.status}
          templates={templates}
        />
      ) : null}
    </article>
  );
}
