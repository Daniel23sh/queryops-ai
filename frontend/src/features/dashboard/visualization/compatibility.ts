import type { DashboardCardType, VisualizationConfig } from "../types";
import { mappingForType } from "./inferVisualization";
import type { VisualizationRecommendation } from "./types";

export function isVisualizationCompatible(
  type: DashboardCardType,
  recommendation: VisualizationRecommendation
): boolean {
  return recommendation.compatibleTypes.includes(type);
}

export function recommendedConfig(
  recommendation: VisualizationRecommendation
): VisualizationConfig {
  return {
    mode: "auto",
    type: recommendation.recommendedType,
    recommended_type: recommendation.recommendedType,
    mapping: recommendation.mapping
  };
}

export function manualConfig(
  type: DashboardCardType,
  recommendation: VisualizationRecommendation
): VisualizationConfig {
  return {
    mode: "manual",
    type,
    recommended_type: recommendation.recommendedType,
    mapping: mappingForType(type, recommendation.profiles)
  };
}
