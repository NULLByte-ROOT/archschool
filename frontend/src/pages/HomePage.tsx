import { memo, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { animate, motion } from "framer-motion";
import {
  ArrowUpRight,
  CalendarDays,
  CalendarRange,
  CheckCircle2,
  CircleDashed,
  ClipboardList,
  Clock,
  Flame,
  Sparkles,
} from "lucide-react";
import {
  fetchAssignments,
  fetchChatOverview,
  fetchRecentComments,
} from "../api/client";
import type { Assignment } from "../api/client";
import ActivityChart from "../components/ActivityChart";
import AssignmentTypesChart from "../components/AssignmentTypesChart";
import Corners from "../components/Corners";
import PulseBox from "../components/PulseBox";
import { useAuth } from "../contexts/AuthContext";
import { useNow } from "../hooks/useNow";
import {
  DAY_MS,
  jalaliToday,
  jalaliTime,
  parseDue,
} from "../lib/assignments";
import { seedFeed, toPulseItem } from "../lib/unread";

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

export default function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const now = useNow(30_000);

  const [items, setItems] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchAssignments(),
      fetchChatOverview(),
      fetchRecentComments(6),
    ])
      .then(([assignments, overview, comments]) => {
        if (!active) return;
        setItems(assignments);
        // Give the Pulse ticker its initial batch; live updates arrive on
        // the pulse socket afterwards.
        const seeded = [
          overview.global_message
            ? toPulseItem(overview.global_message)
            : null,
          ...overview.directs.map((direct) => toPulseItem(direct.message)),
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

  const stats = useMemo(() => {
    const done = items.filter((item) => item.is_completed_by_me).length;
    const urgent = items.filter(
      (item) =>
        !item.is_completed_by_me &&
        item.due_date &&
        parseDue(item.due_date).getTime() - now < DAY_MS * 2
    ).length;
    return { total: items.length, done, urgent, pending: items.length - done };
  }, [items, now]);

  const statCards: {
    label: string;
    value: number;
    tone: "default" | "success" | "danger" | "muted";
    icon: ReactNode;
    to: string;
  }[] = [
    {
      label: "کل تکالیف",
      value: stats.total,
      tone: "default",
      icon: <ClipboardList size={13} />,
      to: "/assignments",
    },
    {
      label: "انجام‌شده",
      value: stats.done,
      tone: "success",
      icon: <CheckCircle2 size={13} />,
      to: "/assignments",
    },
    {
      label: "در جریان",
      value: stats.pending,
      tone: "muted",
      icon: <CircleDashed size={13} />,
      to: "/assignments",
    },
    {
      label: "فوری",
      value: stats.urgent,
      tone: "danger",
      icon: <Flame size={13} />,
      to: "/assignments",
    },
  ];

  return (
    <div className="mx-auto max-w-6xl">
      {/* هدر خوش‌آمد */}
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
        className="glass mb-5 flex flex-wrap items-center justify-between gap-3 rounded-3xl px-4 py-3.5"
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

      {/* CTA */}
      <motion.section
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
        className="cta-hero relative mb-5 overflow-hidden rounded-[28px] border border-white/10 bg-[#07070a] p-6 sm:p-8"
      >
        <div className="pointer-events-none absolute inset-0 grid-bg opacity-40" />
        <div className="pointer-events-none absolute -top-24 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-white/[0.08] blur-[80px]" />
        <Corners className="border-white/25" />

        <div className="relative flex flex-col items-start justify-between gap-6 md:flex-row md:items-center">
          <div className="max-w-lg">
            <span className="badge mb-3">
              <Sparkles size={11} />
              CLASS TIMETABLE
            </span>
            <h1 className="text-2xl leading-[1.4] font-black text-white sm:text-3xl">
              امروز چه زنگی داری؟
              <span className="block text-fg-500">برنامه‌ات را یک‌جا ببین.</span>
            </h1>
            <p className="mt-2 text-[12.5px] leading-6 text-fg-500">
              زنگ جاری، زمان باقی‌مانده و برنامه فردا — همه با یک کلیک.
            </p>
          </div>

          <div className="relative w-full shrink-0 md:w-auto">
            <span
              aria-hidden
              className="cta-glow-layer pointer-events-none absolute inset-0 rounded-2xl"
            />
            <motion.button
              type="button"
              onClick={() => navigate("/timetable")}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="cta-button group relative flex w-full items-center justify-between gap-4 overflow-hidden rounded-2xl border border-white/70 bg-white px-5 py-4 text-black md:min-w-[260px]"
              style={{ willChange: "transform" }}
            >
              <span className="pointer-events-none absolute inset-0 cta-sheen" />
              <span className="relative flex items-center gap-3">
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-black text-white">
                  <CalendarRange size={20} />
                </span>
                <span className="text-right">
                  <span className="block text-base font-black">برنامه کلاس</span>
                  <span className="block text-[10px] font-semibold opacity-60">
                    COUNTDOWN TO TODAY
                  </span>
                </span>
              </span>
              <ArrowUpRight size={20} className="relative shrink-0" />
            </motion.button>
          </div>
        </div>
      </motion.section>

      {/* Pulse — تیکر تک‌خطیِ آخرین پیام‌ها و دیدگاه‌ها + بج ناخوانده‌ها */}
      <PulseBox />

      {/* Stats — کارت‌های آمار با شمارنده */}
      <div className="mb-5 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        {statCards.map((card, index) => (
          <motion.button
            key={card.label}
            type="button"
            onClick={() => navigate(card.to)}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.35,
              ease: [0.16, 1, 0.3, 1],
              delay: 0.05 + index * 0.05,
            }}
            className="panel panel-hover group relative overflow-hidden rounded-2xl px-4 py-3.5 text-right"
          >
            <div className="pointer-events-none absolute inset-x-0 bottom-0 h-[2px] origin-right bg-white/70 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
            <p className="flex items-center gap-1.5 text-[10px] font-semibold text-fg-500">
              <span
                className={`flex h-5 w-5 items-center justify-center rounded-md border border-white/10 bg-white/[0.04] ${
                  card.tone === "success"
                    ? "text-success"
                    : card.tone === "danger"
                      ? "text-danger"
                      : "text-fg-300"
                }`}
              >
                {card.icon}
              </span>
              {card.label}
            </p>
            <AnimatedNumber
              value={card.value}
              className={`mono mt-2 block text-2xl font-black tabular-nums ${
                card.tone === "success"
                  ? "text-success"
                  : card.tone === "danger"
                    ? "text-danger"
                    : "text-white"
              }`}
            />
          </motion.button>
        ))}
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <ActivityChart completed={stats.done} total={stats.total} />
        </div>

        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.08 }}
          className="lg:col-span-7"
        >
          <AssignmentTypesChart items={items} />
        </motion.div>
      </div>

      {/* اسکلت بارگذاری: وقتی داده‌ای نیست و همچنان لود می‌شود */}
      {loading && items.length === 0 && (
        <div className="mt-8 space-y-2.5">
          {[0, 1, 2].map((row) => (
            <div
              key={row}
              className="h-14 animate-pulse rounded-2xl border border-white/[0.05] bg-white/[0.03]"
            />
          ))}
        </div>
      )}
    </div>
  );
}
