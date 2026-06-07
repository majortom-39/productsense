/**
 * TableCard — comparative grid. Used by Aiden (competitor sweep), Theo
 * (stack comparison), or Maya (synthesized cross-tab).
 *
 * Cells render as plain strings; numbers are shown right-aligned to make
 * comparison easier. Cells can be null (renders as em-dash).
 */
import type { TablePayload } from "./types";

export function TableCard({ payload }: { payload: TablePayload }) {
  const { columns, rows } = payload;
  if (columns.length === 0 || rows.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Empty table — Maya passed no rows or columns.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-[12px] border-collapse">
        <thead>
          <tr className="bg-muted/50">
            {columns.map((col, i) => (
              <th
                key={i}
                className="px-3 py-2 text-left text-[11px] font-semibold text-foreground/80 uppercase tracking-wider border-b border-border"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rIdx) => (
            <tr
              key={rIdx}
              className="border-b border-border last:border-b-0 hover:bg-muted/30"
            >
              {columns.map((_, cIdx) => {
                const cell = row[cIdx];
                const isNum = typeof cell === "number";
                return (
                  <td
                    key={cIdx}
                    className={`px-3 py-2 align-top text-foreground/85 ${
                      isNum ? "text-right tabular-nums" : "text-left"
                    }`}
                  >
                    {cell === null || cell === undefined ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      String(cell)
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
