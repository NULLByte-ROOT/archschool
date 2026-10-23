import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUpRight, Rss } from "lucide-react";
import Avatar from "./Avatar";
import Corners from "./Corners";
import { useAuth } from "../contexts/AuthContext";
import { useUnread } from "../lib/unread";
import type { PulseItem } from "../lib/unread";
import { chatTime } from "../lib/chat";

const TICK_MS = 3000;

/** One rotating "latest activity" sentence every 1.5s (Telegram-ish pulse). */
export default function PulseBox() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { feed, total } = useUnread();
  const [tick, setTick] = useState(0);
  const [pedestal, setPedestal] = useState(false);

  useEffect(() => {
    if (feed.length < 2) return;
    const id = window.setInterval(() => setTick((prev) => prev + 1), TICK_MS);
    return () => window.clearInterval(id);
  }, [feed.length]);

  // A fresh batch of items must not race an old index.
  const current: PulseItem | null = feed.length
    ? feed[tick % feed.length]
    : null;

  function openTarget(item: PulseItem) {
    if (item.kind === "comment" && item.assignmentId != null) {
      navigate(`/assignments/${item.assignmentId}`);
      return;
    }
    if (item.room.startsWith("dm:")) {
      const [first, second] = item.room
        .slice(3)
        .split(":")
        .map((value) => Number(value));
      const peer = first === user?.id ? second : first;
      navigate(`/chat?with=${peer}`);
      return;
    }
    navigate("/chat");
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: 0.06 }}
      onMouseEnter={() => setPedestal(true)}
      onMouseLeave={() => setPedestal(false)}
      onClick={() => current && openTarget(current)}
      className="glass panel-hover relative mb-5 cursor-pointer overflow-hidden rounded-3xl p-5"
    >
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-[0.16]" />
      <div className="pointer-events-none absolute -top-20 left-1/4 h-40 w-40 rounded-full bg-white/[0.05] blur-[70px]" />
      <Corners />

      <div className="relative mb-4 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
            <Rss size={16} className="text-white" />
          </span>
          <div>
            <p className="mono-label">// PULSE — جنبِش</p>
            <h3 className="text-base font-bold text-white">آخرین خبرها</h3>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="badge">
            <span className="dot animate-pulse" />
            LIVE
          </span>
          {/* Unread badge — only when there is at least one unread message */}
          {total > 0 && (
            <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-white px-1.5 text-[11px] font-black tabular-nums text-black shadow-[0_0_18px_rgba(255,255,255,0.45)]">
              {total > 99 ? "99+" : total}
            </span>
          )}
        </div>
      </div>

      {/* دوربین تک‌خطی: هر ۱.۵ ثانیه یک جمله */}
      <div className="relative flex min-h-[52px] items-center rounded-2xl border border-white/[0.06] bg-black/30 px-3 py-2.5">
        <AnimatePresence mode="wait" initial={false}>
          {current ? (
            <motion.div
              key={`${current.kind}-${current.id}`}
              initial={{ opacity: 0, y: 14 }}
              animate={{
                opacity: 1,
                y: pedestal ? -1 : 0,
                transition: { duration: 0.5, ease: [0.16, 1, 0.3, 1] },
              }}
              exit={{ opacity: 0, y: -14 }}
              className="flex w-full items-center gap-3"
            >
              {current.kind === "comment" ? (
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/[0.06]">
                  <Rss size={14} className="text-white" />
                </span>
              ) : (
                <Avatar
                  name={current.sender ?? "?"}
                  src={current.avatar}
                  size="sm"
                />
              )}
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span
                    className="truncate text-[12.5px] font-bold text-white"
                    dir="ltr"
                  >
                    {current.sender ?? "کاربر"}
                  </span>
                  <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[9px] font-semibold text-fg-300">
                    {current.kind === "comment"
                      ? "دیدگاه تکلیف"
                      : current.room === "global"
                        ? "گفتگوی عمومی"
                        : "پیام خصوصی"}
                  </span>
                  <span className="mono shrink-0 text-[9px] text-fg-500">
                    {chatTime(current.createdAt)}
                  </span>
                </span>
                <span className="mt-0.5 block truncate text-[12px] text-fg-300">
                  {current.kind === "comment" && current.assignmentTitle
                    ? `روی «${current.assignmentTitle}»: ${current.preview}`
                    : current.preview}
                </span>
              </span>
              <ArrowUpRight
                size={15}
                className="shrink-0 text-fg-500 transition-colors group-hover:text-white"
              />
            </motion.div>
          ) : (
            <motion.p
              key="pulse-empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.4 }}
              className="w-full text-center text-[11px] text-fg-500"
            >
              فعلاً خبری نیست — اولین پیام، همین‌جا می‌درخشد.
            </motion.p>
          )}
        </AnimatePresence>
      </div>
    </motion.section>
  );
}
