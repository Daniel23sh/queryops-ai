import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useRef, useState } from "react";
import { describe, expect, it } from "vitest";

import { AccessibleOverlay } from "./AccessibleOverlay";

describe("AccessibleOverlay", () => {
  it("focuses the panel when every control is disabled and contains escaped focus", async () => {
    render(
      <>
        <button type="button">Outside</button>
        <AccessibleOverlay closeDisabled kind="dialog" onClose={() => undefined} title="Locked dialog">
          <p>Saving in progress</p>
        </AccessibleOverlay>
      </>
    );

    const dialog = screen.getByRole("dialog", { name: "Locked dialog" });
    await waitFor(() => expect(dialog).toHaveFocus());

    screen.getByRole("button", { name: "Outside" }).focus();
    expect(dialog).toHaveFocus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(dialog).toHaveFocus();
  });

  it("uses the requested initial control and restores focus through a return container", async () => {
    render(<OverlayHarness />);
    fireEvent.click(screen.getByRole("button", { name: "Open overlay" }));

    await waitFor(() => expect(screen.getByRole("textbox", { name: "Inside" })).toHaveFocus());
    fireEvent.keyDown(document, { key: "Escape" });

    await waitFor(() => expect(screen.getByRole("textbox", { name: "Command" })).toHaveFocus());
  });
});

function OverlayHarness() {
  const [open, setOpen] = useState(false);
  const initialFocusRef = useRef<HTMLInputElement>(null);
  const returnFocusRef = useRef<HTMLDivElement>(null);
  return (
    <>
      <div ref={returnFocusRef}>
        <label>
          Command
          <textarea />
        </label>
      </div>
      <button type="button" onClick={() => setOpen(true)}>Open overlay</button>
      {open ? (
        <AccessibleOverlay
          initialFocusRef={initialFocusRef}
          kind="drawer"
          onClose={() => setOpen(false)}
          returnFocusRef={returnFocusRef}
          title="Test overlay"
        >
          <label>
            Inside
            <input ref={initialFocusRef} />
          </label>
        </AccessibleOverlay>
      ) : null}
    </>
  );
}
