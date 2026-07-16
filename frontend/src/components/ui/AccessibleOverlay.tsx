import { X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  type ReactNode,
  type RefObject
} from "react";

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function AccessibleOverlay({
  children,
  closeDisabled = false,
  description,
  footer,
  initialFocusRef,
  kind,
  onClose,
  returnFocusRef,
  title
}: {
  children: ReactNode;
  closeDisabled?: boolean;
  description?: string;
  footer?: ReactNode;
  initialFocusRef?: RefObject<HTMLElement>;
  kind: "dialog" | "drawer";
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement>;
  title: string;
}) {
  const titleId = useId();
  const descriptionId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const openerRef = useRef<HTMLElement | null>(
    document.activeElement instanceof HTMLElement ? document.activeElement : null
  );
  const onCloseRef = useRef(onClose);
  const closeDisabledRef = useRef(closeDisabled);
  onCloseRef.current = onClose;
  closeDisabledRef.current = closeDisabled;

  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.requestAnimationFrame(() => {
      focusInsidePanel(panelRef.current, initialFocusRef?.current ?? null);
    });

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        if (!closeDisabledRef.current) {
          event.preventDefault();
          onCloseRef.current();
        }
        return;
      }

      if (event.key !== "Tab" || !panelRef.current) {
        return;
      }

      const focusable = focusableElements(panelRef.current);
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!first || !last) {
        event.preventDefault();
        panelRef.current.focus();
        return;
      }
      if (!panelRef.current.contains(document.activeElement)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function handleFocusIn(event: FocusEvent) {
      const panel = panelRef.current;
      if (
        !panel ||
        !(event.target instanceof Node) ||
        panel.contains(event.target)
      ) {
        return;
      }
      focusInsidePanel(panel, initialFocusRef?.current ?? null);
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", handleFocusIn);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", handleFocusIn);
      document.body.style.overflow = previousOverflow;
      window.requestAnimationFrame(() => {
        focusTarget(returnFocusRef?.current ?? openerRef.current);
      });
    };
  }, [initialFocusRef, returnFocusRef]);

  const isDrawer = kind === "drawer";

  return (
    <div
      className="fixed inset-0 z-[80] flex bg-black/60 backdrop-blur-[2px]"
      data-overlay-kind={kind}
      onMouseDown={(event) => {
        if (
          event.target === event.currentTarget &&
          !closeDisabledRef.current
        ) {
          onClose();
        }
      }}
    >
      <div
        ref={panelRef}
        aria-describedby={description ? descriptionId : undefined}
        aria-labelledby={titleId}
        aria-modal="true"
        className={
          isDrawer
            ? "ml-auto flex h-dvh w-full max-w-xl flex-col overflow-hidden border-l border-app-border bg-app-surface shadow-panel sm:h-full"
            : "m-auto flex max-h-[min(90dvh,760px)] w-[min(92vw,640px)] flex-col overflow-hidden rounded-card border border-app-border bg-app-surface shadow-panel max-sm:h-dvh max-sm:max-h-none max-sm:w-full max-sm:rounded-none"
        }
        role="dialog"
        tabIndex={-1}
      >
        <header className="flex shrink-0 items-start justify-between gap-4 border-b border-app-border px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <h2 id={titleId} className="m-0 text-xl font-bold text-app-text">
              {title}
            </h2>
            {description ? (
              <p
                id={descriptionId}
                className="mb-0 mt-1 text-sm leading-6 text-app-subtle"
              >
                {description}
              </p>
            ) : null}
          </div>
          <button
            type="button"
            className="icon-button shrink-0"
            aria-label={`Close ${title}`}
            disabled={closeDisabled}
            onClick={onClose}
          >
            <X aria-hidden="true" size={20} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 py-5 sm:px-6">
          {children}
        </div>
        {footer ? (
          <footer className="flex shrink-0 flex-wrap justify-end gap-3 border-t border-app-border px-5 py-4 sm:px-6">
            {footer}
          </footer>
        ) : null}
      </div>
    </div>
  );
}

function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR));
}

function focusInsidePanel(
  panel: HTMLElement | null,
  preferred: HTMLElement | null
) {
  if (!panel) return;
  if (preferred && panel.contains(preferred) && preferred.matches(FOCUSABLE_SELECTOR)) {
    preferred.focus();
    return;
  }
  (focusableElements(panel)[0] ?? panel).focus();
}

function focusTarget(target: HTMLElement | null) {
  if (!target) return;
  if (target.matches(FOCUSABLE_SELECTOR)) {
    target.focus();
    return;
  }
  (target.querySelector<HTMLElement>(FOCUSABLE_SELECTOR) ?? target).focus();
}
