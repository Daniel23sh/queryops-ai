import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../../api/client";
import { listQueryTemplates } from "../../../api/queryTemplates";
import type { QueryTemplate, TemplateLoadStatus } from "../types";
import { groupTemplatesByCategory } from "../utils/templateCategories";

export function useQueryTemplates() {
  const [templates, setTemplates] = useState<QueryTemplate[]>([]);
  const [templateLoadStatus, setTemplateLoadStatus] =
    useState<TemplateLoadStatus>("loading");
  const [templateLoadError, setTemplateLoadError] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const templateCategories = useMemo(
    () => groupTemplatesByCategory(templates),
    [templates]
  );
  const selectedTemplate =
    templates.find((template) => template.id === selectedTemplateId) ?? null;

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

  return {
    selectedTemplate,
    selectedTemplateId,
    setSelectedTemplateId,
    templateCategories,
    templateLoadError,
    templateLoadStatus
  };
}

function formatTemplateLoadError(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }

  return "Query templates could not be loaded.";
}
