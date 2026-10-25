import { memo } from "react";
import { motion } from "framer-motion";
import {
  AlarmClock,
  BookOpen,
  CalendarClock,
  Coffee,
  MoonStar,
  User,
} from "lucide-react";
import type { Assignment } from "../api/client";
import { useBellSchedule } from "../hooks/useBellSchedule";
import { useNow } from "../hooks/useNow";
import {
  dayAtIndex,
  formatClock,
  subjectAtPeriod,
  todayDay,
} from "../lib/assignments";
import { getCurrentBellState, scheduleTarget } from "../lib/bell";

function countdown(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

function PeriodCard({ bySubject }: { bySubject: Record<string, Assignment[]> }) {
  // The countdown needs a one-second clock. Owning it here keeps the ticker
  // from re-rendering the whole timetable page (grid + tomorrow schedule)
  // every second.
  const now = useNow(1000);
  const { bells } = useBellSchedule();
  const state = getCurrentBellState(now, bells);

  const day = todayDay(now);
  const target = scheduleTarget(now, bells);
  const targetDay = dayAtIndex(target.dayIndex);
  const targetSubject = subjectAtPeriod(targetDay, 0);

  const subject =
    state.state === "class" ? subjectAtPeriod(day, state.bellIndex) : null;
  const nextSubject =
    state.state === "break"
      ? subjectAtPeriod(day, state.nextBellIndex)
      : state.state === "before"
        ? subjectAtPeriod(day, 0)
        : null;

  const work =
    state.state === "class" && subject ? (bySubject[subject.id] ?? []) : [];

  const label =
    state.state === "class"
      ? "زنگ جاری"
      : state.state === "break"
        ? "زنگ تفریح"
        : state.state === "before"
          ? "شروع مدرسه"
          : state.state === "holiday"
            ? "امروز تعطیل است"
            : "کلاس‌ها تمام شد";

  const title =
    state.state === "class"
      ? (subject?.name ?? "زنگ آزاد")
      : state.state === "break"
        ? "زنگ تفریح"
        : state.state === "before"
          ? (nextSubject?.name ?? state.firstBell.label ?? "بدون کلاس")
          : targetDay
            ? `برنامه ${target.isTomorrow ? "بعدی" : "امروز"} · ${targetDay.name}`
            : "برنامه‌ای ثبت نشده";

  const countdownLabel =
    state.state === "class"
      ? "مانده به پایان زنگ"
      : state.state === "break"
        ? "مانده تا زنگ بعد"
        : state.state === "before"
          ? "مانده تا شروع"
          : "";

  const remainingMs =
    state.state === "class" ||
    state.state === "break" ||
    state.state === "before"
      ? state.remainingMs
      : null;

  const progress =
    state.state === "class" || state.state === "break"
      ? state.progress
      : null;

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
      className="panel noise relative overflow-hidden rounded-3xl p-5 sm:p-6"
    >
      <div
        className="pointer-events-none absolute -top-24 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full blur-[70px]"
        style={{
          background:
            state.state === "break"
              ? "rgba(52, 211, 153, 0.16)"
              : "var(--period-glow, rgba(255,255,255,0.09))",
        }}
      />

      <div className="relative flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <span
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border ${
              state.state === "break"
                ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-300"
                : "border-white/15 bg-white/[0.05] text-white"
            }`}
          >
            {state.state === "class" ? (
              <AlarmClock size={21} />
            ) : state.state === "break" ? (
              <Coffee size={21} />
            ) : state.state === "holiday" ? (
              <MoonStar size={21} />
            ) : state.state === "before" ? (
              <Coffee size={21} />
            ) : (
              <CalendarClock size={21} />
            )}
          </span>
          <div className="min-w-0">
            <p
              className={`mono-label ${
                state.state === "break" ? "!text-emerald-300/80" : ""
              }`}
            >
              {label}
            </p>
            <h2 className="truncate text-xl font-black text-white sm:text-2xl">
              {title}
            </h2>
            {state.state === "class" && subject && (
              <p className="mt-1 flex items-center gap-1.5 truncate text-[12px] text-fg-300">
                <User size={12} className="shrink-0 text-fg-500" />
                {subject.teacher}
                <span className="opacity-50">·</span>
                <span className="mono text-fg-500" dir="ltr">
                  {formatClock(state.bell.start)}–{formatClock(state.bell.end)}
                </span>
              </p>
            )}
            {state.state === "break" && (
              <p className="mt-1 flex flex-wrap items-center gap-1.5 text-[12px] text-emerald-200/85">
                <BookOpen size={12} className="shrink-0" />
                زنگ بعد: {nextSubject?.name ?? state.nextBell.label}
                <span className="opacity-50">·</span>
                <span className="mono text-emerald-200/60" dir="ltr">
                  {formatClock(state.nextBell.start)}
                </span>
              </p>
            )}
            {state.state === "before" && (
              <p className="mt-1 flex items-center gap-1.5 text-[12px] text-fg-300">
                <BookOpen size={12} className="shrink-0 text-fg-500" />
                شروع {formatClock(state.firstBell.start)}
                <span className="opacity-50">·</span>
                <span className="truncate">{state.firstBell.label}</span>
              </p>
            )}
          </div>
        </div>

        {remainingMs !== null && (
          <div className="text-left">
            <p
              className={`mono-label text-right ${
                state.state === "break" ? "!text-emerald-300/75" : ""
              }`}
            >
              {countdownLabel}
            </p>
            <p
              className={`mono text-2xl font-black tabular-nums sm:text-3xl ${
                state.state === "break" ? "text-emerald-200" : "text-white"
              }`}
              dir="ltr"
            >
              {countdown(remainingMs)}
            </p>
          </div>
        )}
      </div>

      {progress !== null && (
        <>
          <div className="relative mt-5 h-2 overflow-hidden rounded-full bg-white/[0.08]">
            <motion.div
              className={`absolute inset-0 origin-right rounded-full ${
                state.state === "break" ? "bg-emerald-400" : "bg-white"
              }`}
              initial={false}
              animate={{ scaleX: progress }}
              transition={{ duration: 0.5, ease: "linear" }}
              style={{ willChange: "transform" }}
            />
          </div>
          <div className="mt-2 flex items-center justify-between text-[11px] text-fg-500">
            <span>
              {state.state === "break"
                ? `${state.previousBell.label} → ${state.nextBell.label}`
                : state.state === "class"
                  ? state.bell.label
                  : ""}
            </span>
            <span className="mono tabular-nums" dir="ltr">
              {Math.max(0, Math.round(progress * 100))}%
            </span>
          </div>
        </>
      )}

      {state.state === "class" && work.length > 0 && (
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

      {(state.state === "after" || state.state === "holiday") && targetDay && (
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
