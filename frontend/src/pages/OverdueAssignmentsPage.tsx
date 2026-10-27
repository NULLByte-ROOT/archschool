import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  AlarmClock,
  ArrowRight,
  CalendarClock,
  Check,
  ClipboardList,
  RefreshCw,
} from "lucide-react";
import { fetchOverdueAssignments } from "../api/client";
import type { Assignment } from "../api/client";
import Corners from "../components/Corners";
import PageHeader from "../components/PageHeader";
import { useNow } from "../hooks/useNow";
import {
  formatDue,
  parseDueTs,
  relativeDue,
  subjectName,
} from "../lib/assignments";

/**
 * صفحهٔ «تکالیف مهلت گذشته».
 *
 * فهرستِ کاملِ تکالیفی که مهلتشان گذشته است — چه کاربر آن‌ها را انجام داده
 * باشد و چه نه. منبع داده `GET /api/assignments/overdue` است، همان چیزی که
 * شمارندهٔ کارتِ صفحهٔ تکالیف را هم پر می‌کند.
 */

const dayCount = (ts: number, now: number) => {
  const a = new Date(ts);
  const b = new Date(now);
  const da = Date.UTC(a.getFullYear(), a.getMonth(), a.getDate());
  const db = Date.UTC(b.getFullYear(), b.getMonth(), b.getDate());
  return Math.max(0, Math.round((db - da) / 86_400_000));
};

const OverdueRow = memo(function OverdueRow({
  item,
  now,
  index,
}: {
  item: Assignment;
  now: number;
  index: number;
}) {
  const done = item.is_completed_by_me;
  const subject = subjectName(item.subject_id, item.course);
  const days = item.due_date ? dayCount(parseDueTs(item.due_date), now) : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.22, delay: Math.min(index, 8) * 0.03 }}
    >
      <Link
        to={`/assignments/${item.id}`}
        className={`group panel relative flex items-center gap-3.5 p-4 transition-colors hover:border-white/25 ${
          done ? "opacity-90" : ""
        }`}
      >
        <Corners className={done ? "border-success/30" : "border-danger/35"} />

        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border ${
            done
              ? "border-success/35 bg-success/12 text-success"
              : "border-danger/35 bg-danger/12 text-danger"
          }`}
        >
          {done ? <Check size={17} strokeWidth={3} /> : <AlarmClock size={17} />}
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3
              className={`truncate text-[13px] font-black ${
                done ? "text-fg-300" : "text-white"
              }`}
            >
              {item.title}
            </h3>
            <span
              className={`mono rounded-full border px-2 py-0.5 text-[9px] ${
                done
                  ? "border-success/35 bg-success/10 text-success"
                  : "border-danger/35 bg-danger/10 text-danger"
              }`}
            >
              {done ? "انجام‌شده" : "انجام‌نشده"}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10.5px] text-fg-500">
            {subject && <span className="truncate">{subject}</span>}
            {subject && item.due_date && <span className="text-fg-500">·</span>}
            {item.due_date && (
              <span className="tabular-nums">{formatDue(item.due_date)}</span>
            )}
          </div>
        </div>

        <div className="shrink-0 text-left">
          <p
            className={`mono text-[10.5px] tabular-nums ${
              done ? "text-fg-500" : "text-danger"
            }`}
          >
            {item.due_date ? relativeDue(item.due_date, now) : "بدون مهلت"}
          </p>
          {days > 0 && (
            <p className="mono mt-0.5 text-[9px] tabular-nums text-fg-500">
              {days} روز
            </p>
          )}
        </div>
      </Link>
    </motion.div>
  );
});

export default function OverdueAssignmentsPage() {
  const navigate = useNavigate();
  const now = useNow(30_000);
  const [items, setItems] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const reload = useCallback(() => setRefreshKey((key) => key + 1), []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchOverdueAssignments(controller.signal)
      .then((data) => {
        setItems(data);
        setLoading(false);
      })
      .catch((e: unknown) => {
        if (controller.signal.aborted) return;
        setError(e instanceof Error ? e.message : "خطا در بارگذاری داده‌ها");
        setLoading(false);
      });
    return () => controller.abort();
  }, [refreshKey]);

  const doneCount = useMemo(
    () => items.filter((item) => item.is_completed_by_me).length,
    [items]
  );

  return (
    <div className="mx-auto w-full max-w-4xl">
      <PageHeader
        kicker="overdue"
        title="تکالیف مهلت گذشته"
        subtitle="همهٔ تکالیفی که مهلتشان گذشته است — انجام‌شده و انجام‌نشده"
        action={
          <button onClick={() => navigate("/assignments")} className="btn-ghost">
            <ArrowRight size={14} />
            بازگشت به تکالیف
          </button>
        }
      />

      {!loading && !error && items.length > 0 && (
        <div className="mb-4 grid grid-cols-3 gap-3">
          {[
            { label: "کل", value: items.length, tone: "text-white" },
            { label: "انجام‌نشده", value: items.length - doneCount, tone: "text-danger" },
            { label: "انجام‌شده", value: doneCount, tone: "text-success" },
          ].map((stat) => (
            <div key={stat.label} className="panel relative p-3 text-center">
              <Corners />
              <p className={`mono text-lg font-black tabular-nums ${stat.tone}`}>
                {stat.value}
              </p>
              <p className="mt-0.5 text-[10px] text-fg-500">{stat.label}</p>
            </div>
          ))}
        </div>
      )}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="relative h-[74px] overflow-hidden rounded-2xl border border-white/10 bg-white/[0.02]"
              style={{ animationDelay: `${i * 90}ms` }}
            >
              <span className="absolute top-5 right-5 h-8 w-8 rounded-xl bg-white/10" />
              <span className="absolute top-5 right-16 h-3 w-1/3 rounded-md bg-white/10" />
              <span className="absolute bottom-5 right-16 h-3 w-1/4 rounded-md bg-white/8" />
            </div>
          ))}
        </div>
      ) : error ? (
        <div className="panel relative flex flex-col items-center justify-center gap-3 p-10 text-center sm:p-16">
          <Corners />
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-danger/30 bg-danger/10">
            <RefreshCw size={20} className="text-danger" />
          </span>
          <p className="text-sm font-semibold text-white">بارگذاری داده‌ها ناموفق بود</p>
          <p className="max-w-xs text-[12px] text-fg-500">{error}</p>
          <button onClick={reload} className="btn-primary mt-1">
            <RefreshCw size={14} />
            تلاش دوباره
          </button>
        </div>
      ) : items.length === 0 ? (
        <div className="panel relative flex flex-col items-center justify-center gap-3 p-10 text-center sm:p-16">
          <Corners />
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-success/30 bg-success/10">
            <CalendarClock size={20} className="text-success" />
          </span>
          <p className="text-sm font-semibold text-white">هیچ تکلیفی از مهلت نگذشته</p>
          <p className="max-w-xs text-[12px] text-fg-500">
            وقتی مهلت تکلیفی تمام شود، همین‌جا با وضعیت انجام‌شده یا انجام‌نشده
            نمایش داده می‌شود.
          </p>
          <button onClick={() => navigate("/assignments")} className="btn-ghost mt-1">
            <ClipboardList size={14} />
            رفتن به تکالیف
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item, index) => (
            <OverdueRow key={item.id} item={item} now={now} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}
