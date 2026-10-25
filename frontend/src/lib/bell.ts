import {
  DAY_MS,
  parseDue,
  calendarDayDiff,
  nextSchoolDayIndex,
  todayIndex,
} from "./assignments";
import { PERIOD_LABELS, PERIOD_TIMES, TIMETABLE } from "../data";
import type { SchoolPeriod } from "../api/client";

/**
 * منطق زمان مدرسه بر پایه‌ی زنگ‌های قابل تنظیم ادمین (GET /api/schedule).
 *
 * تا این‌جا کوت‌داون فقط «due - now» را حساب می‌کرد؛ اگر تکلیفی ساعت ۲۳:۵۹
 * امروز می‌بود و الان زنگ ۲ بود، «۱۲ ساعت مانده» نمایش داده می‌شد که بی‌معنی
 * است. حالا هر مهلتی به «پنجرهٔ مدرسه» همان روز منطبق می‌شود:
 *
 * - امروز: مهلت مؤثر = پایان روز مدرسه (به‌علاوهٔ یادداشت زنگ فعال).
 * - فردا یا بعدتر: تا «پایان زنگ آخر» همان روز، نه نیمه‌شب.
 * - روز تعطیل: مهلت خام.
 */

export interface Bell {
  /** شمارهٔ زنگ، از ۱ */
  number: number;
  label: string;
  /** دقیقه از نیمه‌شب */
  start: number;
  end: number;
}

function minutesToTime(total: number): string {
  const h = Math.floor(total / 60) % 24;
  const m = ((total % 60) + 60) % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

const FALLBACK_PERIODS: SchoolPeriod[] = PERIOD_TIMES.map((t, i) => ({
  period_number: i + 1,
  start_time: minutesToTime(t.start),
  end_time: minutesToTime(t.end),
}));

export function timeToMinutes(t: string): number {
  const match = /^(\d{1,2}):(\d{2})$/.exec(t.trim());
  if (!match) return Number.NaN;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h > 23 || m > 59) return Number.NaN;
  return h * 60 + m;
}

/** زنگ‌های معتبر مرتب‌شده؛ داده‌ی خراب → پیش‌فرض ثابت فعلی (۰۸:۰۰-۱۴:۰۰) */
export function bellsFrom(periods: SchoolPeriod[] | null | undefined): Bell[] {
  const parsed = (periods ?? [])
    .map((p) => ({
      number: p.period_number,
      label: PERIOD_LABELS[p.period_number - 1] ?? `زنگ ${p.period_number}`,
      start: timeToMinutes(p.start_time ?? ""),
      end: timeToMinutes(p.end_time ?? ""),
    }))
    .filter(
      (b) =>
        Number.isFinite(b.start) && Number.isFinite(b.end) && b.end > b.start
    )
    .sort((a, b) => a.start - b.start || a.number - b.number);
  return parsed.length > 0 ? parsed : bellsFrom(FALLBACK_PERIODS);
}

export const DEFAULT_PERIODS: SchoolPeriod[] = FALLBACK_PERIODS;

/** ساعت شروع مدرسه (ابتدای زنگ اول)، دقیقه از نیمه‌شب */
export function schoolStart(bells: Bell[]): number {
  return bells[0]?.start ?? 8 * 60;
}

/** ساعت پایان مدرسه (پایان زنگ آخر)، دقیقه از نیمه‌شب */
export function schoolEnd(bells: Bell[]): number {
  return bells[bells.length - 1]?.end ?? 14 * 60;
}

/** شنبه تا چهارشنبه = روز مدرسه */
export function isSchoolDay(date: Date): boolean {
  return todayIndex(date) < 5;
}

export interface DayBellWindow {
  dayStartMs: number;
  startMs: number;
  endMs: number;
  isSchoolDay: boolean;
}

/** پنجرهٔ مدرسهٔ یک روز مشخص بر اساس زنگ‌های ادمین */
export function dayBellWindow(date: Date, bells: Bell[]): DayBellWindow {
  const dayStartMs = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate()
  ).getTime();
  const school = isSchoolDay(date);
  return {
    dayStartMs,
    startMs: school ? dayStartMs + schoolStart(bells) * 60_000 : dayStartMs,
    endMs: school ? dayStartMs + schoolEnd(bells) * 60_000 : dayStartMs,
    isSchoolDay: school,
  };
}

/**
 * شمارهٔ اولین زنگی که «این درس» در روزِ `date` طبق برنامهٔ هفتگی (TIMETABLE)
 * دارد. بازگشت null یعنی روز تعطیل است یا این درس در آن روز برنامه ندارد؛
 * در این حالت شمارش به‌ناچار به زنگ اول کل روز برمی‌گردد.
 * سلول‌های چنددرسه (multi) هم بررسی می‌شوند؛ در روزهای ۴‌زنگِ یک‌درسه (span=4)
 * درس از زنگ ۱ شروع می‌شود.
 */
