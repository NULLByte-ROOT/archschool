import { memo, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  Crown,
  Flame,
  Loader2,
  Medal,
  RefreshCw,
  Sparkles,
  Trophy,
} from "lucide-react";
import { fetchLeaderboardStats } from "../api/client";
import type { LeaderboardEntry, Role } from "../api/client";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import PageHeader from "../components/PageHeader";
import UserProfileModal from "../components/UserProfileModal";
import { useAuth } from "../contexts/AuthContext";

const RANK_STYLES = [
  {
    border: "border-warning/45",
    bg: "bg-warning/[0.07]",
    glow: "shadow-[0_18px_50px_-24px_rgba(251,191,36,0.55)]",
    medal: "bg-warning text-black",
    bar: "bg-warning",
    pct: "text-warning",
  },
  {
    border: "border-white/30",
    bg: "bg-white/[0.055]",
    glow: "shadow-[0_18px_50px_-28px_rgba(255,255,255,0.45)]",
    medal: "bg-fg-300 text-black",
    bar: "bg-fg-300",
    pct: "text-white",
  },
  {
    border: "border-[#c98455]/45",
    bg: "bg-[#c98455]/[0.07]",
    glow: "shadow-[0_18px_50px_-28px_rgba(201,132,85,0.45)]",
    medal: "bg-[#c98455] text-black",
    bar: "bg-[#c98455]",
    pct: "text-[#e0a479]",
  },
];

type RankStyle = (typeof RANK_STYLES)[number];

const ROLE_BADGE: Record<Role, { label: string; className: string }> = {
  owner: {
    label: "OWNER",
    className: "border-warning/40 bg-warning/10 text-warning",
  },
  admin: {
    label: "ADMIN",
    className: "border-white/25 bg-white/10 text-white",
  },
  friend: {
    label: "FRIEND",
    className: "border-success/35 bg-success/10 text-success",
  },
  member: {
    label: "MEMBER",
    className: "border-white/12 bg-white/[0.04] text-fg-500",
  },
};

const pctFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

function formatPct(value: number): string {
  return `${pctFormatter.format(value)}%`;
}

/**
 * A single leaderboard card. Memoised so refreshing the page (or opening a
 * profile) never re-renders rows whose data did not change; entrance variants
 * still propagate from the parent through AnimatePresence context.
 */
