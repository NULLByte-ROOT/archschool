import {
  SUBJECTS,
  TIMETABLE,
  PERIOD_COUNT,
  PERIOD_LABELS,
  PERIOD_TIMES,
  type Day,
  type Subject,
} from "../data";
import type { Assignment, User } from "../api/client";

/**
 * Admins and owners manage every assignment; members create/edit nothing
 * (read-only). Mirrors the backend `_can_manage` check — the legacy "editor"
 * role no longer exists and boot migrations convert those users to admin.
 */
export function canManageAssignment(
  _assignment: Assignment,
  user: User | null
): boolean {
  if (!user) return false;
  return user.is_admin || user.role === "admin" || user.role === "owner";
  // NOTE: creators who are plain members no longer get edit rights, matching
  // the new permission model ("Member cannot create/edit/delete").
}

// ------------------------------------------------------------------
//  دسته‌بندی موضوع تکلیف
// ------------------------------------------------------------------
export interface CategoryItem {
  id: string;
  label: string;
}

export interface CategoryGroup {
  id: string;
  label: string;
  items: CategoryItem[];
}

export const CATEGORY_GROUPS: CategoryGroup[] = [
  {
    id: "homework",
    label: "تکلیف‌ها",
    items: [
      { id: "written", label: "نوشتنی" },
      { id: "practical", label: "پروژه عملی" },
      { id: "research", label: "تحقیق" },
    ],
  },
  {
    id: "exam",
    label: "امتحان",
    items: [
      { id: "oral", label: "پرسش شفاهی" },
      { id: "written_exam", label: "کتبی" },
      { id: "podmani", label: "پودمانی" },
      { id: "term1", label: "نوبت اول" },
      { id: "term2", label: "نوبت دوم" },
      { id: "question", label: "پرسش" },
    ],
  },
];

export function categoryGroup(id: string): CategoryGroup | undefined {
  return CATEGORY_GROUPS.find((g) => g.id === id);
}

export function categoryItemLabel(subtype: string): string {
  for (const group of CATEGORY_GROUPS) {
    const item = group.items.find((i) => i.id === subtype);
    if (item) return item.label;
  }
  return subtype;
}

export function categoryTitle(category: string, subtype: string): string {
  const group = categoryGroup(category);
  const item = categoryItemLabel(subtype);
  if (group && item) return `${group.label} · ${item}`;
  return group?.label ?? item ?? "";
}

// ------------------------------------------------------------------
//  درس‌ها
// ------------------------------------------------------------------
export const SUBJECT_LIST: Subject[] = Object.values(SUBJECTS);

export const SUBJECT_BY_ID: Record<string, Subject> = Object.fromEntries(
  SUBJECT_LIST.map((s) => [s.id, s])
);

export function subjectName(id: string, fallback = ""): string {
  return SUBJECT_BY_ID[id]?.name ?? fallback;
}

// ------------------------------------------------------------------
//  گروه‌بندی تکالیف بر اساس درس
// ------------------------------------------------------------------
export function groupAssignmentsBySubject(
  assignments: Assignment[]
): Record<string, Assignment[]> {
  const map: Record<string, Assignment[]> = {};
  for (const a of assignments) {
    if (!a.subject_id) continue;
    (map[a.subject_id] ??= []).push(a);
  }
  for (const key of Object.keys(map)) {
    map[key].sort((x, y) => {
      const dx = x.due_date ? parseDue(x.due_date).getTime() : Infinity;
      const dy = y.due_date ? parseDue(y.due_date).getTime() : Infinity;
      return dx - dy;
    });
  }
  return map;
}

// ------------------------------------------------------------------
//  برنامه‌ی روز و منطق هوشمند «روز بعد»
// ------------------------------------------------------------------
export interface DayEntry {
  subject: Subject;
  period: string;
}

/** دروس یک روز به‌ترتیب زنگ‌ها */
export function dayEntries(day: Day): DayEntry[] {
  const out: DayEntry[] = [];
  let period = 0;
  for (const cell of day.cells) {
    const label = cell.span === PERIOD_COUNT ? "تمام زنگ‌ها" : PERIOD_LABELS[period] ?? "";
    if (cell.kind === "class") {
      out.push({ subject: cell.subject, period: label });
    } else if (cell.kind === "multi") {
      for (const subject of cell.subjects) out.push({ subject, period: label });
    }
    period += cell.span;
  }
  return out;
}

