import type { HomeOverview } from "../features/home/types";
import { apiRequest } from "./client";

export function getHomeOverview(signal?: AbortSignal): Promise<HomeOverview> {
  return apiRequest<HomeOverview>("/api/v1/home/overview", {
    method: "GET",
    signal
  });
}
