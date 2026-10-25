import { useEffect, useMemo, useState } from "react";
import { fetchSchoolSchedule } from "../api/client";
import type { SchoolPeriod } from "../api/client";
import { DEFAULT_PERIODS, bellsFrom, type Bell } from "../lib/bell";

/**
 * یک منبع مشترک برای زنگ‌های مدرسه. چند مؤلفه (صفحهٔ تکالیف، برنامه هفتگی،
 * پنل ادمین) همه از همین هوک استفاده می‌کنند تا فقط یک درخواست ارسال شود.
 *
 * نکتهٔ مهم: هر بار mount شدن هوک، یک درخواست تازه هم می‌فرستد. قبلاً فقط
 * کش ماژول برگردانده می‌شد و اگر ادمین زمان‌ها را عوض می‌کرد و صفحهٔ دیگری
 * از قبل mount بود، همان زمان‌های قدیمی می‌ماند. حالا عوض کردن زنگ‌ها در
 * `/admin/bells` هم از طریق `refreshBellCache` و هم با refetch دوباره
 * منتشر می‌شود.
 */

let cached: SchoolPeriod[] | null = null;
let inflight: Promise<SchoolPeriod[]> | null = null;
const listeners = new Set<() => void>();

function notify(): void {
  listeners.forEach((fn) => fn());
}

function load(force = false): Promise<SchoolPeriod[]> {
  if (force) cached = null;
  if (!force && cached) return Promise.resolve(cached);
  if (inflight) return inflight;

  inflight = fetchSchoolSchedule()
    .then((schedule) => {
      const periods =
        Array.isArray(schedule.periods) && schedule.periods.length > 0
          ? [...schedule.periods].sort((a, b) => a.period_number - b.period_number)
          : DEFAULT_PERIODS;
      cached = periods;
      notify();
      return periods;
    })
    .catch((error: unknown) => {
      // بدون زنگ‌ها هم صفحه باید کار کند: پیش‌فرض ثابت ۰۸:۰۰-۱۴:۰۰
      console.warn("[bell] schedule unavailable, using built-in 08:00-14:00", error);
      cached = DEFAULT_PERIODS;
      notify();
      return DEFAULT_PERIODS;
    })
    .finally(() => {
      inflight = null;
    });

  return inflight;
}

/** زنگ‌های ادمین + فهرست Bell آمادهٔ محاسبه و نحوهٔ بازآوری دستی */
export function useBellSchedule(): {
  periods: SchoolPeriod[];
  bells: Bell[];
  ready: boolean;
  reload: () => Promise<void>;
} {
  const [periods, setPeriods] = useState<SchoolPeriod[]>(
    () => cached ?? DEFAULT_PERIODS
  );
  const [ready, setReady] = useState(() => cached !== null);

  useEffect(() => {
    let active = true;

    const apply = () => {
      if (!active) return;
      setPeriods(cached ?? DEFAULT_PERIODS);
      setReady(true);
    };

    listeners.add(apply);
    // Always ask the server on mount: a stale module cache is exactly what made
    // the timetable ignore freshly saved bell times.
    void load(true).then(apply);

    const onFocus = () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") {
        return;
      }
      void load(true).then(apply);
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);

    return () => {
      active = false;
      listeners.delete(apply);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, []);

  // برای پنل ادمین: بعد از ذخیره، حافظهٔ مشترک را تازه کن
  const reload = async (): Promise<void> => {
    const fresh = await load(true);
    setPeriods(fresh);
    setReady(true);
  };

  // A fresh array on every render would invalidate every `useMemo`/`memo` that
  // depends on the bell schedule (all assignment cards take it as a prop).
  const bells = useMemo(() => bellsFrom(periods), [periods]);

  return { periods, bells, ready, reload };
}

/** برای پنل ادمین: بعد از ذخیره، حافظهٔ مشترک را با مقادیر جدید پر کن */
export function refreshBellCache(periods: SchoolPeriod[]): void {
  cached = [...periods].sort((a, b) => a.period_number - b.period_number);
  notify();
}