/** ساعت پایان مدرسه (۱۴:۰۰) به دقیقه */
export const SCHOOL_END_MINUTES = 14 * 60;
export const SCHOOL_START_MINUTES = 8 * 60;

export interface SchoolPeriod {
  index: number;
  label: string;
  start: number;
  end: number;
}

export const SCHOOL_PERIODS: SchoolPeriod[] = PERIOD_TIMES.map((period, index) => ({
  index,
  label: PERIOD_LABELS[index],
  start: period.start,
  end: period.end,
}));

export type SchoolPhase = "before" | "active" | "after" | "holiday";

export interface PeriodState {
  phase: SchoolPhase;
  /** اندیس زنگ فعلی (یا زنگ بعدی در حالت before) */
  periodIndex: number;
  /** میلی‌ثانیه باقی‌مانده تا پایان زنگ/شروع مدرسه */
  remainingMs: number;
  /** درصد سپری‌شده از زنگ فعلی (۰ تا ۱) */
  progress: number;
  /** آیا امروز روز مدرسه است؟ */
  isSchoolDay: boolean;
}

export function schoolDayIndex(base: Date = new Date()): number {
  const index = todayIndex(base);
  return index < TIMETABLE.length ? index : -1;
}

export function nextSchoolDayIndex(index: number): number {
  if (index < 0) return 0;
  return index < TIMETABLE.length - 1 ? index + 1 : 0;
}

