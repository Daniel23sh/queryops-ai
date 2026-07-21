import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useEvaluationResource } from "./useEvaluationResource";

describe("useEvaluationResource", () => {
  it("clears prior identity data immediately and ignores the stale response", async () => {
    let resolveOld!: (value: string) => void;
    let resolveNew!: (value: string) => void;
    const oldRequest = new Promise<string>((resolve) => { resolveOld = resolve; });
    const newRequest = new Promise<string>((resolve) => { resolveNew = resolve; });
    const loads = { old: vi.fn(() => oldRequest), new: vi.fn(() => newRequest) };
    const { rerender, result } = renderHook(({ identity }) => useEvaluationResource({ load: identity === "old" ? loads.old : loads.new, requestKey: identity }), { initialProps: { identity: "old" } });
    resolveOld("old metrics");
    await waitFor(() => expect(result.current.data).toBe("old metrics"));

    rerender({ identity: "new" });
    expect(result.current.data).toBeNull();
    expect(result.current.status).toBe("loading");
    resolveOld("stale metrics");
    resolveNew("new metrics");
    await waitFor(() => expect(result.current.data).toBe("new metrics"));
    expect(result.current.data).not.toBe("old metrics");
  });
});
