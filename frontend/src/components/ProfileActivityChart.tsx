import { useMemo } from "react";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DailyActivity } from "../api/client";

/**
 * 7-day personal activity bars for the profile modal. Lazy-loaded by the modal
 * because Recharts is the heaviest dependency in the app.
 */
export default function ProfileActivityChart({
  data,
}: {
  data: DailyActivity[];
}) {
  const chartData = useMemo(() => {
    const lastIndex = data.length - 1;
    return data.map((point, index) => {
      // The backend sends school-local ISO dates; only the weekday label is
      // needed here and the digits stay Latin (`-u-nu-latn`).
      const date = new Date(`${point.date}T00:00:00`);
      return {
        day: date.toLocaleDateString("fa-IR-u-nu-latn", { weekday: "short" }),
        count: point.count,
        today: index === lastIndex,
      };
    });
  }, [data]);

  const total = useMemo(
    () => chartData.reduce((sum, point) => sum + point.count, 0),
    [chartData]
  );

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="mono-label">// 7 DAYS</p>
        <span className="mono text-[10px] tabular-nums text-fg-500">
          {total} تکمیل در هفته
        </span>
      </div>

      <div className="h-[132px] w-full" dir="ltr">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            margin={{ top: 6, right: 4, left: -28, bottom: 0 }}
            barCategoryGap="28%"
          >
            <defs>
              <linearGradient id="profileBar" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#fb923c" stopOpacity={0.95} />
                <stop offset="100%" stopColor="#f97316" stopOpacity={0.35} />
              </linearGradient>
              <linearGradient id="profileBarToday" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#fef08a" stopOpacity={1} />
                <stop offset="100%" stopColor="#fbbf24" stopOpacity={0.45} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="day"
              tick={{
                fill: "rgba(255,255,255,0.45)",
                fontSize: 10,
                fontFamily: "inherit",
              }}
              axisLine={false}
              tickLine={false}
              interval={0}
            />
            <YAxis
              width={30}
              allowDecimals={false}
              tick={{ fill: "rgba(255,255,255,0.35)", fontSize: 10 }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "rgba(9,9,11,0.94)",
                border: "1px solid rgba(255,255,255,0.14)",
                borderRadius: 14,
                fontSize: 11,
                direction: "rtl",
              }}
              labelStyle={{ color: "#fafafa", fontWeight: 700 }}
              itemStyle={{ color: "#fed7aa" }}
              cursor={{ fill: "rgba(255,255,255,0.05)" }}
              formatter={
                ((value: unknown) =>
                  [`${String(value)} تکمیل`, "فعالیت"]) as never
              }
            />
            <Bar
              dataKey="count"
              name="فعالیت"
              radius={[6, 6, 0, 0]}
              animationDuration={700}
              animationEasing="ease-out"
            >
              {chartData.map((point) => (
                <Cell
                  key={point.day}
                  fill={
                    point.today ? "url(#profileBarToday)" : "url(#profileBar)"
                  }
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
