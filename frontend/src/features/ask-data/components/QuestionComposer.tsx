import {
  BODY_TEXT_CLASS,
  EYEBROW_CLASS,
  INPUT_LABEL_CLASS,
  PANEL_CLASS,
  PANEL_TITLE_CLASS,
  PRIMARY_BUTTON_CLASS,
  SESSION_MESSAGE_CLASS,
  SMALL_PANEL_TITLE_CLASS,
  TEXTAREA_CLASS
} from "./askDataStyles";

export function QuestionComposer({
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
      className={`${PANEL_CLASS} gap-4`}
      aria-labelledby="question-composer-title"
    >
      <div className="grid gap-1">
        <p className={EYEBROW_CLASS}>Ask a question</p>
        <h2 id="question-composer-title" className={PANEL_TITLE_CLASS}>
          Ask a question
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
        <div className="grid gap-2 rounded-card border border-app-border bg-app-muted p-4 text-sm leading-6 text-app-subtle">
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
