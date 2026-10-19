import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import {
  BookOpen,
  User,
  ClipboardList,
  GraduationCap,
  Layers,
  Clock,
  CalendarClock,
  CalendarDays,
  MousePointer2,
  ChevronDown,
  ChevronLeft,
  X,
} from "lucide-react";
import {
  TIMETABLE,
  PERIOD_COUNT,
  PERIOD_LABELS,
  type Cell,
  type Day,
  type Subject,
} from "../data";
import type { Assignment } from "../api/client";
import Corners from "./Corners";
import {
  TONE_BORDER,
  TONE_DOT,
  TONE_GLOW,
  TONE_TEXT,
  categoryGroup,
  categoryItemLabel,
  deadlineTone,
  formatDue,
  parseDue,
  relativeDue,
  type DeadlineTone,
} from "../lib/assignments";

interface HoverState {
  key: string;
  subject: Subject;
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  dir: number;
}

function GroupIcon({ category, size = 15 }: { category?: string; size?: number }) {
  return category === "exam" ? (
    <GraduationCap size={size} className="text-white" />
  ) : (
    <ClipboardList size={size} className="text-white" />
  );
}

function groupAssignments(assignments: Assignment[]): Record<string, Assignment[]> {
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
//  مکعب درس (دسکتاپ)
// ------------------------------------------------------------------
function Cube({
  subject,
  active,
  tone,
  onEnter,
  onLeave,
  className = "",
}: {
  subject: Subject;
  active: boolean;
  tone?: "red" | "yellow" | "none";
  onEnter: (el: HTMLElement, subject: Subject) => void;
  onLeave: () => void;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const hasWork = !!tone && tone !== "none";

  return (
    <div
      ref={ref}
      onMouseEnter={() => ref.current && onEnter(ref.current, subject)}
      onMouseLeave={onLeave}
      className={`group relative flex h-full w-full cursor-pointer flex-col justify-center gap-1 overflow-hidden rounded-2xl border p-3 text-right transition-all duration-300 ${className} ${
        active
          ? "border-white/45 bg-white/[0.1] shadow-[0_0_28px_-12px_rgba(255,255,255,0.65)]"
          : "border-white/10 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.06]"
      }`}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-white/40 to-transparent opacity-0 transition-opacity group-hover:opacity-100" />

      {hasWork && (
        <span className={`absolute left-3 top-3 h-2 w-2 rounded-full ${TONE_DOT[tone!]}`} />
      )}

      <div className="flex items-center gap-2">
        <BookOpen size={15} className="shrink-0 text-white" />
        <span className="truncate text-sm font-bold text-white">{subject.name}</span>
      </div>

      <span className="mono truncate text-[10px] tracking-wider text-fg-500">
        {subject.nameEn}
      </span>

      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-fg-300">
        <User size={12} className="shrink-0 text-fg-500" />
        <span className="truncate">{subject.teacher}</span>
      </div>
    </div>
  );
}

function FreeCell() {
  return (
    <div className="flex h-full w-full items-center justify-center rounded-2xl border border-dashed border-white/10 text-fg-500">
      <span className="mono text-[10px] tracking-[0.25em]">— FREE —</span>
    </div>
  );
}

// ------------------------------------------------------------------
//  جدول هفتگی — دسکتاپ
// ------------------------------------------------------------------
function DesktopTimetable({ bySubject }: { bySubject: Record<string, Assignment[]> }) {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const leaveTimer = useRef<number | null>(null);
  const [hover, setHover] = useState<HoverState | null>(null);

  const cancelLeave = useCallback(() => {
    if (leaveTimer.current) {
      window.clearTimeout(leaveTimer.current);
      leaveTimer.current = null;
    }
  }, []);

  const scheduleLeave = useCallback(() => {
    cancelLeave();
    leaveTimer.current = window.setTimeout(() => setHover(null), 240);
  }, [cancelLeave]);

  useEffect(() => () => cancelLeave(), [cancelLeave]);

  const handleEnter = useCallback(
    (el: HTMLElement, subject: Subject) => {
      cancelLeave();
      const container = containerRef.current;
      if (!container) return;

      const c = container.getBoundingClientRect();
      const r = el.getBoundingClientRect();

      const cy = r.top - c.top + r.height / 2;
      const spaceLeft = r.left - c.left;
      const spaceRight = c.width - (r.right - c.left);
      const dir = spaceRight >= spaceLeft ? 1 : -1;

      const startX = dir === 1 ? r.right - c.left : r.left - c.left;
      const startY = cy;

      const reach = Math.min(150, Math.max(60, (dir === 1 ? spaceRight : spaceLeft) - 24));
      const endX = Math.min(Math.max(startX + dir * reach, 120), c.width - 120);
      const endY = Math.min(Math.max(cy + (cy > c.height / 2 ? -78 : 78), 64), c.height - 64);

      setHover({ key: subject.id, subject, x0: startX, y0: startY, x1: endX, y1: endY, dir });
    },
    [cancelLeave]
  );

  const path = hover
    ? `M ${hover.x0} ${hover.y0} C ${hover.x0 + hover.dir * 72} ${hover.y0}, ${
        hover.x1 - hover.dir * 72
      } ${hover.y1}, ${hover.x1} ${hover.y1}`
    : "";

  const list = hover ? bySubject[hover.subject.id] ?? [] : [];
  const tone = list.length ? deadlineTone(list[0].due_date) : "none";
  const primary = list[0];

  function go(id: number) {
    navigate(`/assignments/${id}`);
  }

  return (
    <div className="hidden overflow-x-auto pb-2 md:block">
      <div ref={containerRef} className="relative min-w-[900px]">
        <div
          className="grid gap-2.5"
          style={{
            gridTemplateColumns: `92px repeat(${TIMETABLE.length}, minmax(0, 1fr))`,
            gridTemplateRows: `auto repeat(${PERIOD_COUNT}, minmax(108px, 1fr))`,
          }}
        >
          <div
            style={{ gridColumn: 1, gridRow: 1 } as CSSProperties}
            className="flex items-center justify-center"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/5">
              <Layers size={16} className="text-fg-500" />
            </span>
          </div>

          {TIMETABLE.map((day, d) => (
            <div
              key={day.id}
              style={{ gridColumn: d + 2, gridRow: 1 } as CSSProperties}
              className="panel flex items-center justify-center gap-2 py-3"
            >
              <span className="text-sm font-bold text-white">{day.name}</span>
              <span className="mono text-[10px] tracking-widest text-fg-500">{day.short}</span>
            </div>
          ))}

          {PERIOD_LABELS.map((label, i) => (
            <div
              key={label}
              style={{ gridColumn: 1, gridRow: i + 2 } as CSSProperties}
              className="flex flex-col items-center justify-center gap-1"
            >
              <Clock size={14} className="text-fg-500" />
              <span className="text-xs font-medium text-fg-300">{label}</span>
            </div>
          ))}

          {TIMETABLE.map((day, d) => {
            let row = 2;
            return day.cells.map((cell: Cell, ci) => {
              const style = {
                gridColumn: d + 2,
                gridRow: `${row} / span ${cell.span}`,
              } as CSSProperties;
              row += cell.span;

              return (
                <div key={`${day.id}-${ci}`} style={style} className="min-h-0">
                  {cell.kind === "free" ? (
                    <FreeCell />
                  ) : cell.kind === "class" ? (
                    <Cube
                      subject={cell.subject}
                      active={hover?.key === cell.subject.id}
                      tone={
                        (bySubject[cell.subject.id]?.[0] &&
                          deadlineTone(bySubject[cell.subject.id][0].due_date)) ||
                        "none"
                      }
                      onEnter={handleEnter}
                      onLeave={scheduleLeave}
                    />
                  ) : (
                    <div className="flex h-full flex-col gap-2">
                      {cell.subjects.map((subject) => (
                        <Cube
                          key={subject.id}
                          subject={subject}
                          active={hover?.key === subject.id}
                          tone={
                            (bySubject[subject.id]?.[0] &&
                              deadlineTone(bySubject[subject.id][0].due_date)) ||
                            "none"
                          }
                          onEnter={handleEnter}
                          onLeave={scheduleLeave}
                          className="flex-1"
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            });
          })}
        </div>

        {/* لایه‌ی شاخه و تولتیپ */}
        <div className="pointer-events-none absolute inset-0 z-40">
          <svg className="h-full w-full overflow-visible">
            <defs>
              <linearGradient id="branchGrad" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="rgba(255,255,255,0.1)" />
                <stop offset="45%" stopColor="rgba(255,255,255,0.9)" />
                <stop offset="100%" stopColor="#ffffff" />
              </linearGradient>
              <filter id="branchGlow" x="-50%" y="-50%" width="200%" height="200%">
                <feGaussianBlur stdDeviation="2.4" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            <AnimatePresence>
              {hover && (
                <motion.g key={hover.key} initial="hidden" animate="visible" exit="hidden">
                  <motion.path
                    d={path}
                    fill="none"
                    stroke="url(#branchGrad)"
                    strokeWidth={2}
                    strokeLinecap="round"
                    filter="url(#branchGlow)"
                    variants={{
                      hidden: { pathLength: 0, opacity: 0 },
                      visible: { pathLength: 1, opacity: 1 },
                    }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  />
                  {primary && (
                    <motion.path
                      d={path}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={22}
                      className="pointer-events-auto cursor-pointer"
                      onClick={() => go(primary.id)}
                      variants={{ hidden: { opacity: 0 }, visible: { opacity: 1 } }}
                    />
                  )}
                  <motion.circle
                    cx={hover.x0}
                    cy={hover.y0}
                    r={4}
                    fill="#ffffff"
                    variants={{ hidden: { scale: 0, opacity: 0 }, visible: { scale: 1, opacity: 1 } }}
                    transition={{ delay: 0.05, duration: 0.2 }}
                  />
                  <motion.circle
                    cx={hover.x1}
                    cy={hover.y1}
                    r={5}
                    fill="#ffffff"
                    variants={{ hidden: { scale: 0, opacity: 0 }, visible: { scale: 1, opacity: 1 } }}
                    transition={{ delay: 0.35, duration: 0.2 }}
                  />
                </motion.g>
              )}
            </AnimatePresence>
          </svg>

          <AnimatePresence>
            {hover && (
              <motion.div
                key={hover.key}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.22, delay: 0.1 }}
                onMouseEnter={cancelLeave}
                onMouseLeave={scheduleLeave}
                onClick={() => primary && go(primary.id)}
                className={`pointer-events-auto absolute -translate-x-1/2 -translate-y-1/2 ${
                  primary ? "cursor-pointer" : ""
                }`}
                style={{ left: hover.x1, top: hover.y1 }}
              >
                <motion.div
                  initial={{ scale: 0.85, y: 10 }}
                  animate={{ scale: 1, y: 0 }}
                  transition={{ duration: 0.32, delay: 0.16, ease: [0.16, 1, 0.3, 1] }}
                  className={`w-64 rounded-2xl border-2 bg-black/95 p-4 text-white ${
                    TONE_BORDER[tone]
                  } ${TONE_GLOW[tone]}`}
                >
                  <Corners className="border-white/30" />

                  <div className="flex items-center gap-2.5">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/25 bg-white/10">
                      <BookOpen size={16} className="text-white" />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-white">{hover.subject.name}</p>
                      <p className="mono truncate text-[10px] tracking-wider text-fg-300">
                        {hover.subject.nameEn}
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center gap-1.5 text-[11px] text-fg-300">
                    <User size={12} className="shrink-0 text-fg-500" />
                    <span className="truncate">{hover.subject.teacher}</span>
                  </div>

                  <div className="my-3 h-px bg-white/15" />

                  <div className="mb-2 flex items-center gap-1.5">
                    <CalendarClock size={12} className="text-fg-500" />
                    <span className="mono-label">
                      {list.length ? `// ${list.length} مورد` : "// رویدادها"}
                    </span>
                  </div>

                  {list.length > 0 ? (
                    <ul className="space-y-2">
                      {list.map((a) => {
                        const aTone = deadlineTone(a.due_date);
                        const group = categoryGroup(a.category);
                        return (
                          <li key={a.id}>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                go(a.id);
                              }}
                              className={`w-full rounded-xl border bg-white/[0.05] p-2.5 text-right transition hover:bg-white/[0.1] ${TONE_BORDER[aTone]}`}
                            >
                              <div className="flex items-center gap-2">
                                <GroupIcon category={a.category} size={13} />
                                <span className="min-w-0 flex-1 truncate text-xs font-semibold text-white">
                                  {a.title}
                                </span>
                                <span className={`h-2 w-2 shrink-0 rounded-full ${TONE_DOT[aTone]}`} />
                              </div>
                              <div className="mt-1 flex items-center justify-between gap-2">
                                <span className="truncate text-[10px] text-fg-500">
                                  {group?.label}
                                  {a.subtype ? ` · ${categoryItemLabel(a.subtype)}` : ""}
                                </span>
                                <span className={`shrink-0 text-[10px] ${TONE_TEXT[aTone]}`}>
                                  {relativeDue(a.due_date)}
                                </span>
                              </div>
                            </button>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="text-xs text-fg-300">تکلیفی برای این درس ثبت نشده</p>
                  )}
                </motion.div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-fg-500">
        <MousePointer2 size={12} />
        روی هر درس هاور کن؛ برای دیدن جزئیات کلیک کن
      </p>
    </div>
  );
}

// ------------------------------------------------------------------
//  موبایل — تایم‌لاین عمودی + باتم‌شیت
// ------------------------------------------------------------------
interface MobileEntry {
  subject: Subject | null;
  label: string;
  dual?: boolean;
}

const EVENT_GLOW: Record<DeadlineTone, string> = {
  red: "shadow-[0_0_10px_rgba(239,68,68,0.9)]",
  yellow: "shadow-[0_0_10px_rgba(234,179,8,0.85)]",
  none: "",
};

function flattenDay(day: Day): MobileEntry[] {
  const out: MobileEntry[] = [];
  let p = 0;
  for (const cell of day.cells) {
    const label = cell.span === PERIOD_COUNT ? "تمام زنگ‌ها" : PERIOD_LABELS[p];
    if (cell.kind === "class") out.push({ subject: cell.subject, label });
    else if (cell.kind === "multi")
      cell.subjects.forEach((s) => out.push({ subject: s, label, dual: true }));
    else out.push({ subject: null, label });
    p += cell.span;
  }
  return out;
}

function MobileTimetable({ bySubject }: { bySubject: Record<string, Assignment[]> }) {
  const navigate = useNavigate();
  const [openDay, setOpenDay] = useState<string | null>(TIMETABLE[0]?.id ?? null);
  const [selected, setSelected] = useState<Subject | null>(null);

  useEffect(() => {
    if (!selected) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [selected]);

  const list = selected ? bySubject[selected.id] ?? [] : [];

  const days = useMemo(
    () =>
      TIMETABLE.map((day) => {
        const entries = flattenDay(day);
        let events = 0;
        let tone: DeadlineTone = "none";

        for (const entry of entries) {
          if (!entry.subject) continue;
          const subjectAssignments = bySubject[entry.subject.id] ?? [];
          events += subjectAssignments.length;
          if (subjectAssignments.length) {
            const t = deadlineTone(subjectAssignments[0].due_date);
            if (t === "red") tone = "red";
            else if (t === "yellow" && tone === "none") tone = "yellow";
          }
        }

        return {
          day,
          entries,
          count: entries.filter((e) => e.subject).length,
          events,
          tone,
        };
      }),
    [bySubject]
  );

  return (
    <div className="md:hidden">
      <div className="relative">
        <span className="pointer-events-none absolute bottom-6 right-[21px] top-8 w-px bg-gradient-to-b from-white/30 via-white/10 to-transparent" />

        <div className="space-y-3">
          {days.map(({ day, entries, count, events, tone }) => {
            const isOpen = openDay === day.id;

            return (
              <div key={day.id} className="relative pr-12">
                <span
                  className={`absolute right-[14px] top-6 z-10 grid h-4 w-4 place-items-center rounded-full border transition-colors ${
                    isOpen ? "border-white bg-white" : "border-white/40 bg-bg-100"
                  }`}
                >
                  {isOpen && <span className="h-1.5 w-1.5 rounded-full bg-black" />}
                </span>

                <button
                  onClick={() => setOpenDay(isOpen ? null : day.id)}
                  className={`panel relative flex w-full items-center justify-between gap-3 p-4 text-right transition-colors ${
                    isOpen ? "border-white/25 bg-white/[0.05]" : "active:bg-white/[0.04]"
                  }`}
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl border border-white/15 bg-white/[0.06] text-lg font-black text-white">
                      {day.short}
                    </span>
                    <div className="min-w-0">
                      <p className="text-base font-bold text-white">{day.name}</p>
                      <p className="flex items-center gap-1.5 text-[11px] text-fg-500">
                        <span className="mono tabular-nums tracking-widest">
                          {String(count).padStart(2, "0")}
                        </span>
                        <span>درس</span>
                      </p>
                    </div>
                  </div>

                  {events > 0 && (
                    <span
                      className="flex shrink-0 items-center gap-1.5 rounded-full border border-white/15 bg-white/[0.05] px-2 py-1"
                      title={`${events} رویداد`}
                    >
                      <span
                        className={`h-2 w-2 animate-pulse rounded-full ${TONE_DOT[tone]} ${EVENT_GLOW[tone]}`}
                      />
                      <span className="mono text-[10px] tabular-nums text-fg-200">{events}</span>
                    </span>
                  )}

                  <motion.span
                    animate={{ rotate: isOpen ? 180 : 0 }}
                    transition={{ type: "spring", stiffness: 400, damping: 28 }}
                    className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-white/12 bg-white/[0.04] text-fg-300"
                  >
                    <ChevronDown size={16} />
                  </motion.span>
                </button>

                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div
                      key="content"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.16, ease: "easeOut" }}
                      className="overflow-hidden"
                    >
                      <div className="space-y-2 pt-2">
                        {entries.map((entry, ei) =>
                          entry.subject ? (
                            <button
                              key={`${day.id}-${ei}`}
                              onClick={() => setSelected(entry.subject)}
                              className="flex w-full items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.02] p-3.5 text-right transition-colors active:scale-[0.98] active:bg-white/[0.06]"
                            >
                              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-white/12 bg-white/[0.05]">
                                <BookOpen size={16} className="text-white" />
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-bold text-white">
                                  {entry.subject.name}
                                </p>
                                <p className="flex items-center gap-1.5 truncate text-[11px] text-fg-500">
                                  <User size={11} className="shrink-0" />
                                  {entry.subject.teacher}
                                </p>
                              </div>
                              {bySubject[entry.subject.id]?.length ? (
                                <span
                                  className={`h-2 w-2 shrink-0 rounded-full ${
                                    TONE_DOT[
                                      deadlineTone(bySubject[entry.subject.id][0].due_date)
                                    ]
                                  }`}
                                />
                              ) : null}
                              <span className="badge shrink-0">{entry.label}</span>
                              <ChevronLeft size={16} className="shrink-0 text-fg-500" />
                            </button>
                          ) : (
                            <div
                              key={`${day.id}-${ei}`}
                              className="flex items-center gap-3 rounded-2xl border border-dashed border-white/10 p-3.5"
                            >
                              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-dashed border-white/10 text-fg-500">
                                <Clock size={16} />
                              </span>
                              <span className="text-sm text-fg-500">زنگ آزاد</span>
                              <span className="badge ml-auto shrink-0">{entry.label}</span>
                            </div>
                          )
                        )}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            );
          })}
        </div>
      </div>

      <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-fg-500">
        <CalendarDays size={12} />
        روی هر روز بزن تا درسهاش باز بشه، روی هر درس بزن تا جزئیات رو ببینی
      </p>

      {createPortal(
        <AnimatePresence>
          {selected && (
            <div className="fixed inset-0 z-[100]">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
                onClick={() => setSelected(null)}
                className="absolute inset-0 bg-black/75"
              />

              <motion.div
                drag="y"
                dragConstraints={{ top: 0, bottom: 0 }}
                dragElastic={{ top: 0, bottom: 0.5 }}
                onDragEnd={(_, info) => {
                  if (info.offset.y > 130 || info.velocity.y > 600) setSelected(null);
                }}
                initial={{ y: "100%" }}
                animate={{ y: 0 }}
                exit={{ y: "100%" }}
                transition={{ type: "spring", stiffness: 320, damping: 34 }}
                className="absolute inset-x-0 bottom-0 max-h-[88vh] overflow-y-auto rounded-t-[28px] border-t border-white/15 bg-bg-100 px-5 pb-10 pt-3 shadow-2xl shadow-black"
              >
                <div className="mx-auto mb-4 h-1.5 w-12 rounded-full bg-white/25" />

                <div className="mb-5 flex items-start gap-3.5">
                  <span className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl border border-white/15 bg-white/[0.06] shadow-inner">
                    <BookOpen size={24} className="text-white" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h3 className="truncate text-xl font-black text-white">{selected.name}</h3>
                    <p className="mono truncate text-[11px] tracking-wider text-fg-500">
                      {selected.nameEn}
                    </p>
                    <p className="mt-1.5 flex items-center gap-1.5 text-[13px] text-fg-300">
                      <User size={13} className="shrink-0 text-fg-500" />
                      {selected.teacher}
                    </p>
                  </div>
                  <button
                    onClick={() => setSelected(null)}
                    aria-label="بستن"
                    className="icon-btn shrink-0"
                  >
                    <X size={18} />
                  </button>
                </div>

                <div className="mb-3 flex items-center gap-2">
                  <CalendarClock size={14} className="text-fg-500" />
                  <span className="mono-label">// EVENTS</span>
                  <span className="ml-auto mono text-[10px] tracking-widest text-fg-500">
                    {String(list.length).padStart(2, "0")}
                  </span>
                </div>

                {list.length > 0 ? (
                  <motion.ul
                    variants={{
                      hidden: {},
                      visible: { transition: { staggerChildren: 0.07, delayChildren: 0.12 } },
                    }}
                    initial="hidden"
                    animate="visible"
                    className="space-y-3"
                  >
                    {list.map((a) => {
                      const aTone = deadlineTone(a.due_date);
                      const group = categoryGroup(a.category);
                      return (
                        <motion.li
                          key={a.id}
                          variants={{ hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } }}
                          transition={{ type: "spring", stiffness: 380, damping: 30 }}
                        >
                          <button
                            onClick={() => {
                              setSelected(null);
                              navigate(`/assignments/${a.id}`);
                            }}
                            className={`w-full rounded-2xl border-2 bg-white/[0.04] p-4 text-right shadow-lg shadow-black/40 ${TONE_BORDER[aTone]}`}
                          >
                            <div className="flex items-center gap-3">
                              <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/15 bg-white/[0.06]">
                                <GroupIcon category={a.category} size={18} />
                              </span>
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-base font-bold text-white">{a.title}</p>
                                <p className="truncate text-[11px] text-fg-500">
                                  {group?.label}
                                  {a.subtype ? ` · ${categoryItemLabel(a.subtype)}` : ""}
                                </p>
                              </div>
                            </div>
                            <div className="mt-3 flex items-center justify-between gap-2 border-t border-white/8 pt-3">
                              <span className="flex items-center gap-1.5 text-[12px] text-fg-300">
                                <CalendarDays size={12} className="text-fg-500" />
                                {formatDue(a.due_date)}
                              </span>
                              <span className={`text-[12px] font-medium ${TONE_TEXT[aTone]}`}>
                                {relativeDue(a.due_date)}
                              </span>
                            </div>
                          </button>
                        </motion.li>
                      );
                    })}
                  </motion.ul>
                ) : (
                  <div className="rounded-2xl border border-dashed border-white/12 p-6 text-center text-sm text-fg-500">
                    تکلیفی برای این درس ثبت نشده
                  </div>
                )}

                <p className="mt-4 text-center text-[10px] text-fg-500">
                  وضعیت مهلت: قرمز = کمتر از یک روز · زرد = بیش از یک روز
                </p>
              </motion.div>
            </div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </div>
  );
}

// ------------------------------------------------------------------
//  انتخاب دسکتاپ / موبایل
// ------------------------------------------------------------------
export default function Timetable({ assignments = [] }: { assignments?: Assignment[] }) {
  const bySubject = useMemo(() => groupAssignments(assignments), [assignments]);
  return (
    <>
      <DesktopTimetable bySubject={bySubject} />
      <MobileTimetable bySubject={bySubject} />
    </>
  );
}
