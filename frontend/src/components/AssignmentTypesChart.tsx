import { memo, useMemo } from "react";
import { motion } from "framer-motion";
import { ClipboardList, GraduationCap, Layers3 } from "lucide-react";
import type { Assignment } from "../api/client";
import { useIsMobileWidth } from "../hooks/useMediaQuery";

const TYPES = [
  { id: "homework", label: "تکلیف", color: "var(--chart-1)" },
  { id: "exam", label: "امتحان", color: "var(--chart-2)" },
  { id: "project", label: "پروژه", color: "var(--chart-3)" },
] as const;

const ICONS = {
  homework: ClipboardList,
  exam: GraduationCap,
  project: Layers3,
} as const;

function AssignmentTypesChart({ items }: { items: Assignment[] }) {
  const isMobile = useIsMobileWidth();
  const segments = useMemo(() => {
    const counts = {
      homework: items.filter(
        (item) => item.category !== "exam" && item.subtype !== "practical"
      ).length,
      exam: items.filter((item) => item.category === "exam").length,
      project: items.filter(
        (item) => item.category !== "exam" && item.subtype === "practical"
      ).length,
    };
    const total = counts.homework + counts.exam + counts.project;
    return { counts, total };
  }, [items]);

  const { counts, total } = segments;
  const radius = 42;
  const circumference = 2 * Math.PI * radius;

  return (
    <div className="panel relative overflow-hidden rounded-3xl p-5">
      <div className="mb-4 flex items-center justify-between gap-2">
        <div>
          <p className="mono-label">// TYPES</p>
          <h3 className="text-base font-bold text-white">ترکیب تکالیف</h3>
        </div>
        <span className="badge">{total} ITEM</span>
      </div>

      {total === 0 ? (
        <p className="py-8 text-center text-[11px] text-fg-500">هنوز تکلیفی ثبت نشده</p>
      ) : isMobile ? (
        <div className="space-y-3">
          <div className="flex h-3 overflow-hidden rounded-full bg-white/[0.06]">
            {TYPES.map((type) => (
              <div
                key={type.id}
                style={{
                  width: `${(counts[type.id] / total) * 100}%`,
                  background: type.color,
                }}
              />
            ))}
          </div>
          {TYPES.map((type) => (
            <Row key={type.id} type={type} value={counts[type.id]} total={total} />
          ))}
        </div>
      ) : (
        <div className="flex items-center gap-5">
          <div className="relative h-[116px] w-[116px] shrink-0">
            <svg viewBox="0 0 110 110" className="h-full w-full -rotate-90">
              <circle cx="55" cy="55" r={radius} fill="none" stroke="var(--chart-track)" strokeWidth="10" />
              {(() => {
                let offset = 0;
                return TYPES.map((type) => {
                  const value = counts[type.id];
                  if (!value) return null;
                  const length = (value / total) * circumference;
                  const dashOffset = -offset;
                  offset += length;
                  return (
                    <motion.circle
                      key={type.id}
                      cx="55"
                      cy="55"
                      r={radius}
                      fill="none"
                      stroke={type.color}
                      strokeWidth="10"
                      strokeLinecap="butt"
                      strokeDasharray={`${length} ${circumference - length}`}
                      strokeDashoffset={dashOffset}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ duration: 0.35 }}
                    />
                  );
                });
              })()}
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="mono text-xl font-black text-white">{total}</span>
              <span className="text-[9px] text-fg-500">مجموع</span>
            </div>
          </div>
          <div className="min-w-0 flex-1 space-y-2.5">
            {TYPES.map((type) => (
              <Row key={type.id} type={type} value={counts[type.id]} total={total} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default memo(AssignmentTypesChart);

function Row({
  type,
  value,
  total,
}: {
  type: (typeof TYPES)[number];
  value: number;
  total: number;
}) {
  const Icon = ICONS[type.id];
  return (
    <div className="flex items-center gap-2">
      <Icon size={14} style={{ color: type.color }} className="shrink-0" />
      <span className="flex-1 truncate text-[11px] text-fg-300">{type.label}</span>
      <span className="mono text-xs font-bold tabular-nums text-white">{value}</span>
      <span className="mono w-8 text-left text-[9px] tabular-nums text-fg-500">
        {Math.round((value / total) * 100)}%
      </span>
    </div>
  );
}
