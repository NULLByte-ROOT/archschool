import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowUpRight, CheckCircle2, CircleDashed } from "lucide-react";
import { useIsMobileWidth } from "../hooks/useMediaQuery";

export default function ActivityChart({
  completed,
  total,
}: {
  completed: number;
  total: number;
}) {
  const navigate = useNavigate();
  const isMobile = useIsMobileWidth();
  const pending = Math.max(0, total - completed);
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  const radius = 54;
  const circumference = useMemo(() => 2 * Math.PI * radius, []);

  return (
    <motion.button
      type="button"
      onClick={() => navigate("/assignments")}
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
      className="panel panel-hover relative flex w-full flex-col overflow-hidden rounded-3xl p-5 text-right"
    >
      <div className="mb-1 flex items-center justify-between gap-2">
        <div>
          <p className="mono-label">// ACTIVITY</p>
          <h3 className="text-base font-bold text-white">وضعیت تکالیف</h3>
        </div>
        <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/10 bg-white/[0.04] text-fg-300">
          <ArrowUpRight size={15} />
        </span>
      </div>

      {isMobile ? (
        <div className="mt-5">
          <div className="mb-3 flex items-end justify-between">
            <span className="mono text-3xl font-black tabular-nums text-white">{pct}%</span>
            <span className="text-[11px] text-fg-500">
              {completed} از {total} انجام شده
            </span>
          </div>
          <div className="relative h-4 overflow-hidden rounded-full bg-white/[0.08]">
            <motion.div
              className="absolute inset-y-0 right-0 rounded-full"
              style={{
                width: `${total ? (completed / total) * 100 : 0}%`,
                background: "linear-gradient(90deg, var(--color-success), #6ee7b7)",
                willChange: "transform",
              }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
          <div className="mt-4 grid grid-cols-2 gap-2">
            <Legend color="var(--color-success)" label="انجام‌شده" value={completed} />
            <Legend color="var(--chart-muted)" label="باقی‌مانده" value={pending} />
          </div>
        </div>
      ) : (
        <div className="mt-3 flex items-center gap-5">
          <div className="relative h-[140px] w-[140px] shrink-0">
            <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
              <circle
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                stroke="var(--chart-track)"
                strokeWidth="12"
              />
              <motion.circle
                cx="70"
                cy="70"
                r={radius}
                fill="none"
                stroke="var(--color-success)"
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={circumference}
                initial={{ strokeDashoffset: circumference }}
                animate={{
                  strokeDashoffset: circumference * (1 - (total ? completed / total : 0)),
                }}
                transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
                style={{ willChange: "stroke-dashoffset" }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="mono text-2xl font-black tabular-nums text-white">{pct}%</span>
              <span className="text-[10px] text-fg-500">تکمیل‌شده</span>
            </div>
          </div>

          <div className="min-w-0 flex-1 space-y-2.5">
            <Legend color="var(--color-success)" label="انجام‌شده" value={completed} />
            <Legend color="var(--chart-muted)" label="باقی‌مانده" value={pending} />
            <div className="border-t border-white/8 pt-2.5">
              <p className="text-[11px] text-fg-500">
                مجموع <span className="font-bold text-fg-100">{total}</span> تکلیف
              </p>
            </div>
          </div>
        </div>
      )}
    </motion.button>
  );
}

function Legend({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <div className="flex items-center gap-2">
      {label === "انجام‌شده" ? (
        <CheckCircle2 size={14} style={{ color }} className="shrink-0" />
      ) : (
        <CircleDashed size={14} style={{ color }} className="shrink-0" />
      )}
      <span className="flex-1 truncate text-[11px] text-fg-300">{label}</span>
      <span className="mono text-xs font-bold tabular-nums text-white">{value}</span>
    </div>
  );
}
