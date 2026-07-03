import type { QueryResultRow } from "../types";
import { formatResultValue, valueForColumn } from "../utils/formatResultValue";

export function ResultTable({
  columns,
  rows
}: {
  columns: string[];
  rows: QueryResultRow[];
}) {
  return (
    <div className="overflow-x-auto rounded-card border border-app-border bg-app-surface shadow-sm">
      <table
        className="w-full min-w-[520px] border-collapse text-left text-sm tabular-nums text-app-text"
        aria-label="Query results"
      >
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column}
                scope="col"
                className="sticky top-0 border-b border-app-border bg-app-muted px-3 py-2.5 font-bold text-app-text"
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr
              key={rowIndex}
              className="even:bg-app-muted hover:bg-app-muted [&:last-child>td]:border-b-0"
            >
              {columns.map((column) => (
                <td
                  key={column}
                  className="whitespace-nowrap border-b border-app-border px-3 py-2.5 align-top text-app-subtle"
                >
                  {formatResultValue(valueForColumn(row, column))}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
