import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { BellRing, Loader2, RotateCcw, Save } from "lucide-react";
import type { SchoolPeriod } from "../api/client";
import { updateSchoolSchedule } from "../api/client";
import { useBellSchedule, refreshBellCache } from "../hooks/useBellSchedule";
import Corners from "./Corners";

const PERIOD_NAMES = ["زنگ ۱", "زنگ ۲", "زنگ ۳", "زنگ ۴"];

const DEFAULT_ROWS: SchoolPeriod[] = [
  { period_number: 1, start_time: "08:00", end_time: "09:30" },
  { period_number: 2, start_time: "09:30", end_time: "11:00" },
  { period_number: 3, start_time: "11:00", end_time: "12:30" },
  { period_number: 4, start_time: "12:30", end_time: "14:00" },
];

/**
 * تنظیم زنگ‌های مدرسه (فقط ادمین): ساعت شروع/پایان ۴ زنگ.
 * کوت‌داون تکالیف و برنامه‌ی زنگ فعال از همین مقادیر خوانده می‌شود.
 */
export default function BellSchedulePanel() {
  const { periods, ready, reload } = useBellSchedule();
  const [rows, setRows] = useState<SchoolPeriod[]>(() => periods);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (ready && periods.length === 4) setRows(periods);
  }, [ready, periods]);

  function patch(index: number, field: "start_time" | "end_time", value: string) {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, [field]: value } : row))
    );
    setSaved(false);
  }

  function resetDefaults() {
    setRows(DEFAULT_ROWS);
    setSaved(false);
  }

  async function save() {
    setError(null);
    // اعتبارسنجی ساده‌ی سمت کلاینت (سرور هم دوباره اعتبارسنجی می‌کند)
    const sorted = [...rows].sort((a, b) => a.period_number - b.period_number);
    for (const row of sorted) {
      if (!row.start_time || !row.end_time) {
        setError("هر ۴ زنگ باید شروع و پایان داشته باشند");
        return;
      }
    }
    setSaving(true);
    try {
      const updated = await updateSchoolSchedule(sorted);
      refreshBellCache(updated.periods);
      reload();
      setRows(updated.periods);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ذخیره‌سازی ناموفق بود");
    } finally {
      setSaving(false);
    }
  }

  const dirty = JSON.stringify(rows) !== JSON.stringify(periods);

  return (
    <section className="panel relative p-5">
      <Corners />
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="mono-label">// BELL TIMES</p>
          <h3 className="flex items-center gap-2 text-base font-bold text-white">
            <BellRing size={16} className="text-white" />
            زنگ‌های مدرسه
          </h3>
          <p className="mt-1 text-[11px] text-fg-500">
            این ساعت‌ها مبنای زمان‌بندی زنگ فعال و محاسبه‌ی دقیق «مقدار مانده» تکالیف است.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={resetDefaults}
            className="btn-ghost !py-2"
            title="بازگشت به ۰۸:۰۰ تا ۱۴:۰۰"
          >
            <RotateCcw size={13} />
            پیش‌فرض
          </button>
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="btn-primary !py-2"
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            {saving ? "ذخیره…" : "ذخیره"}
          </button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {rows.map((row, index) => (
          <div
            key={row.period_number}
            className="rounded-2xl border border-white/10 bg-white/[0.03] p-3"
          >
            <p className="mb-2 text-[12px] font-bold text-white">
              {PERIOD_NAMES[index] ?? `زنگ ${row.period_number}`}
            </p>
            <div className="space-y-2">
              <label className="block">
                <span className="mb-1 block text-[10px] text-fg-500">شروع</span>
                <input
                  type="time"
                  dir="ltr"
                  value={row.start_time}
                  onChange={(e) => patch(index, "start_time", e.target.value)}
                  className="mono w-full rounded-xl border border-white/12 bg-black/30 px-2.5 py-2 text-[13px] text-white outline-none focus:border-white/35"
                />
              </label>
              <label className="block">
                <span className="mb-1 block text-[10px] text-fg-500">پایان</span>
                <input
                  type="time"
                  dir="ltr"
                  value={row.end_time}
                  onChange={(e) => patch(index, "end_time", e.target.value)}
                  className="mono w-full rounded-xl border border-white/12 bg-black/30 px-2.5 py-2 text-[13px] text-white outline-none focus:border-white/35"
                />
              </label>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <p className="mt-3 rounded-xl border border-danger/30 bg-danger/10 px-3 py-2 text-[11px] text-danger">
          {error}
        </p>
      )}
      {saved && !error && (
        <motion.p
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-3 rounded-xl border border-success/30 bg-success/10 px-3 py-2 text-[11px] text-success"
        >
          زنگ‌ها ذخیره شد و از همین لحظه در همه جا اعمال می‌شود.
        </motion.p>
      )}
      {!saved && dirty && !error && (
        <p className="mt-3 text-[10px] text-fg-500">تغییراتی بدون ذخیره وجود دارد.</p>
      )}
    </section>
  );
}
