import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { CalendarDays, Sparkles } from "lucide-react";
import {
  SUBJECT_DAY,
  WEEK_DAYS,
  dateAt,
  deadlineTone,
  formatDue,
  parseDue,
  relativeDue,
  TONE_TEXT,
  weekOffsetOf,
} from "../lib/assignments";

interface DueDatePickerProps {
  value: string | null;
  onChange: (iso: string) => void;
  subjectId?: string;
}

const WEEK_LABELS = ["این هفته", "هفته بعد", "۲ هفته بعد", "۳ هفته بعد"];
const PANEL_ESTIMATE = 300;

interface PanelPos {
  left: number;
  width: number;
  top?: number;
  bottom?: number;
  up: boolean;
}

function sameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export default function DueDatePicker({ value, onChange, subjectId }: DueDatePickerProps) {
  const [open, setOpen] = useState(false);
  const [viewWeek, setViewWeek] = useState(1);
  const [pos, setPos] = useState<PanelPos | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const selected = value ? parseDue(value) : null;
  const subjectDay = subjectId ? SUBJECT_DAY[subjectId] : undefined;

  const reposition = useCallback(() => {
    const el = rootRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const spaceBelow = window.innerHeight - r.bottom;
    const spaceAbove = r.top;
    const up = spaceBelow < PANEL_ESTIMATE && spaceAbove > spaceBelow;
    const width = Math.min(r.width, window.innerWidth - 16);
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    setPos({
      left,
      width,
      up,
      ...(up ? { bottom: window.innerHeight - r.top + 8 } : { top: r.bottom + 8 }),
    });
  }, []);

  function openPanel() {
    if (!open) {
      if (value) setViewWeek(Math.max(0, Math.min(3, weekOffsetOf(parseDue(value)))));
      reposition();
    }
    setOpen((o) => !o);
  }

  useEffect(() => {
    if (!open) return;
    function onPointerDown(e: MouseEvent) {
      const t = e.target as Node;
      if (rootRef.current?.contains(t) || panelRef.current?.contains(t)) return;
      setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    function onMove() {
      reposition();
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("resize", onMove);
    window.addEventListener("scroll", onMove, true);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onMove);
      window.removeEventListener("scroll", onMove, true);
    };
  }, [open, reposition]);

  const tone = deadlineTone(value);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={openPanel}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label="انتخاب مهلت"
        className={`flex w-full items-center gap-3 rounded-2xl border px-3.5 py-3 text-right transition-[background-color,border-color,box-shadow] duration-300 ${
          open
            ? "border-white/35 bg-black/70 shadow-[0_0_30px_-12px_rgba(255,255,255,0.6)]"
            : "border-white/12 bg-white/[0.03] hover:border-white/25 hover:bg-white/[0.05]"
        }`}
      >
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border transition-colors ${
            open ? "border-white/30 bg-white/10 text-white" : "border-white/12 bg-white/[0.04] text-fg-500"
          }`}
        >
          <CalendarDays size={17} />
        </span>
        <span className="min-w-0 flex-1">
          {selected ? (
            <>
              <span className="block truncate text-[13px] font-semibold text-white">
                {formatDue(value)}
              </span>
              <span className={`mt-0.5 block truncate text-[10px] ${TONE_TEXT[tone]}`}>
                {relativeDue(value)}
              </span>
            </>
          ) : (
            <span className="block truncate text-[13px] text-fg-500">انتخاب مهلت…</span>
          )}
        </span>
      </button>

      {createPortal(
        <AnimatePresence>
          {open && pos && (
            <motion.div
              ref={panelRef}
              role="dialog"
              aria-label="انتخاب مهلت"
              initial={{ opacity: 0, y: pos.up ? 10 : -10, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: pos.up ? 10 : -10, scale: 0.98 }}
              transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
              style={{
                position: "fixed",
                left: pos.left,
                width: pos.width,
                top: pos.top,
                bottom: pos.bottom,
                transformOrigin: pos.up ? "bottom" : "top",
              }}
              className="z-[120] max-h-[70dvh] overflow-y-auto overscroll-contain rounded-3xl border border-white/15 bg-[#0a0a0c]/98 p-3.5 shadow-2xl shadow-black/80 ring-1 ring-black/50 sm:p-4"
            >
              {/* سربرگ */}
              <div className="mb-4 flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05] text-white">
                  <CalendarDays size={15} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-bold text-white">مهلت را انتخاب کنید</p>
                  <p className="text-[10px] text-fg-500">روزِ مورد نظر را از هفته‌ی زیر برگزینید</p>
                </div>
              </div>

              {/* روزهای هفته */}
              <div className="grid grid-cols-5 gap-1.5 sm:gap-2">
                {WEEK_DAYS.map((day) => {
                  const date = dateAt(viewWeek, day.index);
                  const isSelected = selected ? sameDay(date, selected) : false;
                  const isSubjectDay = subjectDay === day.index;
                  const dateLabel = date.toLocaleDateString("fa-IR", {
                    day: "numeric",
                    month: "long",
                  });
                  return (
                    <button
                      key={day.id}
                      type="button"
                      onClick={() => {
                        onChange(date.toISOString());
                        setOpen(false);
                      }}
                      className={`relative flex min-h-[68px] flex-col items-center justify-center gap-1 rounded-2xl border px-1 py-2.5 transition-[background-color,border-color,color,box-shadow] duration-200 sm:min-h-[74px] sm:px-1.5 sm:py-3 ${
                        isSelected
                          ? "border-white bg-white text-black shadow-[0_0_26px_-8px_rgba(255,255,255,0.9)]"
                          : "border-white/12 bg-white/[0.03] text-fg-300 hover:border-white/30 hover:bg-white/[0.07] hover:text-white"
                      }`}
                    >
                      <span className="text-[13px] font-extrabold leading-none">{day.name}</span>
                      <span
                        className={`text-[10px] tabular-nums ${
                          isSelected ? "text-black/60" : "text-fg-500"
                        }`}
                      >
                        {dateLabel}
                      </span>
                      {isSubjectDay && (
                        <span
                          className={`absolute top-2 h-1.5 w-1.5 rounded-full ${
                            isSelected ? "bg-black/50" : "bg-white/70"
                          }`}
                        />
                      )}
                    </button>
                  );
                })}
              </div>

              {/* کنترل هفته */}
              <div className="mt-4 grid grid-cols-2 gap-1 rounded-2xl border border-white/10 bg-white/[0.02] p-1 sm:flex sm:rounded-full">
                {WEEK_LABELS.map((label, i) => (
                  <button
                    key={label}
                    type="button"
                    onClick={() => setViewWeek(i)}
                    className={`relative flex flex-1 items-center justify-center gap-1 rounded-full px-2 py-2.5 text-[11px] font-semibold transition-colors sm:py-2 ${
                      viewWeek === i ? "text-black" : "text-fg-500 hover:text-white"
                    }`}
                  >
                    {viewWeek === i && (
                      <motion.span
                        layoutId="due-week-pill"
                        transition={{ type: "spring", stiffness: 420, damping: 34 }}
                        className="absolute inset-0 rounded-full bg-white"
                      />
                    )}
                    <span className="relative z-10 flex items-center gap-1 whitespace-nowrap">
                      {i === 1 && <Sparkles size={11} />}
                      {label}
                    </span>
                  </button>
                ))}
              </div>

              <p className="mt-3 flex items-center gap-1.5 text-[10px] text-fg-500">
                <span className="h-1.5 w-1.5 rounded-full bg-white/70" />
                روزِ همین درس در برنامه‌ی هفتگی با نقطه مشخص شده است
              </p>
            </motion.div>
          )}
        </AnimatePresence>,
        document.body
      )}
    </div>
  );
}
