import type { QueryRunState } from "../types";
import { runningQueryMessage } from "../utils/resultSummary";
import {
  BODY_TEXT_CLASS,
  MUTED_CARD_CLASS,
  SMALL_PANEL_TITLE_CLASS
} from "./askDataStyles";

export function SummaryTab({ queryRunState }: { queryRunState: QueryRunState }) {
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
