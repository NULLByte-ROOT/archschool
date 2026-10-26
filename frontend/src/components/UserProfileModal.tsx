import { lazy, Suspense, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  CalendarDays,
  Flame,
  Gauge,
  Loader2,
  Lock,
  MessageCircle,
  Settings2,
  Trophy,
  TrendingDown,
  TrendingUp,
  UserRound,
  X,
} from "lucide-react";
import { fetchUserProfile, fetchUserStats } from "../api/client";
import type { LeaderboardEntry, Role, UserProfile } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { parseDue } from "../lib/assignments";
import Avatar from "./Avatar";

// Recharts is heavy: only the profile modal needs a chart, so keep it out of
// the main bundle and mount it when the modal actually opens.
const ProfileActivityChart = lazy(() => import("./ProfileActivityChart"));

const ROLE_STYLE: Record<Role, { label: string; className: string }> = {
  owner: {
    label: "Owner",
    className: "border-warning/40 bg-warning/10 text-warning",
  },
  admin: {
    label: "Admin",
    className: "border-white/25 bg-white/10 text-white",
  },
  friend: {
    label: "Friend",
    className: "border-success/35 bg-success/10 text-success",
  },
  member: {
    label: "Member",
    className: "border-white/12 bg-white/[0.04] text-fg-300",
  },
};

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 1,
});

function lastSeenLabel(value?: string | null): string {
  if (!value) return "آخرین بازدید: نامشخص";
  const date = parseDue(value);
  const diff = Date.now() - date.getTime();
  if (diff < 2 * 60_000) return "آنلاین";
  if (diff < 60 * 60_000) {
    const minutes = Math.max(1, Math.round(diff / 60_000));
    return `آخرین بازدید: ${minutes} دقیقه پیش`;
  }

  const clock = date.toLocaleTimeString("fa-IR-u-nu-latn", {
    hour: "2-digit",
    minute: "2-digit",
  });
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const startOfDay = new Date(date);
  startOfDay.setHours(0, 0, 0, 0);
  const dayDiff = Math.round(
    (startOfToday.getTime() - startOfDay.getTime()) / 86_400_000
  );
  if (dayDiff === 0) return `آخرین بازدید: امروز، ساعت ${clock}`;
  if (dayDiff === 1) return `آخرین بازدید: دیروز، ساعت ${clock}`;
  if (dayDiff < 7) return `آخرین بازدید: ${dayDiff} روز پیش`;
  return `آخرین بازدید: ${date.toLocaleDateString("fa-IR-u-nu-latn", {
    day: "numeric",
    month: "long",
  })}، ساعت ${clock}`;
}

function relativeAgo(value?: string | null): string {
  if (!value) return "—";
  const date = parseDue(value);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "همین حالا";
  if (minutes < 60) return `${minutes} دقیقه پیش`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} روز پیش`;
  return date.toLocaleDateString("fa-IR-u-nu-latn", {
    day: "numeric",
    month: "long",
  });
}

function formatSpeed(hours: number | null): string {
  if (hours === null || Number.isNaN(hours)) return "—";
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} دقیقه`;
  return `${numberFormatter.format(hours)} ساعت`;
}

