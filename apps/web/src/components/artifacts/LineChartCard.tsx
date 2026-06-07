/**
 * LineChartCard — series over an axis (time, sample size, etc.). Useful
 * when Maya wants to show a trend or a model's accuracy curve.
 *
 * Each series has its own array of {x, y} points; we merge them into the
 * row-of-objects shape recharts expects by unioning the x-axis values.
 */
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { LineChartPayload } from "./types";

const PALETTE = [
  "#0f766e",
  "#9d2545",
  "#7c3aed",
  "#b45309",
  "#1d4ed8",
  "#15803d",
];

export function LineChartCard({ payload }: { payload: LineChartPayload }) {
  const { series, x_label, y_label } = payload;
  if (series.length === 0 || series.every((s) => s.points.length === 0)) {
    return (
      <p className="text-[12px] text-muted-foreground italic">
        Empty chart — Maya passed no points.
      </p>
    );
  }

  // Union of x-axis values across all series, preserving first-seen order.
  const xValues: (string | number)[] = [];
  const seen = new Set<string>();
  for (const s of series) {
    for (const pt of s.points) {
      const key = String(pt.x);
      if (!seen.has(key)) {
        seen.add(key);
        xValues.push(pt.x);
      }
    }
  }

  const data = xValues.map((x) => {
    const row: Record<string, string | number | null> = { x };
    for (const s of series) {
      const pt = s.points.find((p) => String(p.x) === String(x));
      row[s.name] = pt ? pt.y : null;
    }
    return row;
  });

  return (
    <div className="w-full h-[240px]">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 16 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis
            dataKey="x"
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
          />
          {series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} />}
          {series.map((s, i) => (
            <Line
              key={s.name}
              type="monotone"
              dataKey={s.name}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
