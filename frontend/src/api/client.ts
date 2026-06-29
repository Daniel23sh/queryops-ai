const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL;

type ApiSuccessResponse<T> = {
  data: T;
  meta?: {
    request_id?: string;
    timestamp?: string;
  };
};

type ApiErrorResponse = {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
    request_id?: string;
  };
};

export class ApiError extends Error {
  code: string;
  status: number;
  details: Record<string, unknown>;
  requestId?: string;

  constructor({
    code,
    message,
    status,
    details = {},
    requestId
  }: {
    code: string;
    message: string;
    status: number;
    details?: Record<string, unknown>;
    requestId?: string;
  }) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

export async function apiRequest<T>(
  path: string,
  init: RequestInit = {}
): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...init.headers
    }
  });
  const payload = (await response.json()) as ApiSuccessResponse<T> & ApiErrorResponse;

  if (!response.ok) {
    const error = payload.error;
    throw new ApiError({
      code: error?.code ?? "API_ERROR",
      message: error?.message ?? "Request failed.",
      status: response.status,
      details: error?.details,
      requestId: error?.request_id
    });
  }

  return payload.data;
}

function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}

