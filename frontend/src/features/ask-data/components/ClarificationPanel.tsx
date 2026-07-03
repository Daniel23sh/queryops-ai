import {
  BODY_TEXT_CLASS,
  INFO_CARD_CLASS,
  INPUT_LABEL_CLASS,
  PRIMARY_BUTTON_CLASS,
  SESSION_MESSAGE_CLASS,
  SMALL_PANEL_TITLE_CLASS,
  TEXTAREA_CLASS
} from "./askDataStyles";

export function ClarificationPanel({
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
    <div className={INFO_CARD_CLASS} aria-label="Clarification required">
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
