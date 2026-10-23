import { memo, useMemo } from "react";
import { motion } from "framer-motion";
import { BookOpen, CalendarClock, GraduationCap, MoonStar } from "lucide-react";
import type { Assignment } from "../api/client";
import type { Subject } from "../data";
import Corners from "./Corners";
import {
  TONE_BORDER,
  TONE_DOT,
  TONE_TEXT,
  categoryItemLabel,
  dayAtIndex,
  dayEntries,
  deadlineTone,
  relativeDue,
  scheduleTarget,
  todayIndex,
  type DeadlineTone,
} from "../lib/assignments";

const BADGE_TONE: Record<DeadlineTone, string> = {
  red: "border-red-500/40 bg-red-500/10 text-red-400",
  yellow: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
  none: "border-white/12 bg-white/[0.04] text-fg-300",
};

interface Row {
  subject: Subject;
  period: string;
  events: Assignment[];
  exams: Assignment[];
  tone: DeadlineTone;
}

const ScheduleRow = memo(function ScheduleRow({ row, now }: { row: Row; now: number }) {
  const hasEvents = row.events.length > 0;
  const isExam = row.exams.length > 0;
  const badgeTone: DeadlineTone = isExam ? "red" : row.tone;
  const nearest = row.events[0];

  return (
    <li
      className={`flex items-center gap-3 rounded-2xl border-2 bg-white/[0.02] p-3.5 transition-colors ${
        hasEvents ? TONE_BORDER[row.tone] : "border-white/10"
      }`}
    >
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/12 bg-white/[0.05]">
        {isExam ? (
          <GraduationCap size={18} className="text-white" />
        ) : (
          <BookOpen size={18} className="text-white" />
        )}
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-white">{row.subject.name}</p>
        <p className="mt-0.5 flex items-center gap-1.5 truncate text-[11px] text-fg-500">
          <span className="truncate">{row.subject.teacher}</span>
          <span className="shrink-0 opacity-60">·</span>
          <span className="shrink-0">{row.period}</span>
        </p>
        {nearest && (
          <p className="mt-0.5 truncate text-[10px] text-fg-500">
            {categoryItemLabel(nearest.subtype)}
            <span className="opacity-60"> · </span>
            <span className={TONE_TEXT[row.tone]}>{relativeDue(nearest.due_date, now)}</span>
          </p>
        )}
      </div>

      {hasEvents && (
        <span
          className={`flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${BADGE_TONE[badgeTone]}`}
          title={isExam ? "امتحان پیش‌رو" : "تکلیف پیش‌رو"}
        >
          <span
            className={`h-1.5 w-1.5 animate-pulse rounded-full ${TONE_DOT[badgeTone]}`}
          />
          {isExam ? "امتحان" : "تکلیف"}
          <span className="mono tabular-nums">{row.events.length}</span>
        </span>
      )}
    </li>
  );
});

export default function TomorrowSchedule({
  bySubject,
  now,
  mode = "next",
}: {
  bySubject: Record<string, Assignment[]>;
  now: number;
  /**
   * "next" (default) = the Timetable page's "upcoming school day": today before
   * 14:00, otherwise the next school day. "tomorrow" = the literal calendar
   * day after today, used by the dashboard's tomorrow preview.
   */
  mode?: "next" | "tomorrow";
}) {
  const target = useMemo(() => {
    if (mode === "tomorrow") {
      const dayIndex = (todayIndex(new Date(now)) + 1) % 7;
      return {
        dayIndex,
        isTomorrow: true,
        isAfterSchool: false,
        isWeekend: dayAtIndex(dayIndex) === undefined,
        isLiteralTomorrow: true,
      };
    }
    return scheduleTarget(now);
  }, [now, mode]);
  const day = useMemo(() => dayAtIndex(target.dayIndex), [target.dayIndex]);

  const rows = useMemo<Row[]>(() => {
    if (!day) return [];
    return dayEntries(day).map(({ subject, period }) => {
      const events = (bySubject[subject.id] ?? []).filter((a) => !a.completed);
      const exams = events.filter((a) => a.category === "exam");
      const tone: DeadlineTone = events.length
        ? deadlineTone(events[0].due_date, now)
        : "none";
      return { subject, period, events, exams, tone };
    });
  }, [day, bySubject, now]);

  const totalEvents = useMemo(
    () => rows.reduce((sum, row) => sum + row.events.length, 0),
    [rows]
  );

  const isLiteralTomorrow = target.isTomorrow && target.isLiteralTomorrow;

  const heading = isLiteralTomorrow
    ? target.isWeekend
      ? "فردا تعطیل است"
      : "فردا چه کلاسی داریم؟"
    : target.isWeekend
      ? "برنامه بعد از تعطیلات"
      : target.isTomorrow
        ? "برنامه روز بعد"
        : "برنامه امروز";

  const badgeLabel = isLiteralTomorrow
    ? "فردا"
    : target.isWeekend
      ? "تعطیلات آخر هفته"
      : target.isTomorrow
        ? "روز بعد"
        : "امروز";

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: 0.06 }}
      className="panel noise relative mt-6 overflow-hidden rounded-2xl p-5 sm:p-6"
    >
      <Corners />

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/15 bg-white/5">
            <CalendarClock size={18} className="text-white" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-base font-bold text-white">{heading}</h2>
            <p className="mono truncate text-[10px] tracking-widest text-fg-500">
              // {target.isTomorrow ? "NEXT DAY" : "TODAY"}
              {day ? ` · ${day.name.toUpperCase()}` : ""}
            </p>
          </div>
        </div>

        <span className="badge shrink-0">
          <span className="dot animate-pulse" />
          {badgeLabel}
          {totalEvents > 0 ? ` · ${totalEvents} رویداد` : ""}
        </span>
      </div>

      {!day || rows.length === 0 ? (
        <div className="flex flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-white/12 p-10 text-center">
          <MoonStar size={26} className="text-fg-500" />
          <p className="text-sm text-fg-500">
            {target.isWeekend
              ? "تعطیلات آخر هفته — کلاسی نداریم"
              : target.isTomorrow
                ? "روز بعد کلاسی نداریم"
                : "امروز کلاسی نداریم"}
          </p>
        </div>
      ) : (
        <ul className="space-y-2.5">
          {rows.map((row) => (
            <ScheduleRow key={row.subject.id} row={row} now={now} />
          ))}
        </ul>
      )}
    </motion.section>
  );
}
