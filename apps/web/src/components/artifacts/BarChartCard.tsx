/**
 * BarChartCard — categorical comparison. Used by Hugo (failure-mode
 * severity), Aiden (competitor pricing), or Maya (synthesis).
 *
 * recharts is the heavyweight here. We translate the payload's columnar
 * shape (categories[] + series[]) into the row-of-objects shape recharts
 * wants. A small fixed palette covers up to 6 series; beyond that we
 * recycle.
 */
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { BarChartPayload } from "./types";

// Colour palette — keep accessible against the card background.
const PALETTE = [
  "#0f766e", // teal-700
  "#9d2545", // rose-800 (terracotta-ish)
  "#7c3aed", // violet-600
  "#b45309", // amber-700
  "#1d4ed8", // blue-700
  "#15803d", // green-700
];

export function BarChartCard({ payload }: { payload: BarChartPayload }) {
  const { categories, series, x_label, y_label } = payload;
  if (categories.length === 0 || series.length === 0) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Empty chart — Maya passed no categories or series.
      </p>
    );
  }

  // recharts shape: each row is { categoryLabel, series1: n, series2: n, ... }
  const data = categories.map((cat, i) => {
    const row: Record<string, string | number> = { category: cat };
    for (const s of series) {
      row[s.name] = s.values[i] ?? 0;
    }
    return row;
  });

  return (
    <div className="w-full h-[240px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="category"
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            label={
              x_label
                ? { value: x_label, position: "insideBottom", offset: -6, fontSize: 10, fill: "hsl(var(--muted-foreground))" }
                : undefined
            }
          />
          <YAxis
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: "hsl(var(--border))" }}
            label={
              y_label
                ? { value: y_label, angle: -90, position: "insideLeft", fontSize: 10, fill: "hsl(var(--muted-foreground))" }
                : undefined
            }
          />
          <Tooltip
            contentStyle={{
              background: "hsl(var(--card))",
              border: "1px solid hsl(var(--border))",
              borderRadius: 8,
              fontSize: 12,
            }}
            cursor={{ fill: "hsl(var(--muted) / 0.4)" }}
          />
          {series.length > 1 && (
            <Legend wrapperStyle={{ fontSize: 11 }} />
          )}
          {series.map((s, i) => (
            <Bar
              key={s.name}
              dataKey={s.name}
              fill={PALETTE[i % PALETTE.length]}
              radius={[3, 3, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
