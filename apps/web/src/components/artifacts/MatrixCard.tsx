/**
 * MatrixCard — 2-axis grid (e.g. failure-mode × severity, competitor ×
 * feature). Like TableCard but with explicit row labels in the first
 * column and column labels across the top — making the axes visually
 * symmetric.
 */
import type { MatrixPayload } from "./types";

export function MatrixCard({ payload }: { payload: MatrixPayload }) {
  const { row_labels, col_labels, cells } = payload;
  if (row_labels.length === 0 || col_labels.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Empty matrix — Maya passed no axes.
      </p>
    );
  }
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-[12px] border-collapse">
        <thead>
          <tr className="bg-muted/50">
            <th className="px-3 py-2 text-left text-[10px] uppercase tracking-wider text-muted-foreground border-b border-r border-border" />
            {col_labels.map((col, i) => (
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
          {row_labels.map((rowLabel, rIdx) => (
            <tr
              key={rIdx}
              className="border-b border-border last:border-b-0 hover:bg-muted/30"
            >
              <th className="px-3 py-2 text-left text-[11px] font-semibold text-foreground/80 bg-muted/30 border-r border-border align-top">
                {rowLabel}
              </th>
              {col_labels.map((_, cIdx) => {
                const cell = cells[rIdx]?.[cIdx];
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
