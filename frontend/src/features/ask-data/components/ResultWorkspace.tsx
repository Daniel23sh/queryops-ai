import type { QueryRunState } from "../types";
import { useAskDataTabs } from "../hooks/useAskDataTabs";
import {
  BODY_TEXT_CLASS,
  EYEBROW_CLASS,
  PANEL_CLASS,
  PANEL_HEADER_CLASS,
  PANEL_TITLE_CLASS
} from "./askDataStyles";
import { DiagnosticsTab } from "./DiagnosticsTab";
import { ResultsTab } from "./ResultsTab";
import { ResultTabs } from "./ResultTabs";
import { SqlTab } from "./SqlTab";
import { SummaryTab } from "./SummaryTab";

export function ResultWorkspace({
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
  const { activeTab, setActiveTab } = useAskDataTabs(canViewTechnicalDetails);

  return (
    <section
      className={`${PANEL_CLASS} gap-5`}
      aria-label="Result workspace"
      aria-labelledby="result-workspace-title"
    >
      <div className={PANEL_HEADER_CLASS}>
        <p className={EYEBROW_CLASS}>Result workspace</p>
        <h2 id="result-workspace-title" className={PANEL_TITLE_CLASS}>
          Result workspace
        </h2>
        <p className={BODY_TEXT_CLASS}>
          Results stay in focus. Summary, SQL, and diagnostics are available only
          where the active role allows them.
        </p>
      </div>

      <ResultTabs
        activeTab={activeTab}
        canViewTechnicalDetails={canViewTechnicalDetails}
        onSelectTab={setActiveTab}
      />

      <div
        className="grid gap-3"
        id={`ask-data-tab-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`ask-data-tab-${activeTab}`}
      >
        {activeTab === "results" ? (
          <ResultsTab
            canClarify={canClarify}
            clarificationDisabledReason={clarificationDisabledReason}
            clarificationQuestion={clarificationQuestion}
            onClarificationQuestionChange={onClarificationQuestionChange}
            onSubmitClarification={onSubmitClarification}
            queryRunState={queryRunState}
          />
        ) : null}

        {activeTab === "summary" ? (
          <SummaryTab queryRunState={queryRunState} />
        ) : null}

        {activeTab === "sql" && canViewTechnicalDetails ? (
          <SqlTab queryRunState={queryRunState} />
        ) : null}

        {activeTab === "diagnostics" && canViewTechnicalDetails ? (
          <DiagnosticsTab queryRunState={queryRunState} />
        ) : null}
      </div>
    </section>
  );
}
