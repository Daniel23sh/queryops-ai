import { apiRequest } from "./client";
import type { QueryTemplate } from "../features/ask-data/types";

export function listQueryTemplates(): Promise<QueryTemplate[]> {
  return apiRequest<QueryTemplate[]>("/api/v1/query-templates", {
    method: "GET"
  });
}

export function getQueryTemplate(templateId: string): Promise<QueryTemplate> {
  return apiRequest<QueryTemplate>(
    `/api/v1/query-templates/${encodeURIComponent(templateId)}`,
    {
      method: "GET"
    }
  );
}
