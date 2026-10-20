import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  CalendarDays,
  Crown,
  Loader2,
  MessageCircle,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import { fetchUserProfile } from "../api/client";
import type { UserProfile } from "../api/client";
import { parseDue } from "../lib/assignments";
import Avatar from "./Avatar";

function lastSeenLabel(value?: string | null): string {
  if (!value) return "اخیراً دیده نشده";
  const date = parseDue(value);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 2) return "همین حالا آنلاین";
  if (minutes < 60) return `${minutes} دقیقه پیش`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ساعت پیش`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days} روز پیش`;
  return date.toLocaleDateString("fa-IR", { day: "numeric", month: "long" });
}

export default function UserProfileModal({
  userId,
  onClose,
}: {
  userId: number | null;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!userId) return;
    let active = true;
    fetchUserProfile(userId)
      .then((data) => {
        if (active) setProfile(data);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "خطا در بارگذاری پروفایل");
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

  return createPortal(
    <AnimatePresence>
      {userId && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.16 }}
          className="fixed inset-0 z-[150] flex items-end justify-center bg-black/65 p-0 sm:items-center sm:p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 36, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 24, opacity: 0 }}
            transition={{ type: "spring", stiffness: 320, damping: 30 }}
            onClick={(event) => event.stopPropagation()}
            className="relative w-full max-w-sm overflow-hidden rounded-t-3xl border border-white/10 bg-[#111318] shadow-2xl will-change-transform sm:rounded-3xl"
          >
            <div className="relative h-28 overflow-hidden bg-gradient-to-br from-white/15 via-white/5 to-transparent">
              <span className="pointer-events-none absolute inset-0 grid-bg opacity-30" />
              <button
                type="button"
                onClick={onClose}
                className="icon-btn absolute top-3 left-3 z-10"
                aria-label="بستن"
              >
                <X size={16} />
              </button>
            </div>

            <div className="relative px-5 pb-5">
              <div className="-mt-12 mb-3 flex items-end justify-between gap-3">
                <Avatar
                  name={profile?.username ?? "?"}
                  src={profile?.avatar_url}
                  size="xl"
                  className="border-4 border-[#111318] shadow-xl"
                />
                {profile?.is_admin && (
                  <span className="badge mb-1 border-warning/30 bg-warning/10 text-warning">
                    <Crown size={11} />
                    ADMIN
                  </span>
                )}
              </div>

              {loading ? (
                <div className="flex items-center justify-center gap-2 py-10 text-xs text-fg-500">
                  <Loader2 size={15} className="animate-spin" />
                  در حال بارگذاری…
                </div>
              ) : error ? (
                <p className="py-8 text-center text-xs text-danger">{error}</p>
              ) : profile ? (
                <>
                  <h3 className="truncate text-xl font-black text-white" dir="ltr">
                    {profile.username}
                  </h3>
                  <p className="mt-1 flex items-center gap-1.5 text-[11px] text-fg-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-success shadow-[0_0_8px_#34d399]" />
                    {lastSeenLabel(profile.last_seen)}
                  </p>

                  <p className="mt-4 rounded-2xl border border-white/8 bg-white/[0.03] p-3 text-[12.5px] leading-6 text-fg-300">
                    {profile.bio?.trim() || "این کاربر هنوز بیوگرافی ننوشته."}
                  </p>

                  <div className="mt-4 grid grid-cols-3 gap-2">
                    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-2.5 text-center">
                      <Sparkles size={14} className="mx-auto mb-1 text-fg-500" />
                      <p className="mono text-sm font-bold tabular-nums text-white">
                        {profile.points}
                      </p>
                      <p className="text-[9px] text-fg-500">امتیاز</p>
                    </div>
                    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-2.5 text-center">
                      <UserRound size={14} className="mx-auto mb-1 text-fg-500" />
                      <p className="text-[11px] font-bold capitalize text-white">
                        {profile.role}
                      </p>
                      <p className="text-[9px] text-fg-500">نقش</p>
                    </div>
                    <div className="rounded-2xl border border-white/8 bg-white/[0.02] p-2.5 text-center">
                      <CalendarDays size={14} className="mx-auto mb-1 text-fg-500" />
                      <p className="text-[11px] font-bold text-white">
                        {parseDue(profile.created_at).toLocaleDateString("fa-IR", {
                          month: "short",
                          year: "2-digit",
                        })}
                      </p>
                      <p className="text-[9px] text-fg-500">عضویت</p>
                    </div>
                  </div>

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
