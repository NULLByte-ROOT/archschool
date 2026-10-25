import { AlarmClock, CalendarClock, Coffee, MoonStar } from "lucide-react";
import { useBellSchedule } from "../hooks/useBellSchedule";
import { useNow } from "../hooks/useNow";
import { formatClock, subjectAtPeriod, todayDay } from "../lib/assignments";
import { getCurrentBellState } from "../lib/bell";

const minutes = new Intl.NumberFormat("en-US");

/**
 * نوار باریک وضعیت مدرسه برای داشبورد و صفحهٔ تکالیف.
 * همهٔ زمان‌ها از زنگ‌های ذخیره‌شدهٔ ادمین می‌آیند؛ هیچ ساعت ثابتی اینجا نیست.
 */
export default function SchoolStatusStrip({
  className = "",
}: {
  className?: string;
}) {
  const now = useNow(15_000);
  const { bells } = useBellSchedule();
  const state = getCurrentBellState(now, bells);
  const day = todayDay(now);
  const left = (ms: number) => minutes.format(Math.max(1, Math.ceil(ms / 60_000)));

  let icon = <AlarmClock size={15} />;
  let title = "زنگ جاری";
  let detail = "";
  let tone =
    "border-white/12 bg-white/[0.03] text-fg-300";

  if (state.state === "class") {
    const subject = subjectAtPeriod(day, state.bellIndex);
    title = subject?.name ?? state.bell.label;
    detail = `${left(state.remainingMs)} دقیقه مانده · تا ${formatClock(state.bell.end)}`;
    icon = <AlarmClock size={15} />;
  } else if (state.state === "break") {
    const next = subjectAtPeriod(day, state.nextBellIndex);
    title = "زنگ تفریح";
    detail = `${left(state.remainingMs)} دقیقه مانده تا ${next?.name ?? state.nextBell.label} · ${formatClock(state.nextBell.start)}`;
    icon = <Coffee size={15} />;
    tone = "border-emerald-400/30 bg-emerald-400/[0.07] text-emerald-200";
  } else if (state.state === "before") {
    title = "مدرسه هنوز شروع نشده";
    detail = `${left(state.remainingMs)} دقیقه مانده تا ${state.firstBell.label} · ${formatClock(state.firstBell.start)}`;
    icon = <CalendarClock size={15} />;
  } else if (state.state === "holiday") {
    title = "امروز تعطیل است";
    detail = "برنامهٔ روز بعد را ببین";
    icon = <MoonStar size={15} />;
  } else {
    title = "کلاس‌ها تمام شد";
    detail = `آخرین زنگ ${formatClock(state.lastBell.end)}`;
    icon = <CalendarClock size={15} />;
  }

  return (
    <div
      className={`flex flex-wrap items-center justify-between gap-2 rounded-2xl border px-3.5 py-2.5 text-[12px] ${tone} ${className}`}
    >
      <span className="flex min-w-0 items-center gap-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-white/12 bg-white/[0.05]">
          {icon}
        </span>
        <span className="truncate font-bold">{title}</span>
      </span>
      <span className="truncate text-[11px] opacity-75">{detail}</span>
    </div>
  );
}
