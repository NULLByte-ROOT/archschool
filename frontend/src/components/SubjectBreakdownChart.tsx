import { memo, useMemo } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { motion } from "framer-motion";
import { BookOpen } from "lucide-react";
import type { Assignment } from "../api/client";
import { subjectName } from "../lib/assignments";

/**
 * توزیع تکالیف بر اساس درس (دونات متحرک Recharts).
 * ۵ درس پرمشغله + «سایر» تا راهنما همیشه خوانا بماند.
 */

const PALETTE = [
  "#fafafa",
  "#a5b4fc",
  "#6ee7b7",
  "#fbbf24",
  "#f87171",
  "#94a3b8",
];

interface Slice {
  name: string;
  value: number;
  color: string;
}

function SubjectBreakdownChart({ items }: { items: Assignment[] }) {
  const slices = useMemo<Slice[]>(() => {
    const counts = new Map<string, number>();
    for (const item of items) {
      if (!item.subject_id) continue;
      counts.set(item.subject_id, (counts.get(item.subject_id) ?? 0) + 1);
    }
    const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    const top = ranked.slice(0, 5);
    const rest = ranked.slice(5).reduce((sum, [, v]) => sum + v, 0);
    const result: Slice[] = top.map(([id, value], i) => ({
      name: subjectName(id) || id,
      value,
      color: PALETTE[i % PALETTE.length],
    }));
    if (rest > 0) {
      result.push({
        name: "سایر درس‌ها",
        value: rest,
        color: PALETTE[PALETTE.length - 1],
      });
    }
    return result;
  }, [items]);

  const total = chunks(slices);
  return (
    <motion.div
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
      className="panel relative overflow-hidden rounded-3xl p-5"
    >
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <p className="mono-label">// SUBJECTS</p>
          <h3 className="text-base font-bold text-white">توزیع بر اساس درس</h3>
        </div>
        <span className="badge">
          <BookOpen size={11} />
          {slices.length} درس
        </span>
      </div>

      {total === 0 ? (
        <div className="flex h-[150px] items-center justify-center text-[11px] text-fg-500">
          تکلیفی با درس مشخص ثبت نشده
        </div>
      ) : (
        <div className="flex items-center gap-4">
          <div className="relative h-[150px] w-[150px] shrink-0" dir="ltr">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Tooltip
                  contentStyle={{
                    background: "rgba(9,9,11,0.92)",
                    border: "1px solid rgba(255,255,255,0.14)",
                    borderRadius: 14,
                    fontSize: 11,
                    direction: "rtl",
                  }}
                  itemStyle={{ color: "#d4d4d8" }}
                  formatter={
                    ((value: unknown, name: unknown) => [
                      `${String(value)} تکلیف`,
                      String(name),
                    ]) as never
                  }
                />
                <Pie
                  data={slices}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={46}
                  outerRadius={68}
                  paddingAngle={3}
                  cornerRadius={6}
                  stroke="none"
                  animationDuration={850}
                  animationEasing="ease-out"
                  isAnimationActive
                >
                  {slices.map((slice) => (
                    <Cell key={slice.name} fill={slice.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
            <div
              className="absolute inset-0 flex flex-col items-center justify-center"
              dir="rtl"
            >
              <span className="mono text-xl font-black text-white">{total}</span>
              <span className="text-[9px] text-fg-500">کل تکلیف</span>
            </div>
          </div>

          <div className="min-w-0 flex-1 space-y-2">
            {slices.map((slice) => (
              <div key={slice.name} className="flex items-center gap-2">
                <span
                  className="h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ background: slice.color }}
                />
                <span className="min-w-0 flex-1 truncate text-[11px] text-fg-300">
                  {slice.name}
                </span>
                <span className="mono text-xs font-bold tabular-nums text-white">
                  {slice.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

function chunks(slices: Slice[]): number {
  return slices.reduce((sum, s) => sum + s.value, 0);
}

export default memo(SubjectBreakdownChart);