export function subjectBellNumber(
  subjectId: string | null | undefined,
  date: Date
): number | null {
  if (!subjectId) return null;
  const dayIndex = todayIndex(date);
  const day = TIMETABLE[dayIndex];
  if (!day) return null; // پنجشنبه/جمعه
  let period = 0; // زنگ‌های مصرف‌شده تا این لحظه
  for (const cell of day.cells) {
    const subjectIds =
      cell.kind === "class"
        ? [cell.subject.id]
        : cell.kind === "multi"
          ? cell.subjects.map((s) => s.id)
          : [];
    if (subjectIds.includes(subjectId)) return period + 1;
    period += cell.span;
  }
  return null;
}

/** زنگ فعال الان (اگر داخل یک زنگ باشیم) */
export function activeBell(date: Date, bells: Bell[]): Bell | null {
  const window = dayBellWindow(date, bells);
  if (!window.isSchoolDay) return null;
  const now = date.getTime();
  for (const bell of bells) {
    if (
      now >= window.dayStartMs + bell.start * 60_000 &&
      now < window.dayStartMs + bell.end * 60_000
    ) {
      return bell;
    }
  }
  return null;
}

// ------------------------------------------------------------------
//  وضعیت لحظه‌ای مدرسه: زنگ، زنگ تفریح، قبل/بعد از مدرسه
// ------------------------------------------------------------------

export type CurrentBellState =
  | {
      state: "class";
      bell: Bell;
      bellIndex: number;
      remainingMs: number;
      progress: number;
      endsAtMs: number;
    }
  | {
      state: "break";
      previousBell: Bell;
      nextBell: Bell;
      nextBellIndex: number;
      remainingMs: number;
      progress: number;
      startedAtMs: number;
      endsAtMs: number;
    }
  | {
      state: "before";
      firstBell: Bell;
      remainingMs: number;
      startsAtMs: number;
    }
  | { state: "after"; lastBell: Bell }
  | { state: "holiday" };

/**
 * وضعیت مدرسه را از روی همان زنگ‌های ذخیره‌شده در پنل ادمین می‌سازد.
 *
 * «زنگ تفریح» یک رکورد جداگانه در دیتابیس نیست؛ هر فاصلهٔ خالی بین پایان
 * زنگ N و شروع زنگ N+1 یک زنگ تفریح است. به همین دلیل تغییر زمان‌ها در
 * `/admin/bells` بلافاصله هم زنگ جاری و هم زنگ تفریح را جابه‌جا می‌کند.
 */
export function getCurrentBellState(
  now: number = Date.now(),
  bells: Bell[] = []
): CurrentBellState {
  const list = bells.length > 0 ? bells : bellsFrom(DEFAULT_PERIODS);
  const date = new Date(now);
  const window = dayBellWindow(date, list);
  if (!window.isSchoolDay) return { state: "holiday" };

  const at = (minute: number) => window.dayStartMs + minute * 60_000;
  const remaining = (target: number) => Math.max(0, target - now);

  const first = list[0];
  if (now < at(first.start)) {
    return {
      state: "before",
      firstBell: first,
      remainingMs: remaining(at(first.start)),
      startsAtMs: at(first.start),
    };
  }

  for (let index = 0; index < list.length; index += 1) {
    const bell = list[index];
    const startMs = at(bell.start);
    const endMs = at(bell.end);
    if (now >= startMs && now < endMs) {
      return {
        state: "class",
        bell,
        bellIndex: index,
        remainingMs: remaining(endMs),
        progress: Math.min(1, Math.max(0, (now - startMs) / (endMs - startMs))),
        endsAtMs: endMs,
      };
    }
  }

  for (let index = 0; index < list.length - 1; index += 1) {
    const previousBell = list[index];
    const nextBell = list[index + 1];
    const startedAtMs = at(previousBell.end);
    const endsAtMs = at(nextBell.start);
    if (endsAtMs > startedAtMs && now >= startedAtMs && now < endsAtMs) {
      return {
        state: "break",
        previousBell,
        nextBell,
        nextBellIndex: index + 1,
        remainingMs: remaining(endsAtMs),
        progress: Math.min(
          1,
          Math.max(0, (now - startedAtMs) / (endsAtMs - startedAtMs))
        ),
        startedAtMs,
        endsAtMs,
      };
    }
  }

  return { state: "after", lastBell: list[list.length - 1] };
}

