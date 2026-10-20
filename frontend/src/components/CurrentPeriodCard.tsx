import { memo } from "react";
import { motion } from "framer-motion";
import { AlarmClock, BookOpen, CalendarClock, Coffee, MoonStar, User } from "lucide-react";
import type { Assignment } from "../api/client";
import {
  SCHOOL_PERIODS,
  dayAtIndex,
  formatClock,
  periodState,
  scheduleTarget,
  subjectAtPeriod,
  todayDay,
} from "../lib/assignments";

function countdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function PeriodCard({
  now,
  bySubject,
}: {
  now: number;
  bySubject: Record<string, Assignment[]>;
}) {
  const state = periodState(now);
  const day = todayDay(now);
  const subject = subjectAtPeriod(day, state.periodIndex);
  const period = SCHOOL_PERIODS[state.periodIndex];
  const target = scheduleTarget(now);
  const targetDay = dayAtIndex(target.dayIndex);
  const targetSubject = subjectAtPeriod(targetDay, 0);
  const work =
    subject && state.phase === "active" ? (bySubject[subject.id] ?? []) : [];

  const label =
    state.phase === "active"
      ? "زنگ جاری"
      : state.phase === "before"
        ? "شروع مدرسه"
        : state.phase === "holiday"
          ? "امروز تعطیل است"
          : "کلاس‌ها تمام شد";

  const countdownLabel =
    state.phase === "before"
      ? "مانده تا شروع"
      : state.phase === "active"
        ? "مانده به پایان زنگ"
        : "";

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="panel noise relative overflow-hidden rounded-3xl p-5 sm:p-6"
    >
      <div
        className="pointer-events-none absolute -top-24 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full blur-[70px]"
        style={{ background: "var(--period-glow, rgba(255,255,255,0.09))" }}
      />

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.05]">
            {state.phase === "active" ? (
              <AlarmClock size={21} className="text-white" />
            ) : state.phase === "holiday" ? (
              <MoonStar size={21} className="text-white" />
            ) : state.phase === "before" ? (
              <Coffee size={21} className="text-white" />
            ) : (
              <CalendarClock size={21} className="text-white" />
            )}
          </span>
          <div className="min-w-0">
            <p className="mono-label">{label}</p>
            <h2 className="truncate text-xl font-black text-white sm:text-2xl">
              {state.phase === "active"
                ? subject?.name ?? "زنگ آزاد"
                : state.phase === "before"
                  ? subject?.name ?? targetSubject?.name ?? "بدون کلاس"
                  : targetDay
                    ? `برنامه ${target.isTomorrow ? "بعدی" : "امروز"} · ${targetDay.name}`
                    : "برنامه‌ای ثبت نشده"}
            </h2>
            {state.phase === "active" && subject && (
              <p className="mt-1 flex items-center gap-1.5 truncate text-[12px] text-fg-300">
                <User size={12} className="shrink-0 text-fg-500" />
                {subject.teacher}
                <span className="opacity-50">·</span>
                <span className="mono text-fg-500">
                  {formatClock(period.start)}–{formatClock(period.end)}
                </span>
              </p>
            )}
          </div>
        </div>

        {(state.phase === "active" || state.phase === "before") && (
          <div className="text-left">
            <p className="mono-label text-right">{countdownLabel}</p>
            <p
              className="mono text-2xl font-black tabular-nums text-white sm:text-3xl"
              dir="ltr"
            >
              {countdown(state.remainingMs)}
            </p>
          </div>
        )}
      </div>

      {state.phase === "active" && (
        <>
          <div className="relative mt-5 h-2 overflow-hidden rounded-full bg-white/[0.08]">
            <motion.div
              className="absolute inset-0 origin-right rounded-full bg-white"
              initial={false}
              animate={{ scaleX: state.progress }}
              transition={{ duration: 0.5, ease: "linear" }}
              style={{ willChange: "transform" }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-fg-500">
            <span>{period.label}</span>
            <span className="mono tabular-nums" dir="ltr">
              {Math.max(0, Math.round(state.progress * 100))}%
            </span>
          </div>
          {work.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {work.slice(0, 3).map((assignment) => (
                <span
                  key={assignment.id}
                  className="badge max-w-full !normal-case whitespace-normal text-right"
                >
                  <BookOpen size={11} className="shrink-0" />
                  <span className="min-w-0 break-words">{assignment.title}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}

      {(state.phase === "after" || state.phase === "holiday") && targetDay && (
        <div className="relative mt-4 flex items-center gap-2 rounded-2xl border border-white/8 bg-white/[0.025] px-3 py-2.5 text-[12px] text-fg-300">
          <CalendarClock size={14} className="shrink-0 text-fg-500" />
          <span>
            {targetDay.name}
            {targetSubject ? ` · زنگ اول با ${targetSubject.name}` : " · کلاسی ثبت نشده"}
          </span>
        </div>
      )}
    </motion.section>
  );
}

export default memo(PeriodCard);
