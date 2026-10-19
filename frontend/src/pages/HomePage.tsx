import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CalendarDays, Clock } from "lucide-react";
import { fetchAssignments } from "../api/client";
import type { Assignment } from "../api/client";
import Corners from "../components/Corners";
import Timetable from "../components/Timetable";
import { useNow } from "../hooks/useNow";
import { jalaliTime, jalaliToday } from "../lib/assignments";

export default function HomePage() {
  const [items, setItems] = useState<Assignment[]>([]);
  const now = useNow(30_000);

  useEffect(() => {
    fetchAssignments().then(setItems).catch(console.error);
  }, []);

  const today = jalaliToday(now);
  const time = jalaliTime(now);

  return (
    <div>
      {/* نوار اطلاعات بالا */}
      <div className="mb-6 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3.5">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl border border-white/12 bg-white/[0.04]">
            <CalendarDays size={18} className="text-white" />
          </span>
          <div>
            <p className="text-[15px] font-bold text-white">امروز: {today}</p>
            <p className="mono text-[10px] tracking-[0.18em] text-fg-500 uppercase">// TODAY</p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
            <Clock size={14} className="text-fg-500" />
            <span className="mono text-sm tabular-nums text-fg-100" dir="ltr">
              {time}
            </span>
          </span>
          <span className="badge">
            <span className="dot animate-pulse" />
            DASHBOARD
          </span>
        </div>
      </div>

      {/* برنامه هفتگی */}
      <motion.section
        initial={{ opacity: 0, y: 20 }}
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
              <h2 className="text-base font-bold text-white">برنامه هفتگی</h2>
              <p className="mono text-[10px] tracking-widest text-fg-500">
                // CLASS TIMETABLE · YAZDAHOM NETWORK 1
              </p>
            </div>
          </div>
          <span className="badge">شنبه تا چهارشنبه</span>
        </div>

        <Timetable assignments={items} />
      </motion.section>
    </div>
  );
}