export interface ScheduleTarget {
  /** اندیس روز در TIMETABLE (۰ = شنبه) */
  dayIndex: number;
  /** آیا هدف، نزدیک‌ترین روز مدرسه‌ی بعد از امروز است؟ (نه امروز) */
  isTomorrow: boolean;
  /** آیا ساعت از پایان مدرسه گذشته است؟ */
  isAfterSchool: boolean;
  /** آیا امروز پنجشنبه یا جمعه (تعطیلات آخر هفته) است؟ */
  isWeekend: boolean;
  /** آیا روز هدف دقیقاً فردای تقویمی است؟ */
  isLiteralTomorrow: boolean;
}

/**
 * «برنامه‌ی پیش‌رو» را بر اساس پایانِ آخرین زنگِ ذخیره‌شده حساب می‌کند.
 * اگر ادمین مدرسه را تا ۱۵:۰۰ تمدید کند، داشبورد هم بلافاصله بعد از ۱۵:۰۰
 * به روز بعد می‌رود — نه ساعت ۱۴:۰۰ هاردکدشده.
 */
export function scheduleTarget(
  now: number = Date.now(),
  bells: Bell[] = []
): ScheduleTarget {
  const base = new Date(now);
  const minutes = base.getHours() * 60 + base.getMinutes();
  const today = todayIndex(base);
  const isWeekend = today >= TIMETABLE.length;
  const isAfterSchool = minutes >= schoolEnd(bells) || isWeekend;
  const dayIndex = isAfterSchool ? nextSchoolDayIndex(today) : today;
  return {
    dayIndex,
    isTomorrow: isAfterSchool || dayIndex !== today,
    isAfterSchool,
    isWeekend,
    isLiteralTomorrow: dayIndex === (today + 1) % 7,
  };
}

// ------------------------------------------------------------------
//  کوت‌داون منطبق با زنگ‌ها
// ------------------------------------------------------------------

export interface DueCountdown {
  /** میلی‌ثانیهٔ تفاوت خام (مهلت - حال) */
  raw: number;
  /** میلی‌ثانیهٔ تفاوت تا هدف دقیق (شروع زنگ) */
  aligned: number;
  /** هدف دقیق: شروع زنگ مربوط به روز مهلت بر اساس برنامهٔ ادمین */
  alignedDueMs: number;
  /** اختلاف روز تقویمی (۰ = امروز) */
  dayDiff: number;
  overdue: boolean;
  /** کمتر از ۴۸ ساعت مانده */
  urgent: boolean;
  /** یادداشت زنگ: «تا شروع زنگ ۲» یا «تا پایان مدرسه» */
  periodNote: string | null;
  /** آیا مهلت با زنگ‌ها منطبق/برش خورده است؟ */
  isAligned: boolean;
  /** لیبل فارسی کامل برای نمایش */
  label: string;
  /** لیبل کوتاه (فقط «مانده») */
  short: string;
}

const fa = new Intl.NumberFormat("en-US");
const HOUR_MS = 3_600_000;

/**
 * `when` is a Persian-calendar date string that only depends on the due day.
 * Caching it keeps `dueCountdown` free of Intl work on repeat renders (it runs
 * for every visible card on every clock tick).
 */
const WHEN_CACHE = new Map<string, string>();
const WHEN_CACHE_LIMIT = 1000;

function dueDayLabel(dueDate: Date): string {
  const key = `${dueDate.getFullYear()}-${dueDate.getMonth()}-${dueDate.getDate()}`;
  const hit = WHEN_CACHE.get(key);
  if (hit !== undefined) return hit;
  const label = dueDate.toLocaleDateString("fa-IR-u-nu-latn", {
    day: "numeric",
    month: "long",
  });
  if (WHEN_CACHE.size >= WHEN_CACHE_LIMIT) WHEN_CACHE.clear();
  WHEN_CACHE.set(key, label);
  return label;
}

function humanLeft(ms: number): string {
  if (ms <= 0) return "";
  if (ms < 60_000) {
    return `${fa.format(Math.max(1, Math.round(ms / 1000)))} ثانیه`;
  }
  const minutes = Math.round(ms / 60_000);
  if (minutes < 60) return `${fa.format(minutes)} دقیقه`;
  const hours = Math.floor(minutes / 60);
  const rem = minutes % 60;
  if (ms < DAY_MS) {
    return rem
      ? `${fa.format(hours)} ساعت و ${fa.format(rem)} دقیقه`
      : `${fa.format(hours)} ساعت`;
  }
  const days = Math.floor(hours / 24);
  const rh = hours % 24;
  return rh
    ? `${fa.format(days)} روز و ${fa.format(rh)} ساعت`
    : `${fa.format(days)} روز`;
}