export default function UserProfileModal({
  userId,
  onClose,
}: {
  userId: number | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const { user, isMember } = useAuth();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [stats, setStats] = useState<LeaderboardEntry | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    setLoading(true);
    setError(null);
    setProfile(null);
    setStats(null);

    Promise.all([fetchUserProfile(userId), fetchUserStats(userId)])
      .then(([nextProfile, nextStats]) => {
        if (!active) return;
        setProfile(nextProfile);
        setStats(nextStats);
      })
      .catch((e: unknown) => {
        if (active) {
          setError(e instanceof Error ? e.message : "خطا در بارگذاری پروفایل");
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", onKey);
    };
  }, [userId, onClose]);

  const isSelf = Boolean(profile && user && profile.id === user.id);
  const role = (profile?.role ?? "member") as Role;
  const roleStyle = ROLE_STYLE[role] ?? ROLE_STYLE.member;
  const pct = Math.max(
    0,
    Math.min(100, stats?.completion_percentage ?? 0)
  );

  return createPortal(
    <AnimatePresence>
      {userId && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="fixed inset-0 z-[150] flex items-end justify-center bg-black/70 p-0 sm:items-center sm:p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 36, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            onClick={(event) => event.stopPropagation()}
            className="chat-scroll relative max-h-[92dvh] w-full max-w-md overflow-x-hidden overflow-y-auto rounded-t-3xl border border-white/12 bg-[#0b0b10] shadow-2xl will-change-transform sm:rounded-3xl"
          >
            {/* پوشش بالای کارت */}
            <div className="relative h-32 overflow-hidden">
              <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-white/16 via-white/5 to-transparent" />
              <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />
              <div className="pointer-events-none absolute -top-24 left-1/2 h-56 w-56 -translate-x-1/2 rounded-full bg-white/10 blur-3xl" />
              <span className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-l from-transparent via-white/50 to-transparent" />
              <button
                type="button"
                onClick={onClose}
                className="icon-btn absolute top-3 left-3 z-10"
                aria-label="بستن"
              >
                <X size={16} />
              </button>
              {stats && stats.rank > 0 && (
                <span className="absolute top-3 right-3 z-10 inline-flex items-center gap-1 rounded-full border border-white/20 bg-black/45 px-2.5 py-1 font-mono text-[10px] font-bold text-white">
                  <Trophy size={11} className="text-warning" />
                  رتبه {stats.rank}
                </span>
              )}
            </div>

            <div className="relative px-5 pb-5">
              <div className="-mt-12 mb-3 flex items-end justify-between gap-3">
                <Avatar
                  name={profile?.username ?? "?"}
                  src={profile?.avatar_url}
                  size="xl"
                  className="border-4 border-[#0b0b10] shadow-xl"
                />
                {profile && (
                  <span
                    className={`badge mb-1 !text-[9px] ${roleStyle.className}`}
                  >
                    <UserRound size={11} />
                    {roleStyle.label}
                  </span>
                )}
              </div>

              {loading ? (
                <div className="flex items-center justify-center gap-2 py-12 text-xs text-fg-500">
                  <Loader2 size={15} className="animate-spin" />
                  در حال بارگذاری…
                </div>
              ) : error ? (
                <p className="py-8 text-center text-xs text-danger">{error}</p>
              ) : profile && stats ? (
                <>
                  <h3
                    className="truncate text-xl font-black text-white"
                    dir="ltr"
                  >
                    {profile.username}
                  </h3>
                  <p className="mt-1 flex items-center gap-1.5 text-[11px] text-fg-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_8px_#34d399]" />
                    {lastSeenLabel(profile.last_seen)}
                    <span className="opacity-50">·</span>
                    <CalendarDays size={11} />
                    عضو از{" "}
                    {parseDue(profile.created_at).toLocaleDateString(
                      "fa-IR-u-nu-latn",
                      { month: "short", year: "2-digit" }
                    )}
                  </p>

                  {/* درصد تکمیل */}
                  <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-3.5">
                    <div className="mb-2 flex items-end justify-between gap-2">
                      <div>
                        <p className="mono-label">// COMPLETION</p>
                        <p className="mt-0.5 text-[11px] text-fg-500">
                          {stats.completed_count} از {stats.total_assignments}{" "}
                          تکلیف
                        </p>
                      </div>
                      <p className="mono text-2xl font-black tabular-nums text-white">
                        {numberFormatter.format(pct)}%
                      </p>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
                      <motion.div
                        initial={{ scaleX: 0 }}
                        animate={{ scaleX: pct / 100 }}
                        transition={{ duration: 0.18, ease: "easeOut" }}
                        className="h-full w-full origin-right rounded-full bg-gradient-to-l from-zinc-500 via-zinc-200 to-white"
                        style={{ willChange: "transform" }}
                      />
                    </div>
                  </div>

                  {/* استریک */}
                  <div className="mt-2.5 grid grid-cols-2 gap-2.5">
                    <div className="relative overflow-hidden rounded-2xl border border-orange-400/30 bg-gradient-to-br from-orange-500/15 to-transparent p-3">
                      <div className="pointer-events-none absolute -right-4 -top-4 h-16 w-16 rounded-full bg-orange-500/20 blur-xl" />
                      <div className="relative flex items-center gap-1.5 text-[10px] text-orange-200/80">
                        <Flame size={12} className="text-orange-400" />
                        استریک فعلی
                      </div>
                      <p className="relative mt-1 text-lg font-black text-white">
                        <span className="tabular-nums">
                          {stats.current_streak}
                        </span>{" "}
                        <span className="text-[11px] font-bold text-orange-200/80">
                          روز
                        </span>
                      </p>
                    </div>
                    <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-[10px] text-fg-500">
                        <Trophy size={12} className="text-warning" />
                        بهترین استریک
                      </div>
                      <p className="mt-1 text-lg font-black text-white">
                        <span className="tabular-nums">{stats.best_streak}</span>{" "}
                        <span className="text-[11px] font-bold text-fg-500">
                          روز
                        </span>
                      </p>
                    </div>
                  </div>

                  {/* سرعت و رتبه */}
                  <div className="mt-2.5 grid grid-cols-2 gap-2.5">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-[10px] text-fg-500">
                        <Gauge size={12} />
                        سرعت میانگین
                      </div>
                      <p className="mt-1 text-[13px] font-bold text-white">
                        {formatSpeed(stats.average_speed_hours)}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                      <div className="flex items-center gap-1.5 text-[10px] text-fg-500">
                        <Activity size={12} />
                        آخرین فعالیت
                      </div>
                      <p className="mt-1 text-[13px] font-bold text-white">
                        {stats.completed_today
                          ? "امروز"
                          : relativeAgo(stats.last_completion_time)}
                      </p>
                    </div>
                  </div>

                  {/* قوی‌ترین/ضعیف‌ترین درس */}
                  <div className="mt-2.5 grid grid-cols-2 gap-2.5">
                    <div className="rounded-2xl border border-success/20 bg-success/[0.05] p-3">
                      <div className="flex items-center gap-1.5 text-[10px] text-success/80">
                        <TrendingUp size={12} />
                        قوی‌ترین درس
                      </div>
                      <p className="mt-1 truncate text-[12.5px] font-bold text-white">
                        {stats.strongest_subject ?? "هنوز مشخص نیست"}
                      </p>
                    </div>
                    <div className="rounded-2xl border border-danger/20 bg-danger/[0.05] p-3">
                      <div className="flex items-center gap-1.5 text-[10px] text-danger/80">
                        <TrendingDown size={12} />
                        ضعیف‌ترین درس
                      </div>
                      <p className="mt-1 truncate text-[12.5px] font-bold text-white">
                        {stats.weakest_subject ?? "هنوز مشخص نیست"}
                      </p>
                    </div>
                  </div>

                  {/* نمودار فعالیت ۷ روزه */}
                  <div className="mt-2.5 rounded-2xl border border-white/10 bg-white/[0.02] p-3">
                    <Suspense
                      fallback={
                        <div className="h-[132px] animate-pulse rounded-xl bg-white/[0.03]" />
                      }
                    >
                      <ProfileActivityChart data={stats.weekly_activity} />
                    </Suspense>
                  </div>

                  <p className="mt-3 rounded-2xl border border-white/8 bg-white/[0.03] p-3 text-[12px] leading-6 text-fg-300">
                    {profile.bio?.trim() || "این کاربر هنوز بیوگرافی ننوشته."}
                  </p>

                  {isSelf ? (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        navigate("/settings");
                      }}
                      className="btn-ghost mt-4 w-full"
                    >
                      <Settings2 size={14} />
                      ویرایش پروفایل من
                    </button>
                  ) : isMember ? (
                    <div className="mt-4 flex items-center justify-center gap-1.5 rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5 text-[11px] text-fg-500">
                      <Lock size={12} />
                      برای دسترسی به گفتگو، از ادمین اجازه بگیرید.
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        onClose();
                        navigate(`/chat?with=${profile.id}`);
                      }}
                      className="btn-primary mt-4 w-full"
                    >
                      <MessageCircle size={14} />
                      ارسال پیام
                    </button>
                  )}
                </>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}
