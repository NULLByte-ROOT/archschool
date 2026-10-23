import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import { CalendarDays, Clock } from "lucide-react";
import { fetchAssignments } from "../api/client";
import type { Assignment } from "../api/client";
import Corners from "../components/Corners";
import CurrentPeriodCard from "../components/CurrentPeriodCard";
import Timetable from "../components/Timetable";
import TomorrowSchedule from "../components/TomorrowSchedule";
import PageHeader from "../components/PageHeader";
import { useNow } from "../hooks/useNow";
import { groupAssignmentsBySubject, jalaliToday } from "../lib/assignments";

/**
 * The ticking header clock. It owns its own 1s interval so the rest of the
 * page only re-renders when something factual changes (day / assignments).
 */
function LiveClock() {
  const now = useNow(1000);
  return (
    <span className="badge">
      <Clock size={11} />
      <span className="mono tabular-nums" dir="ltr">
        {new Date(now).toLocaleTimeString("fa-IR-u-nu-latn", {
          hour: "2-digit",
          minute: "2-digit",
        })}
      </span>
    </span>
  );
}

export default function TimetablePage() {
  const [items, setItems] = useState<Assignment[]>([]);
  const [error, setError] = useState<string | null>(null);
  // Day-level granularity: the header date, the schedule preview and the
  // chosen day change at most once a minute — not once a second.
  const now = useNow(30_000);

  useEffect(() => {
    fetchAssignments()
      .then(setItems)
      .catch((e: unknown) => {
        setError(e instanceof Error ? e.message : "خطا در بارگذاری");
      });
  }, []);

  const bySubject = useMemo(() => groupAssignmentsBySubject(items), [items]);

  return (
    <div>
      <PageHeader
        kicker="timetable"
        title="برنامه هفتگی"
        subtitle={`شنبه تا چهارشنبه · ۰۸:۰۰ تا ۱۴:۰۰ · امروز ${jalaliToday(now)}`}
        action={<LiveClock />}
      />

      <div className="mb-5">
        <CurrentPeriodCard bySubject={bySubject} />
      </div>

      {error && (
        <p className="mb-4 rounded-xl border border-danger/25 bg-danger/10 px-3 py-2 text-xs text-danger">
          {error}
        </p>
      )}

      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="panel noise relative overflow-hidden rounded-2xl p-5 sm:p-6"
      >
        <Corners />
        <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl border border-white/15 bg-white/5">
              <CalendarDays size={18} className="text-white" />
            </span>
            <div>
              <h2 className="text-base font-bold text-white">جدول کلاس‌ها</h2>
              <p className="mono text-[10px] tracking-widest text-fg-500">
                // CLASS TIMETABLE · YAZDAHOM NETWORK 1
              </p>
            </div>
          </div>
          <span className="badge">۴ زنگ · ۹۰ دقیقه‌ای</span>
        </div>

        <Timetable bySubject={bySubject} />
      </motion.section>

      <TomorrowSchedule bySubject={bySubject} now={now} />
    </div>
  );
}
