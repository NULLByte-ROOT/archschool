import { useEffect, useMemo, useState } from "react";
import { fetchSchoolSchedule } from "../api/client";
import type { SchoolPeriod } from "../api/client";
import { DEFAULT_PERIODS, bellsFrom, type Bell } from "../lib/bell";

/**
 * یک منبع مشترک برای زنگ‌های مدرسه. چند مؤلفه (صفحهٔ تکالیف، پنل ادمین)
 * همه از همین هوک استفاده می‌کنند تا فقط یک درخواست ارسال شود؛ پاسخ در
 * حافظهٔ ماژول کش می‌شود.
 */

let cached: SchoolPeriod[] | null = null;
let inflight: Promise<SchoolPeriod[]> | null = null;
let version = 0;
const listeners = new Set<() => void>();

async function load(): Promise<SchoolPeriod[]> {
  if (cached) return cached;
  if (!inflight) {
    inflight = fetchSchoolSchedule()
      .then((schedule) => {
        const periods =
          Array.isArray(schedule.periods) && schedule.periods.length > 0
            ? [...schedule.periods].sort((a, b) => a.period_number - b.period_number)
            : DEFAULT_PERIODS;
        cached = periods;
        version += 1;
        listeners.forEach((fn) => fn());
        return periods;
      })
      .catch((error: unknown) => {
        // بدون زنگ‌ها هم صفحه باید کار کند: پیش‌فرض ثابت ۰۸:۰۰-۱۴:۰۰
        console.warn("[bell] schedule unavailable, using built-in 08:00-14:00", error);
        inflight = null;
        return DEFAULT_PERIODS;
      });
  }
  return inflight;
}

/** زنگ‌های ادمین + فهرست Bell آمادهٔ محاسبه و نحوهٔ بازآوری دستی */
export function useBellSchedule(): {
  periods: SchoolPeriod[];
  bells: Bell[];
  ready: boolean;
  reload: () => void;
} {
  const [periods, setPeriods] = useState<SchoolPeriod[]>(() => cached ?? DEFAULT_PERIODS);
  const [ready, setReady] = useState(() => cached !== null);

  useEffect(() => {
    let active = true;
    const listener = () => {
      if (active) {
        setPeriods(cached ?? DEFAULT_PERIODS);
        setReady(true);
      }
    };
    listeners.add(listener);
    load().finally(() => {
      if (active) {
        setPeriods(cached ?? DEFAULT_PERIODS);
        setReady(true);
      }
    });
    return () => {
      active = false;
      listeners.delete(listener);
    };
  }, []);

  // برای پنل ادمین: بعد از ذخیره، حافظهٔ مشترک را تازه کن
  const reload = () => {
    cached = null;
    inflight = null;
    void load();
  };

  // A fresh array on every render would invalidate every `useMemo`/`memo` that
  // depends on the bell schedule (all assignment cards take it as a prop).
  const bells = useMemo(() => bellsFrom(periods), [periods]);

  return { periods, bells, ready, reload };
}

/** برای پنل ادمین: بعد از ذخیره، حافظهٔ مشترک را با مقادیر جدید پر کن */
export function refreshBellCache(periods: SchoolPeriod[]): void {
  cached = [...periods].sort((a, b) => a.period_number - b.period_number);
  version += 1;
  listeners.forEach((fn) => fn());
}
