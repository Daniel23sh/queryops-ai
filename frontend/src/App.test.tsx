import { render, screen } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import App from "./App";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("renders the project shell", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => undefined)));

    render(<App />);

    expect(screen.getByRole("heading", { level: 1, name: "QueryOps AI" })).toBeInTheDocument();
    expect(screen.getByText(/governed conversational data workspace/i)).toBeInTheDocument();
    expect(screen.getByText("Backend status")).toBeInTheDocument();
    expect(screen.getByText("Checking backend...")).toBeInTheDocument();
  });
});
