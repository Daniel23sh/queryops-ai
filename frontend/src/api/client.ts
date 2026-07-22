const DEFAULT_API_BASE_URL = "http://localhost:8000";

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

export type ApiDownloadResult = {
  blob: Blob;
  filename: string;
  contentType: string;
};

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

export async function apiDownload(
  path: string,
  init: RequestInit = {},
  fallbackFilename = "queryops-export.csv"
): Promise<ApiDownloadResult> {
  const headers = new Headers(init.headers);
  if (!headers.has("Accept")) {
    headers.set("Accept", "text/csv, application/json");
  }

  const response = await fetch(apiUrl(path), {
    ...init,
    credentials: "include",
    headers
  });

  if (!response.ok) {
    throw await downloadError(response);
  }

  const contentType =
    response.headers.get("Content-Type") ?? "application/octet-stream";
  return {
    blob: await response.blob(),
    filename: downloadFilename(
      response.headers.get("Content-Disposition"),
      fallbackFilename
    ),
    contentType
  };
}

export function downloadBlob(result: ApiDownloadResult): void {
  const objectUrl = URL.createObjectURL(result.blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = result.filename;
  anchor.hidden = true;
  document.body.appendChild(anchor);

  try {
    anchor.click();
  } finally {
    anchor.remove();
    URL.revokeObjectURL(objectUrl);
  }
}

async function downloadError(response: Response): Promise<ApiError> {
  const contentType = response.headers.get("Content-Type")?.toLowerCase() ?? "";
  let payload: ApiErrorResponse = {};

  if (contentType.includes("application/json")) {
    try {
      payload = (await response.json()) as ApiErrorResponse;
    } catch {
      payload = {};
    }
  }

  const error = payload.error;
  return new ApiError({
    code: error?.code ?? "API_ERROR",
    message: error?.message ?? "Download request failed.",
    status: response.status,
    details: error?.details,
    requestId: error?.request_id
  });
}

function downloadFilename(
  contentDisposition: string | null,
  fallbackFilename: string
): string {
  if (!contentDisposition) {
    return fallbackFilename;
  }

  const encodedMatch = contentDisposition.match(
    /filename\*\s*=\s*(?:UTF-8'')?([^;]+)/i
  );
  const plainMatch = contentDisposition.match(
    /filename\s*=\s*(?:"([^"]+)"|([^;]+))/i
  );
  const rawFilename = encodedMatch?.[1] ?? plainMatch?.[1] ?? plainMatch?.[2];
  if (!rawFilename) {
    return fallbackFilename;
  }

  let decodedFilename = rawFilename.trim().replace(/^"|"$/g, "");
  if (encodedMatch) {
    try {
      decodedFilename = decodeURIComponent(decodedFilename);
    } catch {
      return fallbackFilename;
    }
  }

  const safeFilename = decodedFilename
    .split(/[\\/]/)
    .pop()
    ?.split("")
    .filter((character) => {
      const code = character.charCodeAt(0);
      return code > 31 && code !== 127;
    })
    .join("")
    .trim();
  if (
    !safeFilename ||
    safeFilename === "." ||
    safeFilename === ".." ||
    safeFilename.length > 255
  ) {
    return fallbackFilename;
  }
  return safeFilename;
}

function apiUrl(path: string): string {
  return `${API_BASE_URL.replace(/\/$/, "")}${path}`;
}