/**
 * کوت‌داون دقیق تا شروعِ زنگِ مرتبط با روز مهلت (بر پایهٔ زنگ‌های ادمین).
 *
 * منطق هدف:
 * - روز آینده درسی: شروعِ زنگی که «درسِ تکلیف» (subjectId) در آن روز برنامه
 *   دارد؛ اگر درس در آن روز نبود یا زنگش تعریف نشده بود، شروعِ زنگ اول
 *   (مثال: شنبه ۰۸:۰۰). با این حال هر دو صفحهٔ «تکالیف» و «جزئیات تکلیف»
 *   از همین یک تابع با یک آرگومان subjectId استفاده می‌کنند.
 * - امروز: اگر زنگِ موضوع تکلیف هنوز شروع نشده، دقیقاً شروعِ همان زنگ؛
 *   وگرنه شروعِ نزدیک‌ترین زنگِ شروع‌نشده؛ اگر همهٔ زنگ‌ها شروع شده‌اند،
 *   تا پایان روز مدرسه.
 * - روز تعطیل: خودِ مهلت.
 * `bells` خالی/ناموجود → پیش‌فرض ثابت ۰۸:۰۰ تا ۱۴:۰۰.
 */
export function dueCountdown(
  due: string | null | undefined,
  now: number,
  bells: Bell[],
  subjectId?: string | null
): DueCountdown | null {
  if (!due) return null;
  const dueDate = parseDue(due);
  const dueMs = dueDate.getTime();
  if (Number.isNaN(dueMs)) return null;

  const dayDiff = calendarDayDiff(dueDate, new Date(now));
  const window = dayBellWindow(dueDate, bells);
  const subjectBell = subjectBellNumber(subjectId, dueDate);

  let target: number;
  let isAligned = false;
  if (!window.isSchoolDay) {
    // روز تعطیل: مهلت خام
    target = dueMs;
  } else if (dayDiff === 0) {
    // امروز: اول زنگِ موضوع تکلیف اگر هنوز شروع نشده؛ وگرنه نزدیک‌ترین
    // زنگِ شروع‌نشده؛ وگرنه پایان مدرسه
    const pendingSubjectBell = subjectBell
      ? bells.find(
          (b) =>
            b.number === subjectBell &&
            window.dayStartMs + b.start * 60_000 > now
        )
      : null;
    const upcoming =
      pendingSubjectBell ??
      bells.find((b) => window.dayStartMs + b.start * 60_000 > now);
    if (upcoming) {
      target = window.dayStartMs + upcoming.start * 60_000;
      isAligned = true;
    } else {
      target = window.endMs;
      isAligned = true;
    }
  } else {
    // روز آینده درسی: شروعِ زنگِ درسِ تکلیف (یا زنگ اول اگر درس در آن
    // روز برنامه ندارد)
    const subjectPending = subjectBell
      ? bells.find((b) => b.number === subjectBell)
      : null;
    target =
      window.dayStartMs + (subjectPending?.start ?? schoolStart(bells)) * 60_000;
    isAligned = true;
  }

  // «گذشته» یعنی هدف (شروع زنگ) گذشته است، نه ۲۳:۵۹ خام
  const overdue = target <= now;
  const aligned = target - now;
  const alignedDueMs = target;

  // فوری: کمتر از ۴۸ ساعت تا هدف
  const urgent = !overdue && aligned > 0 && aligned < 48 * HOUR_MS;

  let periodNote: string | null = null;
  if (isAligned && !overdue) {
    const targetBell = bells.find(
      (b) => window.dayStartMs + b.start * 60_000 === target
    );
    if (targetBell) {
      periodNote = `تا شروع ${targetBell.label}`;
    } else {
      periodNote = "تا پایان مدرسه";
    }
  }

  const when =
    dayDiff === 0 ? "امروز" : dayDiff === 1 ? "فردا" : dueDayLabel(dueDate);

  let label: string;
  if (overdue) {
    if (dayDiff < 0) {
      const days = -dayDiff;
      label = days === 1 ? "۱ روز گذشته" : `${fa.format(days)} روز گذشته`;
    } else {
      label = "مهلت گذشته";
    }
  } else {
    label = `${when} · ${humanLeft(aligned)} مانده${
      periodNote ? ` · ${periodNote}` : ""
    }`;
  }

  return {
    raw: dueMs - now,
    aligned: Math.max(0, aligned),
    alignedDueMs,
    dayDiff,
    overdue,
    urgent,
    periodNote,
    isAligned,
    label,
    short: overdue ? "مهلت گذشته" : `${humanLeft(aligned)} مانده`,
  };
}

export type CountdownTone = "red" | "yellow" | "none";

/** رنگ مهلت بر اساس زمان منطبق‌شده (نه تفاوت خام) */
export function countdownTone(c: DueCountdown | null): CountdownTone {
  if (!c) return "none";
  if (c.overdue || c.aligned < DAY_MS) return "red";
  if (c.aligned < DAY_MS * 2) return "yellow";
  return "none";
}
