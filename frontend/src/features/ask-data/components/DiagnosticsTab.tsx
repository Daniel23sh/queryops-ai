import type { DiagnosticItem, QueryRunState } from "../types";
import {
  formatDiagnosticValue,
  formatReferencedTables,
  formatValidationStatus,
  safeDiagnosticText,
  selfCorrectionItems
} from "../utils/diagnostics";
import {
  BODY_TEXT_CLASS,
  MUTED_CARD_CLASS,
  SMALL_PANEL_TITLE_CLASS
} from "./askDataStyles";

export function DiagnosticsTab({
  queryRunState
}: {
  queryRunState: QueryRunState;
}) {
  if (queryRunState.status === "idle") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Run a query to inspect diagnostics for this role.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "running") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Diagnostics will be available after the query finishes.
        </p>
      </div>
    );
  }

  if (queryRunState.status === "error") {
    return (
      <div className={MUTED_CARD_CLASS}>
        <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
        <p className={BODY_TEXT_CLASS}>
          Diagnostics are not available because the latest request ended with a
          safe error state.
        </p>
      </div>
    );
  }

  const { result } = queryRunState;
  const metadata = result.metadata;
  const validation = metadata.validation;
  const execution = metadata.execution;
  const selfCorrection = metadata.self_correction;
  const safeWarnings = result.warnings
    .map(safeDiagnosticText)
    .filter((warning): warning is string => warning !== null);

  return (
    <div className={`${MUTED_CARD_CLASS} gap-4`}>
      <h3 className={SMALL_PANEL_TITLE_CLASS}>Diagnostics</h3>
      <p className={BODY_TEXT_CLASS}>
        Technical diagnostics are built from safe query metadata. SQL text stays
        in the SQL tab.
      </p>

      <DiagnosticSection
        title="Run"
        items={[
          { label: "Query run ID", value: result.query_run_id },
          { label: "Status", value: result.status },
          { label: "Error code", value: result.error_code },
          {
            label: "Clarification required",
            value: result.clarification_required
          }
        ]}
      />

      <DiagnosticSection
        title="Generation"
        items={[
          { label: "Provider", value: metadata.provider },
          { label: "Model", value: metadata.model },
          { label: "Template", value: metadata.template_id },
          { label: "Scope", value: metadata.scope_type },
          {
            label: "Referenced tables",
            value: formatReferencedTables(metadata.referenced_tables)
          }
        ]}
      />

      {validation ? (
        <DiagnosticSection
          title="Validation"
          items={[
            {
              label: "Validation status",
              value: formatValidationStatus(validation.valid)
            },
            { label: "Validation error code", value: validation.error_code }
          ]}
        />
      ) : null}

      {execution ? (
        <DiagnosticSection
          title="Execution"
          items={[
            { label: "Execution status", value: execution.status },
            { label: "Execution error code", value: execution.error_code },
            { label: "Execution row count", value: execution.row_count },
            {
              label: "Execution duration",
              value:
                typeof execution.duration_ms === "number"
                  ? `${execution.duration_ms} ms`
                  : null
            },
            { label: "Execution truncated", value: execution.truncated }
          ]}
        />
      ) : null}

      {selfCorrection ? (
        <DiagnosticSection
          title="Self-correction"
          items={selfCorrectionItems(selfCorrection)}
        />
      ) : null}

      {safeWarnings.length > 0 ? (
        <section className="grid gap-2.5" aria-label="Diagnostic warnings">
          <h4 className="m-0 text-sm font-bold text-app-text">Warnings</h4>
          <ul className="m-0 grid gap-1.5 rounded-card border border-app-border bg-app-surface py-3 pl-8 pr-3.5 text-sm leading-6 text-app-text">
            {safeWarnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function DiagnosticSection({
  items,
  title
}: {
  items: DiagnosticItem[];
  title: string;
}) {
  const visibleItems = items
    .map((item) => ({
      label: item.label,
      value: formatDiagnosticValue(item.value)
    }))
    .filter((item): item is { label: string; value: string } => item.value !== null);

  if (visibleItems.length === 0) {
    return null;
  }

  return (
    <section className="grid gap-2.5" aria-label={`${title} diagnostics`}>
      <h4 className="m-0 text-sm font-bold text-app-text">{title}</h4>
      <dl className="m-0 grid gap-2.5 md:grid-cols-2">
        {visibleItems.map((item) => (
          <div
            key={item.label}
            className="grid gap-1 rounded-card border border-app-border bg-app-surface px-3 py-2.5"
          >
            <dt className="text-xs font-bold uppercase text-app-faint">
              {item.label}
            </dt>
            <dd className="m-0 text-sm font-bold leading-6 text-app-text [overflow-wrap:anywhere]">
              {item.value}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
