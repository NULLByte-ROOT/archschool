import { lazy, memo, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { animate, motion } from "framer-motion";
import {
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  CircleDashed,
  ClipboardList,
  Clock,
  Flame,
  Loader2,
  Sparkles,
  Target,
  Trophy,
  Users,
} from "lucide-react";
import {
  fetchAssignments,
  fetchChatOverview,
  fetchRecentComments,
  fetchTeamOverview,
} from "../api/client";
import type { Assignment, TeamOverview } from "../api/client";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import PulseBox from "../components/PulseBox";
import TomorrowSchedule from "../components/TomorrowSchedule";
import { useAuth } from "../contexts/AuthContext";
import { useNow } from "../hooks/useNow";
import {
  DAY_MS,
  groupAssignmentsBySubject,
  jalaliToday,
  jalaliTime,
  parseDue,
  relativeDue,
} from "../lib/assignments";
import { seedFeed, toPulseItem } from "../lib/unread";

// Recharts is the heaviest dependency: the trend chart is split out of the main
// bundle and only requested when the dashboard mounts.
const ClassTrendChart = lazy(() => import("../components/ClassTrendChart"));

/** Numbers that count up from their previous value (Linear-style stat cards). */
const AnimatedNumber = memo(function AnimatedNumber({
  value,
  className,
}: {
  value: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const previous = useRef(0);

  useEffect(() => {
    const controls = animate(previous.current, value, {
      duration: 0.7,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => {
        if (ref.current) ref.current.textContent = String(Math.round(latest));
      },
    });
    previous.current = value;
    return () => controls.stop();
  }, [value]);

  return (
    <span ref={ref} className={className}>
      {Math.round(previous.current)}
    </span>
  );
});

const pctFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

export default function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const now = useNow(30_000);

  const [items, setItems] = useState<Assignment[]>([]);
  const [overview, setOverview] = useState<TeamOverview | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [loading, setLoading] = useState(true);

  // Workspace data (assignments + the pulse ticker seed).
  useEffect(() => {
    let active = true;
    Promise.all([fetchAssignments(), fetchChatOverview(), fetchRecentComments(6)])
      .then(([assignments, chatOverview, comments]) => {
        if (!active) return;
        setItems(assignments);
        const seeded = [
          chatOverview.global_message
            ? toPulseItem(chatOverview.global_message)
            : null,
          ...chatOverview.directs.map((direct) => toPulseItem(direct.message)),
          ...comments.map((comment) => toPulseItem(comment)),
        ].filter((item): item is NonNullable<typeof item> => item !== null);
        seedFeed(seeded);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Team stats are fetched separately so a stats hiccup can never hide the
  // assignments/pulse data.
  useEffect(() => {
    let active = true;
    fetchTeamOverview()
      .then((data) => {
        if (active) setOverview(data);
      })
      .catch(() => undefined)
      .finally(() => {
        if (active) setStatsLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const personal = useMemo(() => {
    const done = items.filter((item) => item.is_completed_by_me).length;
    const pending = items.filter((item) => !item.is_completed_by_me);
    const urgent = pending.filter(
      (item) =>
        item.due_date && parseDue(item.due_date).getTime() - now < DAY_MS * 2
    ).length;
    const next = [...pending]
      .filter((item) => item.due_date)
      .sort(
        (a, b) =>
          parseDue(a.due_date as string).getTime() -
          parseDue(b.due_date as string).getTime()
      )
      .slice(0, 2);
    return { total: items.length, done, pending: pending.length, urgent, next };
  }, [items, now]);

  const bySubject = useMemo(() => groupAssignmentsBySubject(items), [items]);

  const me = overview?.me;
  const streak = me?.current_streak ?? 0;
  const atRisk = Boolean(overview && !overview.me.completed_today);
  const teamRecord = overview?.team_record_streak ?? 0;
  const bestStreak = me?.best_streak ?? 0;

  return (
    <div className="mx-auto max-w-6xl">
      {/* هدر خوش‌آمد */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="glass mb-4 flex flex-wrap items-center justify-between gap-3 rounded-3xl px-4 py-3.5"
      >
        <div className="flex items-center gap-3">
          <span className="relative flex h-11 w-11 items-center justify-center rounded-2xl border border-white/12 bg-gradient-to-br from-white/[0.14] to-white/[0.02]">
            <CalendarDays size={18} className="text-white" />
            <span className="absolute -bottom-1 -left-1 h-3 w-3 rounded-full border-2 border-black bg-success motion-safe:animate-pulse" />
          </span>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-black text-white">
              سلام {user?.username} 👋
            </p>
            <p className="truncate text-[11px] text-fg-500">
              امروز: {jalaliToday(now)}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
            <Clock size={13} className="text-fg-500" />
            <span className="mono text-sm tabular-nums text-fg-100" dir="ltr">
              {jalaliTime(now)}
            </span>
          </span>
          <span className="badge">
            <span className="dot motion-safe:animate-pulse" />
            DASHBOARD
          </span>
        </div>
      </motion.div>

      {/* --------------------------------------------------------------
          HERO — استریک من (مهم‌ترین ویجت داشبورد)
      -------------------------------------------------------------- */}
      <motion.div
        role="button"
        tabIndex={0}
        onClick={() => navigate("/leaderboard")}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            navigate("/leaderboard");
          }
        }}
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={`group relative mb-4 cursor-pointer overflow-hidden rounded-[28px] border p-5 text-right sm:p-7 ${
          atRisk
            ? "border-red-500/45 bg-[#140607]"
            : "border-orange-500/30 bg-[#0d0805]"
        }`}
      >
        <div className="pointer-events-none absolute inset-0 grid-bg opacity-[0.18]" />
        <div
          className={`pointer-events-none absolute -top-24 right-1/4 h-64 w-64 rounded-full ${
            atRisk ? "bg-red-500/20" : "bg-orange-500/20"
          }`}
          style={{ filter: "blur(70px)" }}
        />
        <div
          className={`pointer-events-none absolute -bottom-24 left-1/4 h-56 w-56 rounded-full ${
            atRisk ? "bg-red-600/15" : "bg-amber-500/15"
          }`}
          style={{ filter: "blur(70px)" }}
        />
        {atRisk && (
          <span
            aria-hidden
            className="pointer-events-none absolute inset-0 rounded-[28px] border border-red-500/60 motion-safe:animate-pulse"
            style={{
              boxShadow: "inset 0 0 70px -24px rgba(248,113,113,0.9)",
            }}
          />
        )}
        <Corners className={atRisk ? "border-red-400/40" : "border-orange-400/30"} />

        <div className="relative flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-4">
            <span
              className={`relative flex h-20 w-20 shrink-0 items-center justify-center rounded-3xl border ${
                atRisk
                  ? "border-red-400/35 bg-gradient-to-br from-red-500/25 to-red-500/5"
                  : "border-orange-400/35 bg-gradient-to-br from-orange-500/25 to-amber-500/5"
              }`}
            >
              <motion.span
                animate={{ scale: [1, 1.12, 1], rotate: [0, -5, 0] }}
                transition={{
                  duration: 2.4,
                  repeat: Infinity,
                  ease: "easeInOut",
                }}
                className="will-change-transform"
              >
                <Flame
                  size={40}
                  className={atRisk ? "text-red-400" : "text-orange-400"}
                />
              </motion.span>
            </span>

            <div className="min-w-0">
              <p className="mono-label">// MY STREAK</p>
              <div className="flex items-end gap-2">
                <span className="bg-gradient-to-b from-white via-amber-100 to-orange-400 bg-clip-text text-6xl leading-none font-black tabular-nums text-transparent sm:text-7xl">
                  {streak}
                </span>
                <span className="pb-2 text-sm font-bold text-orange-200/80">
                  روز متوالی
                </span>
              </div>
              <p className="mt-1.5 text-[12px] text-fg-500">
                {atRisk
                  ? "امروز هنوز هیچ تکلیفی را انجام ندادی."
                  : streak > 0
                    ? "استریکت را حفظ کردی — همین‌طور ادامه بده 🔥"
                    : "امروز اولین روز استریک جدیدت می‌تواند باشد."}
              </p>
            </div>
          </div>

          <div className="grid w-full grid-cols-2 gap-2.5 sm:w-auto sm:min-w-[280px]">
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-[10px] text-fg-500">
                <Trophy size={11} className="text-warning" />
                رکورد تیم
              </p>
              <p className="mt-0.5 text-[15px] font-black text-white">
                <span className="tabular-nums">{teamRecord}</span> روز
              </p>
            </div>
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] px-3 py-2.5">
              <p className="flex items-center gap-1.5 text-[10px] text-fg-500">
                <Sparkles size={11} className="text-orange-300" />
                بهترین تو
              </p>
              <p className="mt-0.5 text-[15px] font-black text-white">
                <span className="tabular-nums">{bestStreak}</span> روز
              </p>
            </div>
            <div className="col-span-2 flex items-center justify-between rounded-2xl border border-white/10 bg-white/[0.03] px-3 py-2 text-[11px] font-bold text-fg-300 transition-colors group-hover:border-white/25 group-hover:text-white">
              <span className="flex items-center gap-1.5">
                <Trophy size={12} className="text-warning" />
                جدول قهرمانان کلاس
              </span>
              <ArrowUpRight size={14} />
            </div>
          </div>
        </div>

        {atRisk && (
          <div className="relative mt-4 flex flex-col gap-2.5 rounded-2xl border border-red-500/35 bg-red-500/10 p-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="flex items-center gap-2 text-[12.5px] leading-6 font-bold text-red-200">
              <motion.span
                aria-hidden
                animate={{ opacity: [1, 0.35, 1] }}
                transition={{ duration: 1.5, repeat: Infinity }}
              >
                ⚠️
              </motion.span>
              استریک شما در خطر است! امروز هیچ تکلیفی انجام ندادی.
            </p>
            <button
              type="button"
              onClick={(event) => {
                event.stopPropagation();
                navigate("/assignments");
              }}
              onKeyDown={(event) => event.stopPropagation()}
              className="flex min-h-9 shrink-0 items-center justify-center gap-1.5 rounded-xl border border-red-400/40 bg-red-500/20 px-3.5 py-1.5 text-[11px] font-bold text-red-100 transition-colors hover:bg-red-500/35 hover:text-white"
            >
              <CheckCircle2 size={13} />
              همین حالا انجام بده
            </button>
          </div>
        )}
      </motion.div>

      {/* --------------------------------------------------------------
          ردیف دوم: وضعیت کلاس + مینی‌لیدربورد + تمرکز من
      -------------------------------------------------------------- */}
      <div className="mb-4 grid gap-4 lg:grid-cols-12">
        {/* آمار کلی کلاس */}
        <motion.div
          role="button"
          tabIndex={0}
          onClick={() => navigate("/leaderboard")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              navigate("/leaderboard");
            }
          }}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.05 }}
          className="panel panel-hover relative flex cursor-pointer flex-col overflow-hidden rounded-3xl p-5 text-right lg:col-span-4"
        >
          <Corners />
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
                <Users size={16} className="text-white" />
              </span>
              <div>
                <p className="mono-label">// CLASS PULSE</p>
                <h3 className="text-base font-bold text-white">وضعیت کلی کلاس</h3>
              </div>
            </div>
            <ArrowUpRight size={16} className="text-fg-500" />
          </div>

          <div className="mb-4">
            <div className="flex items-end justify-between gap-2">
              <span className="mono text-3xl font-black tabular-nums text-white">
                {pctFormatter.format(overview?.class_completion_percentage ?? 0)}
                %
              </span>
              <span className="text-[10.5px] text-fg-500">تکمیل کل کلاس</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div
                initial={{ scaleX: 0 }}
                animate={{
                  scaleX: (overview?.class_completion_percentage ?? 0) / 100,
                }}
                transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                className="h-full w-full origin-right rounded-full bg-gradient-to-l from-success via-emerald-300 to-emerald-100"
                style={{ willChange: "transform" }}
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <MiniStat
              icon={<ClipboardList size={12} />}
              label="کل تکالیف"
              value={<AnimatedNumber value={overview?.total_assignments ?? 0} />}
            />
            <MiniStat
              icon={<CheckCircle2 size={12} />}
              label="تکمیل‌ها"
              value={<AnimatedNumber value={overview?.total_completions ?? 0} />}
            />
            <MiniStat
              icon={<Users size={12} />}
              label="اعضای فعال"
              value={<AnimatedNumber value={overview?.active_users ?? 0} />}
            />
          </div>
        </motion.div>

        {/* مینی‌لیدربورد */}
        <motion.div
          role="button"
          tabIndex={0}
          onClick={() => navigate("/leaderboard")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              navigate("/leaderboard");
            }
          }}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.1 }}
          className="panel panel-hover relative flex cursor-pointer flex-col overflow-hidden rounded-3xl p-5 text-right lg:col-span-4"
        >
          <Corners />
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-warning/25 bg-warning/10">
                <Trophy size={16} className="text-warning" />
              </span>
              <div>
                <p className="mono-label">// TOP 3</p>
                <h3 className="text-base font-bold text-white">صدر جدول</h3>
              </div>
            </div>
            <ArrowUpRight size={16} className="text-fg-500" />
          </div>

          {statsLoading ? (
            <div className="flex flex-1 items-center justify-center py-8">
              <Loader2 size={16} className="animate-spin text-fg-500" />
            </div>
          ) : overview && overview.top_users.length > 0 ? (
            <ul className="flex flex-1 flex-col justify-center gap-2">
              {overview.top_users.map((entry) => (
                <li
                  key={entry.user.id}
                  className="flex items-center gap-2.5 rounded-2xl border border-white/[0.07] bg-white/[0.02] px-2.5 py-2"
                >
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg font-mono text-[10px] font-black ${
                      entry.rank === 1
                        ? "bg-warning text-black"
                        : entry.rank === 2
                          ? "bg-fg-300 text-black"
                          : "bg-[#c98455] text-black"
                    }`}
                  >
                    {entry.rank}
                  </span>
                  <Avatar
                    name={entry.user.username}
                    src={entry.user.avatar_url}
                    size="xs"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span
                        className="truncate text-[12px] font-bold text-white"
                        dir="ltr"
                      >
                        {entry.user.username}
                      </span>
                      {entry.current_streak > 0 && (
                        <span className="inline-flex shrink-0 items-center gap-0.5 rounded-full border border-orange-400/35 bg-orange-500/15 px-1.5 py-0.5 text-[9px] font-black text-orange-200">
                          <Flame size={9} />
                          {entry.current_streak}
                        </span>
                      )}
                    </div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{
                          scaleX: entry.completion_percentage / 100,
                        }}
                        transition={{
                          duration: 0.7,
                          ease: [0.16, 1, 0.3, 1],
                        }}
                        className="h-full w-full origin-right rounded-full bg-warning/80"
                        style={{ willChange: "transform" }}
                      />
                    </div>
                  </div>
                  <span className="mono shrink-0 text-[11px] font-bold tabular-nums text-white">
                    {pctFormatter.format(entry.completion_percentage)}%
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex flex-1 items-center justify-center py-8 text-[11px] text-fg-500">
              هنوز رتبه‌ای ثبت نشده
            </p>
          )}
        </motion.div>

        {/* تمرکز من */}
        <motion.div
          role="button"
          tabIndex={0}
          onClick={() => navigate("/assignments")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              navigate("/assignments");
            }
          }}
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
          className="panel panel-hover relative flex cursor-pointer flex-col overflow-hidden rounded-3xl p-5 text-right lg:col-span-4"
        >
          <Corners />
          <div className="mb-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
                <Target size={16} className="text-danger" />
              </span>
              <div>
                <p className="mono-label">// MY FOCUS</p>
                <h3 className="text-base font-bold text-white">تمرکز من</h3>
              </div>
            </div>
            <ArrowUpRight size={16} className="text-fg-500" />
          </div>

          <div className="mb-3 grid grid-cols-3 gap-2">
            <MiniStat
              icon={<CircleDashed size={12} />}
              label="در جریان"
              value={<AnimatedNumber value={personal.pending} />}
            />
            <MiniStat
              icon={<Flame size={12} />}
              label="فوری"
              value={<AnimatedNumber value={personal.urgent} />}
              tone="danger"
            />
            <MiniStat
              icon={<CheckCircle2 size={12} />}
              label="انجام‌شده"
              value={<AnimatedNumber value={personal.done} />}
              tone="success"
            />
          </div>

          {loading && items.length === 0 ? (
            <div className="flex flex-1 items-center justify-center py-6">
              <Loader2 size={16} className="animate-spin text-fg-500" />
            </div>
          ) : personal.next.length > 0 ? (
            <ul className="mt-auto space-y-1.5">
              {personal.next.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center gap-2 rounded-xl border border-white/[0.06] bg-white/[0.02] px-2.5 py-1.5"
                >
                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-danger" />
                  <span className="min-w-0 flex-1 truncate text-[11px] font-semibold text-fg-300">
                    {item.title}
                  </span>
                  <span className="shrink-0 text-[9.5px] text-fg-500">
                    {relativeDue(item.due_date, now)}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="flex flex-1 items-center justify-center py-6 text-[11px] text-fg-500">
              تکلیف بازِ سررسیده‌ای نداری ✨
            </p>
          )}
        </motion.div>
      </div>

      {/* Pulse — تیکر تک‌خطیِ آخرین پیام‌ها و دیدگاه‌ها + بج ناخوانده‌ها */}
      <PulseBox />

      {/* --------------------------------------------------------------
          ردیف سوم: روند ۷ روزه + برنامه فردا
      -------------------------------------------------------------- */}
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-7">
          <Suspense
            fallback={
              <div className="panel h-[282px] animate-pulse rounded-3xl border border-white/8" />
            }
          >
            <ClassTrendChart
              data={overview?.weekly_trend ?? []}
              onOpen={() => navigate("/leaderboard")}
            />
          </Suspense>
        </div>

        <motion.div
          role="button"
          tabIndex={0}
          onClick={() => navigate("/timetable")}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              navigate("/timetable");
            }
          }}
          className="cursor-pointer lg:col-span-5 [&>section]:mt-0 [&>section]:h-full"
        >
          <TomorrowSchedule bySubject={bySubject} now={now} mode="tomorrow" />
        </motion.div>
      </div>
    </div>
  );
}

function MiniStat({
  icon,
  label,
  value,
  tone = "default",
}: {
  icon: ReactNode;
  label: string;
  value: ReactNode;
  tone?: "default" | "success" | "danger";
}) {
  const toneClass =
    tone === "success"
      ? "text-success"
      : tone === "danger"
        ? "text-danger"
        : "text-white";
  return (
    <div className="rounded-2xl border border-white/[0.07] bg-white/[0.02] px-2 py-2 text-center">
      <span className="mx-auto mb-1 flex h-5 w-5 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] text-fg-500">
        {icon}
      </span>
      <p className={`mono text-base font-black tabular-nums ${toneClass}`}>
        {value}
      </p>
      <p className="text-[9px] text-fg-500">{label}</p>
    </div>
  );
}
