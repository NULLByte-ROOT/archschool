import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  CheckCircle2,
  Crown,
  Flame,
  Loader2,
  Medal,
  RefreshCw,
  Sparkles,
  Trophy,
  UploadCloud,
} from "lucide-react";
import { fetchLeaderboard } from "../api/client";
import type { PublicUser } from "../api/client";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import PageHeader from "../components/PageHeader";
import { useAuth } from "../contexts/AuthContext";

const RANK_STYLES = [
  {
    border: "border-warning/45",
    bg: "bg-warning/[0.07]",
    glow: "shadow-[0_18px_50px_-24px_rgba(251,191,36,0.55)]",
    medal: "bg-warning text-black",
  },
  {
    border: "border-white/30",
    bg: "bg-white/[0.055]",
    glow: "shadow-[0_18px_50px_-28px_rgba(255,255,255,0.45)]",
    medal: "bg-fg-300 text-black",
  },
  {
    border: "border-[#c98455]/45",
    bg: "bg-[#c98455]/[0.07]",
    glow: "shadow-[0_18px_50px_-28px_rgba(201,132,85,0.45)]",
    medal: "bg-[#c98455] text-black",
  },
];

export default function LeaderboardPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;
    fetchLeaderboard()
      .then((data) => {
        if (active) setRows(data);
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

  const topPoints = Math.max(rows[0]?.points ?? 0, 1);
  const totalPoints = rows.reduce((sum, row) => sum + row.points, 0);
  const myRank = rows.findIndex((row) => row.id === user?.id) + 1;

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        kicker="leaderboard"
        title="جدول امتیازها"
        subtitle="با انجام تکالیف و آپلود فایل، امتیاز بگیر و بالا برو"
        action={
          <button
            onClick={() => {
              setLoading(true);
              setError(null);
              setRefreshKey((key) => key + 1);
            }}
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
          value={rows[0]?.username ?? "—"}
          hint={`${rows[0]?.points ?? 0} امتیاز`}
        />
        <StatCard
          icon={<Flame size={17} />}
          label="مجموع امتیازها"
          value={String(totalPoints)}
          hint={`${rows.length} بازیکن`}
        />
        <StatCard
          icon={<Sparkles size={17} />}
          label="رتبه تو"
          value={myRank > 0 ? `#${myRank}` : "—"}
          hint={`${user?.points ?? 0} امتیاز`}
          className="col-span-2 sm:col-span-1"
        />
      </div>

      {/* راهنمای امتیاز */}
      <div className="mb-5 grid gap-2 sm:grid-cols-2">
        <div className="flex items-center gap-3 rounded-2xl border border-success/20 bg-success/[0.04] px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-success/25 bg-success/10 text-success">
            <CheckCircle2 size={16} />
          </span>
          <div>
            <p className="text-[12px] font-bold text-white">انجام دادن تکلیف</p>
            <p className="font-mono text-[10px] text-success">+10 POINTS</p>
          </div>
        </div>
        <div className="flex items-center gap-3 rounded-2xl border border-white/12 bg-white/[0.03] px-4 py-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/15 bg-white/[0.05] text-white">
            <UploadCloud size={16} />
          </span>
          <div>
            <p className="text-[12px] font-bold text-white">آپلود فایل برای تکلیف</p>
            <p className="font-mono text-[10px] text-fg-300">+15 POINTS</p>
          </div>
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
          <p className="text-sm text-fg-500">هنوز امتیازی ثبت نشده.</p>
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
          {rows.map((row, index) => {
            const rank = index + 1;
            const style = RANK_STYLES[index];
            const isMe = row.id === user?.id;
            return (
              <motion.div
                key={row.id}
                variants={{
                  hidden: { opacity: 0, y: 10 },
                  show: { opacity: 1, y: 0 },
                }}
                transition={{ duration: 0.22 }}
                className={`relative flex items-center gap-3 overflow-hidden rounded-2xl border p-3 sm:p-4 ${
                  style
                    ? `${style.border} ${style.bg} ${style.glow}`
                    : "border-white/8 bg-white/[0.02]"
                } ${isMe ? "ring-1 ring-white/40" : ""}`}
              >
                <Corners />

                <span
                  className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl font-mono text-[12px] font-bold ${
                    style ? style.medal : "border border-white/10 bg-white/[0.04] text-fg-500"
                  }`}
                >
                  {rank === 1 ? <Crown size={16} /> : rank <= 3 ? <Medal size={16} /> : rank}
                </span>

                <Avatar name={row.username} size={rank === 1 ? "md" : "sm"} />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="truncate text-[13px] font-bold text-white" dir="ltr">
                      {row.username}
                    </p>
                    {row.is_admin && (
                      <span className="badge !py-0.5 !text-[8px]">ADMIN</span>
                    )}
                    {isMe && (
                      <span className="rounded-full border border-white/20 bg-white/10 px-2 py-0.5 text-[9px] font-semibold text-white">
                        تو
                      </span>
                    )}
                  </div>
                  <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
                    <motion.div
                      initial={{ scaleX: 0 }}
                      animate={{ scaleX: Math.max(0.04, row.points / topPoints) }}
                      transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                      className={`h-full w-full origin-right rounded-full ${
                        rank === 1
                          ? "bg-warning"
                          : rank === 2
                            ? "bg-fg-300"
                            : rank === 3
                              ? "bg-[#c98455]"
                              : "bg-white/40"
                      }`}
                    />
                  </div>
                </div>

                <div className="shrink-0 text-left">
                  <p className="font-mono text-base font-bold tabular-nums text-white">
                    {row.points}
                  </p>
                  <p className="font-mono text-[8px] tracking-[0.16em] text-fg-500">
                    POINTS
                  </p>
                </div>
              </motion.div>
            );
          })}
        </motion.div>
      )}
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
