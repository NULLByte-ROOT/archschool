import { memo, useMemo } from "react";
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { motion } from "framer-motion";
import { CalendarClock } from "lucide-react";
import type { Assignment } from "../api/client";
import { parseDue, todayIndex } from "../lib/assignments";

/**
 * روند مهلت‌های ۷ روز آینده (خط منحنی متحرک با type="monotone").
 * هر نقطه = تعداد تکالیفی که هنوز انجام نشده و مهلتشان در آن روز تقویمی است.
 */

const DAY_NAMES = [
  "شنبه",
  "یکشنبه",
  "دوشنبه",
  "سه‌شنبه",
  "چهارشنبه",
  "پنجشنبه",
  "جمعه",
];

function DeadlineTrendChart({ items, now }: { items: Assignment[]; now: number }) {
  const { data, weekTotal } = useMemo(() => {
    const day0 = (() => {
      const base = new Date(now);
      return new Date(base.getFullYear(), base.getMonth(), base.getDate());
    })();
    const countsMap = new Map<number, number>();
    for (const item of items) {
      if (item.is_completed_by_me || !item.due_date) continue;
      const due = parseDue(item.due_date);
      const dueDay = new Date(due.getFullYear(), due.getMonth(), due.getDate()).getTime();
      const offset = Math.round((dueDay - day0.getTime()) / 86_400_000);
      if (offset >= 0 && offset <= 6) {
        countsMap.set(offset, (countsMap.get(offset) ?? 0) + 1);
      }
    }
    const data = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(day0.getTime());
      d.setDate(day0.getDate() + i);
      data.push({ day: DAY_NAMES[todayIndex(d)] ?? "", count: countsMap.get(i) ?? 0 });
    }
    return { data, weekTotal: data.reduce((sum, p) => sum + p.count, 0) };
  }, [items, now]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="panel relative overflow-hidden rounded-3xl p-5"
    >
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <p className="mono-label">// WORKLOAD</p>
          <h3 className="text-base font-bold text-white">روند مهلت‌های ۷ روز آینده</h3>
        </div>
        <span className="badge">
          <CalendarClock size={11} />
          {weekTotal} مهلت پیشِ رو
        </span>
      </div>

      {weekTotal === 0 ? (
        <div className="flex h-[150px] items-center justify-center text-[11px] text-fg-500">
          مهلتی برای هفت روز آینده ثبت نشده
        </div>
      ) : (
        <div className="h-[175px] w-full" dir="ltr">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
              <defs>
                <linearGradient id="deadlineFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity={0.35} />
                  <stop offset="70%" stopColor="#ffffff" stopOpacity={0.08} />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
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
                width={34}
                allowDecimals={false}
                tick={{ fill: "rgba(255,255,255,0.35)", fontSize: 10 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(9,9,11,0.92)",
                  border: "1px solid rgba(255,255,255,0.14)",
                  borderRadius: 14,
                  fontSize: 11,
                  direction: "rtl",
                }}
                labelStyle={{ color: "#fafafa", fontWeight: 700 }}
                itemStyle={{ color: "#d4d4d8" }}
                cursor={{ stroke: "rgba(255,255,255,0.25)", strokeDasharray: "3 3" }}
                formatter={
                  ((value: unknown) =>
                    [`${String(value)} تکلیف`, "روند مهلت"]) as never
                }
              />
              <Area
                type="monotone"
                dataKey="count"
                name="روند مهلت"
                stroke="#ffffff"
                strokeWidth={2.5}
                fill="url(#deadlineFill)"
                dot={false}
                activeDot={{
                  r: 4,
                  fill: "#ffffff",
                  stroke: "rgba(255,255,255,0.35)",
                  strokeWidth: 4,
                }}
                animationDuration={900}
                animationEasing="ease-out"
                isAnimationActive
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </motion.div>
  );
}

export default memo(DeadlineTrendChart);
