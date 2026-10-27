import { useMemo } from "react";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowUpRight, TrendingUp } from "lucide-react";
import type { DailyActivity } from "../api/client";
import Corners from "./Corners";

/**
 * Seven-day class completion trend for the dashboard. Lazy-loaded (Recharts is
 * only needed here and in the profile modal).
 */
export default function ClassTrendChart({
  data,
  onOpen,
}: {
  data: DailyActivity[];
  onOpen: () => void;
}) {
  const chartData = useMemo(
    () =>
      data.map((point) => {
        const date = new Date(`${point.date}T00:00:00`);
        return {
          day: date.toLocaleDateString("fa-IR-u-nu-latn", {
            weekday: "short",
          }),
          count: point.count,
        };
      }),
    [data]
  );

  const total = useMemo(
    () => chartData.reduce((sum, point) => sum + point.count, 0),
    [chartData]
  );

  // Green = at least one completion that day, red = no activity at all.
  const renderDot = (props: {
    cx?: number;
    cy?: number;
    payload?: { count?: number };
  }) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return <g />;
    const active = (payload?.count ?? 0) > 0;
    return (
      <circle
        cx={cx}
        cy={cy}
        r={3}
        fill={active ? "#34d399" : "#f87171"}
        stroke="#09090b"
        strokeWidth={1.5}
      />
    );
  };

  return (
    <button
      type="button"
      onClick={onOpen}
      className="panel panel-hover relative flex h-full w-full flex-col overflow-hidden rounded-3xl p-5 text-right"
    >
      <Corners />
      <div className="mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
            <TrendingUp size={16} className="text-success" />
          </span>
          <div>
            <p className="mono-label">// CLASS TREND</p>
            <h3 className="text-base font-bold text-white">روند ۷ روز کلاس</h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge">{total} تکمیل</span>
          <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-fg-300">
            <ArrowUpRight size={15} />
          </span>
        </div>
      </div>

      {total === 0 ? (
        <div className="flex flex-1 items-center justify-center py-10 text-[11px] text-fg-500">
          هنوز تکمیل‌ای در هفت روز گذشته ثبت نشده
        </div>
      ) : (
        <div className="h-[180px] w-full" dir="ltr">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart
              data={chartData}
              margin={{ top: 8, right: 8, left: -20, bottom: 0 }}
            >
              <defs>
                <linearGradient id="classTrendFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#34d399" stopOpacity={0.4} />
                  <stop offset="65%" stopColor="#34d399" stopOpacity={0.1} />
                  <stop offset="100%" stopColor="#34d399" stopOpacity={0} />
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
                width={32}
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
                itemStyle={{ color: "#a7f3d0" }}
                cursor={{ stroke: "rgba(255,255,255,0.22)", strokeDasharray: "3 3" }}
                formatter={
                  ((value: unknown) =>
                    [`${String(value)} تکمیل`, "کلاس"]) as never
                }
              />
              <Area
                type="monotone"
                dataKey="count"
                name="کلاس"
                stroke="#34d399"
                strokeWidth={2.5}
                fill="url(#classTrendFill)"
                dot={renderDot as never}
                activeDot={{
                  r: 4,
                  fill: "#34d399",
                  stroke: "rgba(52,211,153,0.35)",
                  strokeWidth: 4,
                }}
                animationDuration={900}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </button>
  );
}
