import { useEffect, useMemo, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { clarifyQuery, runQuery } from "../../../api/queries";
import { inferVisualization } from "../../dashboard/visualization";
import type {
  CurrentQueryResult,
  QueryRequestState,
  QueryRunMode,
  QueryRunRequest,
  QueryTemplate,
  ResultDisplayMode
} from "../types";

export function useAskDataRun({
  canRunFreeQuery,
  csrfToken,
  templates
}: {
  canRunFreeQuery: boolean;
  csrfToken: string | null;
  templates: QueryTemplate[];
}) {
  const [requestState, setRequestState] = useState<QueryRequestState>({
    status: "idle"
  });
  const [composerText, setComposerText] = useState("");
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [currentResult, setCurrentResult] = useState<CurrentQueryResult | null>(null);
  const [clarificationText, setClarificationText] = useState("");
  const [clarificationError, setClarificationError] = useState<string | null>(null);
  const [resultDisplayMode, setResultDisplayMode] = useState<ResultDisplayMode>("table");
  const [historyRefreshGeneration, setHistoryRefreshGeneration] = useState(0);
  const mountedRef = useRef(true);
  const requestGenerationRef = useRef(0);
  const requestInFlightRef = useRef(false);
  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) ?? null,
    [selectedTemplateId, templates]
  );
  const composerMode = selectedTemplate ? "template" : "free";
  const running = requestState.status === "running";

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestGenerationRef.current += 1;
    };
  }, []);

  useEffect(() => {
    if (selectedTemplateId && !selectedTemplate) {
      setSelectedTemplateId(null);
      if (!canRunFreeQuery) {
        setComposerText("");
      }
    }
  }, [canRunFreeQuery, selectedTemplate, selectedTemplateId]);

  function selectTemplate(template: QueryTemplate) {
    if (running) return;
    setSelectedTemplateId(template.id);
    setComposerText(template.natural_language_question);
    setRequestState({ status: "idle" });
  }

  function clearTemplate() {
    if (running) return;
    setSelectedTemplateId(null);
    if (!canRunFreeQuery) setComposerText("");
  }

  function updateComposerText(value: string) {
    if (!canRunFreeQuery || running) return;
    setComposerText(value);
    if (selectedTemplate && value !== selectedTemplate.natural_language_question) {
      setSelectedTemplateId(null);
    }
  }

  async function runCurrentQuestion() {
    if (selectedTemplate) {
      return runTemplate(selectedTemplate);
    }
    if (!canRunFreeQuery) return false;
    return runFreeQuestion(composerText);
  }

  async function runTemplate(template: QueryTemplate) {
    selectTemplate(template);
    return executeQuery(
      {
        question: template.natural_language_question,
        template_id: template.id
      },
      "template"
    );
  }

  async function runFreeQuestion(value: string) {
    if (!canRunFreeQuery) return false;
    const question = value.trim();
    if (!question) return false;
    setSelectedTemplateId(null);
    setComposerText(question);
    return executeQuery({ question }, "free");
  }

  function useQuestion(question: string) {
    if (!canRunFreeQuery || running) return;
    setSelectedTemplateId(null);
    setComposerText(question);
    setRequestState({ status: "idle" });
  }

  async function executeQuery(payload: QueryRunRequest, mode: Exclude<QueryRunMode, "clarification">) {
    if (requestInFlightRef.current) return false;
    if (!csrfToken) {
      setRequestState({
        status: "error",
        mode,
        message: "Refresh your session before running a query."
      });
      return false;
    }

    const generation = ++requestGenerationRef.current;
    requestInFlightRef.current = true;
    setClarificationText("");
    setClarificationError(null);
    setRequestState({ status: "running", mode, question: payload.question });

    try {
      const result = await runQuery(payload, csrfToken);
      if (!isCurrent(generation)) return false;
      setCurrentResult({
        question: payload.question,
        originalQuestion: payload.question,
        clarificationResponse: null,
        result,
        generation
      });
      setResultDisplayMode(defaultDisplayMode(result));
      setRequestState({ status: "idle" });
      setHistoryRefreshGeneration((value) => value + 1);
      requestInFlightRef.current = false;
      return true;
    } catch (error: unknown) {
      if (!isCurrent(generation)) return false;
      setRequestState({ status: "error", mode, message: formatQueryRunError(error) });
      requestInFlightRef.current = false;
      return false;
    }
  }

  async function submitClarification() {
    const question = clarificationText.trim();
    if (
      requestInFlightRef.current ||
      !currentResult?.result.clarification_required ||
      !question
    ) {
      return false;
    }

    const queryRunId = currentResult.result.query_run_id;
    if (!queryRunId || !csrfToken) {
      setClarificationError("Refresh your session before submitting clarification.");
      return false;
    }

    const generation = ++requestGenerationRef.current;
    requestInFlightRef.current = true;
    setClarificationError(null);
    setRequestState({ status: "running", mode: "clarification", question });

    try {
      const result = await clarifyQuery(queryRunId, question, csrfToken);
      if (!isCurrent(generation)) return false;
      setCurrentResult({
        question: currentResult.question,
        originalQuestion: currentResult.originalQuestion,
        clarificationResponse: question,
        result,
        generation
      });
      setClarificationText("");
      setResultDisplayMode(defaultDisplayMode(result));
      setRequestState({ status: "idle" });
      setHistoryRefreshGeneration((value) => value + 1);
      requestInFlightRef.current = false;
      return true;
    } catch (error: unknown) {
      if (!isCurrent(generation)) return false;
      setRequestState({ status: "idle" });
      setClarificationError(formatClarificationError(error));
      requestInFlightRef.current = false;
      return false;
    }
  }

  function isCurrent(generation: number) {
    return mountedRef.current && requestGenerationRef.current === generation;
  }

  return {
    clarificationError,
    clarificationText,
    clearTemplate,
    composerMode,
    composerText,
    currentResult,
    historyRefreshGeneration,
    requestState,
    resultDisplayMode,
    runCurrentQuestion,
    runFreeQuestion,
    runTemplate,
    selectTemplate,
    selectedTemplate,
    selectedTemplateId,
    setClarificationText,
    setResultDisplayMode,
    submitClarification,
    updateComposerText,
    useQuestion
  };
}

function defaultDisplayMode(result: { columns: string[]; rows: import("../types").QueryResultRow[] }): ResultDisplayMode {
  if (result.rows.length === 0) return "table";
  return inferVisualization({ columns: result.columns, rows: result.rows }).recommendedType === "table"
    ? "table"
    : "visual";
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