const LeaderboardRow = memo(function LeaderboardRow({
  row,
  rank,
  style,
  isMe,
  onOpen,
}: {
  row: LeaderboardEntry;
  rank: number;
  style: RankStyle | undefined;
  isMe: boolean;
  onOpen: (userId: number) => void;
}) {
  const role = (row.user.role ?? "member") as Role;
  const badge = ROLE_BADGE[role] ?? ROLE_BADGE.member;
  const pct = Math.max(0, Math.min(100, row.completion_percentage));

  return (
    <motion.div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(row.user.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(row.user.id);
        }
      }}
      variants={{
        hidden: { opacity: 0, y: 10 },
        show: { opacity: 1, y: 0 },
      }}
      transition={{ duration: 0.22 }}
      className={`group relative cursor-pointer overflow-hidden rounded-2xl border p-3.5 text-right transition-colors sm:p-4 ${
        style
          ? `${style.border} ${style.bg} ${style.glow}`
          : "border-white/8 bg-white/[0.02] hover:border-white/20"
      } ${isMe ? "ring-1 ring-white/40" : ""}`}
    >
      <Corners />

      <div className="relative flex items-center gap-3">
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-[12px] font-bold ${
            style
              ? style.medal
              : "border border-white/10 bg-white/[0.04] text-fg-500"
          }`}
        >
          {rank === 1 ? (
            <Crown size={16} />
          ) : rank <= 3 ? (
            <Medal size={16} />
          ) : (
            rank
          )}
        </span>

        <Avatar name={row.user.username} src={row.user.avatar_url} size="md" />

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <p
              className="truncate text-[13.5px] font-bold text-white"
              dir="ltr"
            >
              {row.user.username}
            </p>
            <span
              className={`rounded-full border px-1.5 py-0.5 font-mono text-[8px] font-bold tracking-[0.14em] ${badge.className}`}
            >
              {badge.label}
            </span>
            {isMe && (
              <span className="rounded-full border border-white/25 bg-white/10 px-2 py-0.5 text-[9px] font-semibold text-white">
                تو
              </span>
            )}
            {row.current_streak > 0 ? (
              <span className="inline-flex items-center gap-1 rounded-full border border-orange-400/40 bg-gradient-to-l from-orange-500/25 via-orange-500/10 to-transparent px-2 py-0.5 text-[10.5px] font-black text-orange-200 shadow-[0_0_18px_-6px_rgba(251,146,60,0.85)]">
                <Flame size={11} className="shrink-0 text-orange-400" />
                {row.current_streak} روز
              </span>
            ) : (
              <span className="rounded-full border border-white/8 bg-white/[0.02] px-2 py-0.5 text-[9px] text-fg-500">
                بدون استریک
              </span>
            )}
          </div>

          <div className="mt-2 flex items-center gap-2.5">
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-white/[0.06]">
              <motion.div
                initial={{ scaleX: 0 }}
                animate={{ scaleX: pct / 100 }}
                transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
                className={`h-full w-full origin-right rounded-full ${
                  style ? style.bar : "bg-white/40"
                }`}
                style={{ willChange: "transform" }}
              />
            </div>
            <span className="mono shrink-0 text-[9px] tabular-nums text-fg-500">
              {row.completed_count} از {row.total_assignments}
            </span>
          </div>
        </div>

        <div className="shrink-0 text-center">
          <p
            className={`mono text-lg font-black tabular-nums sm:text-xl ${
              style ? style.pct : "text-white"
            }`}
          >
            {formatPct(pct)}
          </p>
          <p className="text-[9px] text-fg-500">تکمیل</p>
        </div>
      </div>
    </motion.div>
  );
});

export default function LeaderboardPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [profileId, setProfileId] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    fetchLeaderboardStats()
      .then((data) => {
        if (!active) return;
        setRows(data);
        setError(null);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "خطا در بارگذاری");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [refreshKey]);

  const me = rows.find((row) => row.user.id === user?.id);
  const teamRecord = rows.reduce(
    (best, row) => Math.max(best, row.best_streak),
    0
  );

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        kicker="leaderboard"
        title="جدول قهرمانان"
        subtitle="رتبه‌بندی بر اساس درصد تکمیل تکالیف — نه امتیاز"
        action={
          <button
            onClick={() => setRefreshKey((key) => key + 1)}
            className="btn-ghost"
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
            بروزرسانی
          </button>
        }
      />

      {/* خلاصه */}
      <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <StatCard
          icon={<Trophy size={17} />}
          label="نفر اول"
          value={rows[0]?.user.username ?? "—"}
          hint={rows[0] ? `${formatPct(rows[0].completion_percentage)} تکمیل` : undefined}
        />
        <StatCard
          icon={<Flame size={17} />}
          label="رکورد استریک تیم"
          value={`${teamRecord} روز`}
          hint="بالاترین استریک بین همهٔ اعضا"
        />
        <StatCard
          icon={<Sparkles size={17} />}
          label="رتبه تو"
          value={me ? `#${me.rank}` : "—"}
          hint={me ? `${formatPct(me.completion_percentage)} تکمیل` : undefined}
          className="col-span-2 sm:col-span-1"
        />
      </div>

      {/* قانون رتبه‌بندی */}
      <div className="mb-5 flex items-start gap-3 rounded-2xl border border-white/10 bg-white/[0.02] px-4 py-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.04] text-warning">
          <Trophy size={16} />
        </span>
        <div className="min-w-0">
          <p className="text-[12px] font-bold text-white">
            رتبه‌بندی فقط با درصد تکمیل
          </p>
          <p className="mt-0.5 text-[11px] leading-5 text-fg-500">
            هرکس درصد بیشتری از تکالیف را انجام داده باشد بالاتر است؛ در صورت
            تساوی، کسی که زودتر به آن درصد رسیده رتبهٔ بالاتر می‌گیرد.
          </p>
        </div>
      </div>

      {/* جدول */}
      {loading ? (
        <div className="panel relative flex items-center justify-center gap-2 p-10 text-sm text-fg-500 sm:p-16">
          <Corners />
          <Loader2 size={16} className="animate-spin" />
          در حال بارگذاری…
        </div>
      ) : error ? (
        <div className="panel relative flex flex-col items-center gap-2 p-10 text-center sm:p-16">
          <Corners />
          <p className="text-sm font-semibold text-white">بارگذاری ناموفق بود</p>
          <p className="text-[11px] text-fg-500">{error}</p>
        </div>
      ) : rows.length === 0 ? (
        <div className="panel relative flex flex-col items-center gap-2 p-10 text-center sm:p-16">
          <Corners />
          <Trophy size={28} className="text-fg-500" />
          <p className="text-sm text-fg-500">هنوز آماری برای نمایش نیست.</p>
        </div>
      ) : (
        <motion.div
          initial="hidden"
          animate="show"
          variants={{
            hidden: {},
            show: { transition: { staggerChildren: 0.035 } },
          }}
          className="space-y-2.5"
        >
          {rows.map((row, index) => (
            <LeaderboardRow
              key={row.user.id}
              row={row}
              rank={index + 1}
              style={RANK_STYLES[index]}
              isMe={row.user.id === user?.id}
              onOpen={setProfileId}
            />
          ))}
        </motion.div>
      )}

      <UserProfileModal userId={profileId} onClose={() => setProfileId(null)} />
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  hint,
  className = "",
}: {
  icon: ReactNode;
  label: string;
  value: string;
  hint?: string;
  className?: string;
}) {
  return (
    <div className={`panel relative overflow-hidden p-4 ${className}`}>
      <Corners />
      <div className="mb-2 flex items-center gap-2 text-fg-500">
        {icon}
        <span className="mono-label">{label}</span>
      </div>
      <p className="truncate text-lg font-black text-white" dir="auto">
        {value}
      </p>
      {hint && <p className="mt-0.5 text-[10px] text-fg-500">{hint}</p>}
    </div>
  );
}
