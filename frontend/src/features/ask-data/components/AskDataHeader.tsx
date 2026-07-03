import {
  EYEBROW_CLASS,
  STATUS_TILE_CLASS
} from "./askDataStyles";

export function AskDataHeader({
  modeDescription,
  modeLabel,
  roleLabel,
  scopeLabel,
  showAdminGlobalIndicator
}: {
  modeDescription: string;
  modeLabel: string;
  roleLabel: string;
  scopeLabel: string;
  showAdminGlobalIndicator: boolean;
}) {
  return (
    <header className="overflow-hidden rounded-card border border-app-border bg-app-surface p-5 shadow-card sm:p-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-3xl">
          <p className={EYEBROW_CLASS}>Command workspace</p>
          <h1
            id="workspace-title"
            className="mt-2 text-[clamp(2rem,4vw,3rem)] font-bold leading-tight tracking-normal text-app-text"
          >
            Ask Data
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-app-subtle">
            Choose an approved template, ask permitted questions, and inspect
            results in a focused workspace that keeps technical detail role-gated.
          </p>
        </div>
        <ContextChips
          modeDescription={modeDescription}
          modeLabel={modeLabel}
          roleLabel={roleLabel}
          scopeLabel={scopeLabel}
          showAdminGlobalIndicator={showAdminGlobalIndicator}
        />
      </div>
    </header>
  );
}

function ContextChips({
  modeLabel,
  modeDescription,
  roleLabel,
  scopeLabel,
  showAdminGlobalIndicator
}: {
  modeLabel: string;
  modeDescription: string;
  roleLabel: string;
  scopeLabel: string;
  showAdminGlobalIndicator: boolean;
}) {
  return (
    <div className="grid gap-3 lg:max-w-[28rem]" aria-label="Ask Data access summary">
      <dl className="m-0 flex flex-wrap gap-2">
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Mode</dt>
          <dd className="m-0">{modeLabel}</dd>
        </div>
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Role</dt>
          <dd className="m-0">{roleLabel}</dd>
        </div>
        <div className={STATUS_TILE_CLASS}>
          <dt className="text-app-faint">Scope</dt>
          <dd className="m-0">{scopeLabel}</dd>
        </div>
      </dl>
      <p className="m-0 max-w-md text-sm leading-6 text-app-subtle">
        {modeDescription}
      </p>
      {showAdminGlobalIndicator ? (
        <p className="m-0 rounded-control border border-app-border bg-app-muted px-3 py-2 text-xs font-bold leading-5 text-app-text">
          Admin global scope indicator. Query runs still use backend authorization.
        </p>
      ) : null}
    </div>
  );
}
