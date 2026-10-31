export type DeliveryCompleteness = "complete" | "safety_limited" | "unknown";

export function resultDeliveryWarning(
  completeness: DeliveryCompleteness | undefined,
  truncated = false
): string | null {
  if (truncated || completeness === "safety_limited") {
    return "Partial result: a safety limit may have omitted rows. The full total is unknown.";
  }
  return completeness === "complete"
    ? null
    : "Result completeness is unknown. The returned rows may not be the full result.";
}
