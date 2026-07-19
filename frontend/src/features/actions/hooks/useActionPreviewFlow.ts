import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createActionPreview, submitActionRequest } from "../../../api/actions";
import { ApiError } from "../../../api/client";
import type { ActionDetail, ActionResolution } from "../types";

type AvailableResolution = Extract<ActionResolution, { status: "available" }>;
type SourceResolution = AvailableResolution & { previewRequestSourceGeneration: number };

export type ActionPreviewFlow = {
  isOpen: boolean;
  phase: "creating" | "ready" | "preview-error" | "submitting" | "submit-error";
  resolution: SourceResolution;
  preview: ActionDetail | null;
  reason: string;
  error: string | null;
};

export function useActionPreviewFlow({
  csrfToken,
  sourceGeneration
}: {
  csrfToken: string | null;
  sourceGeneration: number | null;
}) {
  const [flow, setFlow] = useState<ActionPreviewFlow | null>(null);
  const tokenRef = useRef(0);
  const inFlightRef = useRef(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (flow && sourceGeneration !== flow.resolution.previewRequestSourceGeneration) {
      tokenRef.current += 1;
      inFlightRef.current = false;
      setFlow(null);
    }
  }, [flow, sourceGeneration]);

  async function openPreview(resolution: AvailableResolution) {
    if (inFlightRef.current || sourceGeneration === null) return;
    const guardedResolution = {
      ...resolution,
      previewRequestSourceGeneration: sourceGeneration
    };
    if (!csrfToken) {
      setFlow({
        isOpen: true,
        phase: "preview-error",
        resolution: guardedResolution,
        preview: null,
        reason: resolution.previewRequest.reason,
        error: "Refresh your session before creating an action preview."
      });
      return;
    }
    const token = ++tokenRef.current;
    inFlightRef.current = true;
    setFlow({
      isOpen: true,
      phase: "creating",
      resolution: guardedResolution,
      preview: null,
      reason: resolution.previewRequest.reason,
      error: null
    });
    try {
      const preview = await createActionPreview(resolution.previewRequest, csrfToken);
      if (tokenRef.current !== token) return;
      setFlow((current) =>
        current
          ? { ...current, phase: "ready", preview, error: null }
          : current
      );
    } catch (error: unknown) {
      if (tokenRef.current !== token) return;
      setFlow((current) =>
        current
          ? {
              ...current,
              phase: "preview-error",
              error: safeError(error, "The action preview could not be created safely.")
            }
          : current
      );
    } finally {
      if (tokenRef.current === token) inFlightRef.current = false;
    }
  }

  async function submit() {
    if (
      !flow?.preview ||
      inFlightRef.current ||
      !csrfToken ||
      !flow.reason.trim() ||
      previewExpired(flow.preview)
    ) {
      return;
    }
    const token = ++tokenRef.current;
    inFlightRef.current = true;
    setFlow((current) => (current ? { ...current, phase: "submitting", error: null } : null));
    try {
      const submitted = await submitActionRequest(
        {
          action_request_id: flow.preview.action_request_id,
          reason: flow.reason.trim()
        },
        csrfToken
      );
      if (tokenRef.current !== token) return;
      navigate(`/actions/${encodeURIComponent(submitted.action_request_id)}`);
    } catch (error: unknown) {
      if (tokenRef.current !== token) return;
      setFlow((current) =>
        current
          ? {
              ...current,
              phase: "submit-error",
              error: safeError(error, "The action request could not be submitted safely.")
            }
          : current
      );
    } finally {
      if (tokenRef.current === token) inFlightRef.current = false;
    }
  }

  function close() {
    if (flow?.phase === "creating" || flow?.phase === "submitting") return;
    tokenRef.current += 1;
    setFlow(null);
  }

  function setReason(reason: string) {
    setFlow((current) => (current ? { ...current, reason } : null));
  }

  function recreate() {
    if (!flow || sourceGeneration !== flow.resolution.previewRequestSourceGeneration) return;
    const resolution = flow.resolution;
    setFlow(null);
    void openPreview(resolution);
  }

  return { close, flow, openPreview, recreate, setReason, submit };
}

export function previewExpired(preview: ActionDetail, now = Date.now()): boolean {
  if (preview.is_expired || !preview.preview_expires_at) return true;
  const deadline = new Date(preview.preview_expires_at).getTime();
  return Number.isNaN(deadline) || deadline <= now;
}

function safeError(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : fallback;
}