export function formatClock(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/** محاسبه‌ی دقیق زنگ جاری و زمان باقی‌مانده تا پایان آن. */
export function periodState(now: number = Date.now()): PeriodState {
  const date = new Date(now);
  const dayIndex = schoolDayIndex(date);
  const dayStart = new Date(
    date.getFullYear(),
    date.getMonth(),
    date.getDate()
  ).getTime();
  const elapsed = now - dayStart;
  const minuteNow = elapsed / 60_000;

  if (dayIndex < 0) {
    return {
      phase: "holiday",
      periodIndex: 0,
      remainingMs: 0,
      progress: 0,
      isSchoolDay: false,
    };
  }

  if (minuteNow < SCHOOL_START_MINUTES) {
    return {
      phase: "before",
      periodIndex: 0,
      remainingMs: dayStart + SCHOOL_START_MINUTES * 60_000 - now,
      progress: 0,
      isSchoolDay: true,
    };
  }

  for (const period of SCHOOL_PERIODS) {
    if (minuteNow >= period.start && minuteNow < period.end) {
      const startMs = dayStart + period.start * 60_000;
      const endMs = dayStart + period.end * 60_000;
      return {
        phase: "active",
        periodIndex: period.index,
        remainingMs: endMs - now,
        progress: Math.min(1, Math.max(0, (now - startMs) / (endMs - startMs))),
        isSchoolDay: true,
      };
    }
  }

  return {
    phase: "after",
    periodIndex: SCHOOL_PERIODS.length - 1,
    remainingMs: 0,
    progress: 1,
    isSchoolDay: true,
  };
}

/** دروس حاضر در یک زنگ مشخص (پشتیبانی از سلول‌های چنددرسی). */
export function subjectsAtPeriod(day: Day, periodIndex: number): Subject[] {
  let cursor = 0;
  for (const cell of day.cells) {
    if (periodIndex >= cursor && periodIndex < cursor + cell.span) {
      if (cell.kind === "class") return [cell.subject];
      if (cell.kind === "multi") {
        const offset = periodIndex - cursor;
        const subject = cell.subjects[offset] ?? cell.subjects[0];
        return subject ? [subject] : [];
      }
      return [];
    }
    cursor += cell.span;
  }
  return [];
}

export function subjectAtPeriod(day: Day | undefined, periodIndex: number): Subject | null {
  if (!day) return null;
  return subjectsAtPeriod(day, periodIndex)[0] ?? null;
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
 * منطق «برنامه‌ی پیش‌رو»:
 * - بعد از ۱۴:۰۰ یا در تعطیلات آخر هفته، نزدیک‌ترین روز مدرسه‌ی بعدی (شنبه).
 * - قبل از آن برنامه‌ی امروز.
 */
export function scheduleTarget(now: number = Date.now()): ScheduleTarget {
  const base = new Date(now);
  const minutes = base.getHours() * 60 + base.getMinutes();
  const today = todayIndex(base);
  const isWeekend = today >= TIMETABLE.length;
  const isAfterSchool = minutes >= SCHOOL_END_MINUTES || isWeekend;
  const dayIndex = isAfterSchool ? nextSchoolDayIndex(today) : today;
  return {
    dayIndex,
    isTomorrow: isAfterSchool || dayIndex !== today,
    isAfterSchool,
    isWeekend,
    isLiteralTomorrow: dayIndex === (today + 1) % 7,
  };
}

/** روزِ برنامه با اندیس؛ خارج از روزهای مدرسه undefined است */
export function dayAtIndex(index: number): Day | undefined {
  return index >= 0 && index < TIMETABLE.length ? TIMETABLE[index] : undefined;
}

/** روز برنامه‌ی امروز (یا undefined در تعطیلی) */
export function todayDay(now: number = Date.now()): Day | undefined {
  return dayAtIndex(schoolDayIndex(new Date(now)));
}

// ------------------------------------------------------------------
//  روزهای هفته (شنبه تا چهارشنبه) و برنامه‌ی هر درس
// ------------------------------------------------------------------
const DAY_INDEX: Record<string, number> = { sat: 0, sun: 1, mon: 2, tue: 3, wed: 4 };

export const WEEK_DAYS = TIMETABLE.map((day, index) => ({
  index,
  id: day.id,
  name: day.name,
  short: day.short,
}));

/** نگاشت «شناسه درس» به «اندیس روز» در برنامه‌ی هفتگی */
export const SUBJECT_DAY: Record<string, number> = (() => {
  const map: Record<string, number> = {};
  for (const day of TIMETABLE) {
    for (const cell of day.cells) {
      const subjects =
        cell.kind === "class"
          ? [cell.subject]
          : cell.kind === "multi"
            ? cell.subjects
            : [];
      for (const subject of subjects) {
        if (!(subject.id in map)) map[subject.id] = DAY_INDEX[day.id];
      }
    }
  }
  return map;
})();

export const HOUR_MS = 3_600_000;
export const DAY_MS = 86_400_000;

/**
 * مهلت‌ها ممکن است بدون اطلاعات منطقه‌زمانی ذخیره شوند (مثل «2026-10-19T13:26:16»).
 * چنین مقادیری در UTC ذخیره شده‌اند، پس برای مقایسه‌ی درست باید به‌صورت UTC خوانده شوند.
 */
export function parseDue(value: string): Date {
  const normalized = value.includes("T") ? value : value.replace(" ", "T");
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(normalized);
  return new Date(hasTimezone ? normalized : `${normalized}Z`);
}

/** شنبه‌ی هفته‌ی جاری (ساعت ۰۰:۰۰) */
export function startOfWeek(base: Date = new Date()): Date {
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate());
  const offset = (d.getDay() + 1) % 7; // یکشنبه=۱ ... شنبه=۰
  d.setDate(d.getDate() - offset);
  return d;
}

/** اندیس روز جاری در بازه‌ی شنبه..چهارشنبه (۵ و ۶ = پنجشنبه/جمعه) */
export function todayIndex(base: Date = new Date()): number {
  return (base.getDay() + 1) % 7;
}

/** تاریخِ یک روز مشخص در هفته‌ی هدف (weekOffset هفته بعدتر) */
export function dateAt(weekOffset: number, dayIndex: number, base: Date = new Date()): Date {
  const d = new Date(startOfWeek(base));
  d.setDate(d.getDate() + weekOffset * 7 + dayIndex);
  d.setHours(23, 59, 0, 0);
  return d;
}

/** هفته‌ی یک تاریخ نسبت به هفته‌ی جاری */
export function weekOffsetOf(date: Date, base: Date = new Date()): number {
  return Math.round((startOfWeek(date).getTime() - startOfWeek(base).getTime()) / (7 * DAY_MS));
}

/** مهلت پیشنهادی برای یک درس: نزدیک‌ترین روز هفته که آن درس در برنامه هست */
export function defaultDueForSubject(subjectId: string, base: Date = new Date()): Date | null {
  const dayIndex = SUBJECT_DAY[subjectId];
  if (dayIndex === undefined) return null;
  const upcoming = dayIndex > todayIndex(base) ? 0 : 1;
  return dateAt(upcoming, dayIndex, base);
}

// ------------------------------------------------------------------
//  رنگ مهلت (deadline)
// ------------------------------------------------------------------
export type DeadlineTone = "red" | "yellow" | "none";

export function deadlineTone(due?: string | null, now: number = Date.now()): DeadlineTone {
  if (!due) return "none";
  const diff = parseDue(due).getTime() - now;
  return diff < DAY_MS ? "red" : "yellow";
}

export const TONE_BORDER: Record<DeadlineTone, string> = {
  red: "border-red-500",
  yellow: "border-yellow-500",
  none: "border-white/15",
};

export const TONE_GLOW: Record<DeadlineTone, string> = {
  red: "shadow-[0_0_18px_-10px_rgba(239,68,68,0.9)]",
  yellow: "shadow-[0_0_18px_-10px_rgba(234,179,8,0.85)]",
  none: "shadow-[0_0_16px_-10px_rgba(255,255,255,0.35)]",
};

export const TONE_TEXT: Record<DeadlineTone, string> = {
  red: "text-red-400",
  yellow: "text-yellow-400",
  none: "text-fg-300",
};

export const TONE_DOT: Record<DeadlineTone, string> = {
  red: "bg-red-500",
  yellow: "bg-yellow-500",
  none: "bg-white/40",
};

// ------------------------------------------------------------------
//  قالب‌بندی تاریخ
// ------------------------------------------------------------------
export function formatDue(due?: string | null): string {
  if (!due) return "بدون مهلت";
  return parseDue(due).toLocaleDateString("fa-IR", {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

/**
 * اختلاف «روز تقویمی» بین دو تاریخ، مستقل از ساعت.
 * ساعت هر دو تاریخ به نیمه‌شب منتقل می‌شود تا مهلتِ فردا همیشه ۱ روز باشد.
 */
export function calendarDayDiff(due: Date, base: Date = new Date()): number {
  const dueDay = Date.UTC(due.getFullYear(), due.getMonth(), due.getDate());
  const baseDay = Date.UTC(base.getFullYear(), base.getMonth(), base.getDate());
  return Math.round((dueDay - baseDay) / DAY_MS);
}

export function relativeDue(due?: string | null, now: number = Date.now()): string {
  if (!due) return "";

  const dueDate = parseDue(due);
  const diff = dueDate.getTime() - now;
  const dayDiff = calendarDayDiff(dueDate, new Date(now));

  // گذشته
  if (dayDiff < 0) {
    const days = -dayDiff;
    return days === 1 ? "1 روز گذشته" : `${days} روز گذشته`;
  }

  // امروز
  if (dayDiff === 0) {
    if (diff <= 0) return "مهلت گذشته";
    if (diff < HOUR_MS) {
      const minutes = Math.max(1, Math.round(diff / 60_000));
      return `امروز · ${minutes} دقیقه مانده`;
    }
    const hours = Math.max(1, Math.round(diff / HOUR_MS));
    return `امروز · ${hours} ساعت مانده`;
  }

  // آینده: فردا = ۱ روز، نه بر اساس ۲۴ ساعت دقیق
  return dayDiff === 1 ? "1 روز مانده" : `${dayDiff} روز مانده`;
}

/** تاریخ کامل شمسیِ امروز، مثلاً «پنجشنبه ۲۶ مهر» */
export function jalaliToday(now: number = Date.now()): string {
  return new Date(now).toLocaleDateString("fa-IR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  });
}

/** ساعت جاری به‌صورت شمسی، مثلاً «۱۴:۳۰» */
export function jalaliTime(now: number = Date.now()): string {
  return new Date(now).toLocaleTimeString("fa-IR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortDayLabel(due?: string | null): string {
  if (!due) return "—";
  return parseDue(due).toLocaleDateString("fa-IR", { day: "numeric", month: "short" });
}
