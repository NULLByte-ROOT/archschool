import {
  SUBJECTS,
  TIMETABLE,
  PERIOD_COUNT,
  PERIOD_LABELS,
  type Day,
  type Subject,
} from "../data";
import type { Assignment } from "../api/client";

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
      { id: "poem", label: "حفظ شعر" },
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

export interface ScheduleTarget {
  /** اندیس روز در TIMETABLE (۰ = شنبه) */
  dayIndex: number;
  /** آیا هدف، روز بعد است؟ */
  isTomorrow: boolean;
  /** آیا ساعت از پایان مدرسه گذشته است؟ */
  isAfterSchool: boolean;
}

/**
 * منطق هوشمند «برنامه‌ی پیش‌رو»:
 * - بعد از ساعت ۱۴:۰۰ برنامه‌ی روز تقویمی بعد نمایش داده می‌شود.
 * - قبل از آن برنامه‌ی امروز نمایش داده می‌شود.
 */
export function scheduleTarget(now: number = Date.now()): ScheduleTarget {
  const base = new Date(now);
  const minutes = base.getHours() * 60 + base.getMinutes();
  const isAfterSchool = minutes >= SCHOOL_END_MINUTES;
  const today = todayIndex(base);
  const dayIndex = isAfterSchool ? (today + 1) % 7 : today;
  return { dayIndex, isTomorrow: isAfterSchool, isAfterSchool };
}

/** روزِ برنامه با اندیس؛ خارج از روزهای مدرسه undefined است */
export function dayAtIndex(index: number): Day | undefined {
  return index >= 0 && index < TIMETABLE.length ? TIMETABLE[index] : undefined;
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

export function relativeDue(due?: string | null, now: number = Date.now()): string {
  if (!due) return "";
  const diff = parseDue(due).getTime() - now;
  if (diff <= 0) return "مهلت گذشته";
  if (diff < HOUR_MS) {
    const minutes = Math.max(1, Math.round(diff / 60_000));
    return `${minutes} دقیقه مانده`;
  }
  if (diff < DAY_MS) {
    const hours = Math.max(1, Math.round(diff / HOUR_MS));
    return `${hours} ساعت مانده`;
  }
  return `${Math.ceil(diff / DAY_MS)} روز مانده`;
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
