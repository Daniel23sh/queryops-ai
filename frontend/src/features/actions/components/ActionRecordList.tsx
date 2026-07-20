import type { SafeActionRecord } from "../types";

export function ActionRecordList({
  records,
  emptyMessage
}: {
  records: SafeActionRecord[];
  emptyMessage: string;
}) {
  if (!records.length) {
    return <p className="m-0 rounded-control bg-app-muted p-3 text-sm text-app-subtle">{emptyMessage}</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-2 p-0">
      {records.map((record, index) => (
        <li className="rounded-control border border-app-border bg-app-muted p-3" key={record.record_id ?? index}>
          <p className="m-0 text-sm font-bold text-app-text">
            {record.user_display_label ?? record.license_product ?? "Governed record"}
          </p>
          {record.license_product ? (
            <p className="mb-0 mt-1 text-xs text-app-subtle">
              {[record.license_vendor, record.license_product].filter(Boolean).join(" · ")}
            </p>
          ) : null}
          {record.reason ? <p className="mb-0 mt-1 text-xs leading-5 text-app-subtle">{record.reason}</p> : null}
          {record.scope.key ? <p className="mb-0 mt-1 text-xs text-app-faint">Scope: {record.scope.key}</p> : null}
        </li>
      ))}
    </ul>
  );
}
