import { useState } from "react";

import { ApiError } from "../../../api/client";
import { clarifyQuery, runQuery } from "../../../api/queries";
import type { QueryRunState, QueryTemplate } from "../types";

export function useAskDataRun({
  csrfToken,
  selectedTemplate
}: {
  csrfToken: string | null;
  selectedTemplate: QueryTemplate | null;
}) {
  const [queryRunState, setQueryRunState] = useState<QueryRunState>({
    status: "idle"
  });
  const [freeQuestion, setFreeQuestion] = useState("");
  const [clarificationQuestion, setClarificationQuestion] = useState("");

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

  return {
    clarificationQuestion,
    freeQuestion,
    handleRunFreeQuery,
    handleRunSelectedTemplate,
    handleSubmitClarification,
    queryRunState,
    setClarificationQuestion,
    setFreeQuestion
  };
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
