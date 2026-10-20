import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowUpRight,
  CalendarDays,
  CalendarRange,
  Clock,
  Flame,
  MessageCircle,
  MessageSquare,
  Sparkles,
} from "lucide-react";
import {
  fetchAssignments,
  fetchChatOverview,
  fetchRecentComments,
} from "../api/client";
import type { Assignment, ChatOverview, Message } from "../api/client";
import ActivityChart from "../components/ActivityChart";
import AssignmentTypesChart from "../components/AssignmentTypesChart";
import Avatar from "../components/Avatar";
import Corners from "../components/Corners";
import { useAuth } from "../contexts/AuthContext";
import { useNow } from "../hooks/useNow";
import {
  DAY_MS,
  jalaliToday,
  jalaliTime,
  parseDue,
} from "../lib/assignments";
import { chatTime, messagePreview } from "../lib/chat";

function chatSeenKey(userId?: number) {
  return `chat-seen:${userId ?? "anon"}`;
}

function readSeen(userId?: number): number {
  try {
    return Number(localStorage.getItem(chatSeenKey(userId))) || 0;
  } catch {
    return 0;
  }
}

export default function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const now = useNow(30_000);

  const [items, setItems] = useState<Assignment[]>([]);
  const [overview, setOverview] = useState<ChatOverview | null>(null);
  const [comments, setComments] = useState<Message[]>([]);

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchAssignments(),
      fetchChatOverview(),
      fetchRecentComments(3),
    ])
      .then(([assignments, chat, recent]) => {
        if (!active) return;
        setItems(assignments);
        setOverview(chat);
        setComments(recent);
      })
      .catch(() => undefined);
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

  const recentChats = useMemo(() => {
    const rows: Message[] = [];
    if (overview?.global_message) rows.push(overview.global_message);
    overview?.directs.forEach((direct) => rows.push(direct.message));
    return rows
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      .slice(0, 3);
  }, [overview]);

  const unread = useMemo(() => {
    const seen = readSeen(user?.id);
    return recentChats.filter(
      (message) => new Date(message.created_at).getTime() > seen
    ).length;
  }, [recentChats, user?.id]);

  return (
    <div className="mx-auto max-w-6xl">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-white/8 bg-white/[0.02] px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/12 bg-white/[0.04]">
            <CalendarDays size={17} className="text-white" />
          </span>
          <div>
            <p className="text-sm font-bold text-white">سلام {user?.username} 👋</p>
            <p className="text-[11px] text-fg-500">امروز: {jalaliToday(now)}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1.5 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
            <Clock size={13} className="text-fg-500" />
            <span className="mono text-sm tabular-nums text-fg-100" dir="ltr">
              {jalaliTime(now)}
            </span>
          </span>
          <span className="badge">
            <span className="dot animate-pulse" />
            DASHBOARD
          </span>
        </div>
      </div>

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

          <motion.button
            type="button"
            onClick={() => navigate("/timetable")}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className="cta-glow cta-button group relative flex w-full shrink-0 items-center justify-between gap-4 overflow-hidden rounded-2xl border border-white/70 bg-white px-5 py-4 text-black md:w-auto md:min-w-[260px]"
            style={{ willChange: "transform" }}
          >
            <span className="pointer-events-none absolute inset-0 cta-sheen" />
            <span className="relative flex items-center gap-3">
              <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-black text-white">
                <CalendarRange size={20} />
              </span>
              <span className="text-right">
                <span className="block text-base font-black">برنامه هفتگی</span>
                <span className="block text-[10px] font-semibold opacity-60">
                  COUNTDOWN · TODAY
                </span>
              </span>
            </span>
            <ArrowUpRight size={20} className="relative shrink-0" />
          </motion.button>
        </div>
      </motion.section>

      {/* Stats */}
      <div className="mb-5 grid grid-cols-3 gap-2.5">
        <MiniStat label="کل تکالیف" value={stats.total} />
        <MiniStat label="انجام‌شده" value={stats.done} tone="success" />
        <MiniStat label="فوری" value={stats.urgent} tone="danger" icon={<Flame size={13} />} />
      </div>

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

        {/* Recent chat */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.12 }}
          className="lg:col-span-7"
        >
          <button
            type="button"
            onClick={() => navigate("/chat")}
            className="panel panel-hover relative w-full overflow-hidden rounded-3xl p-5 text-right"
          >
            <div className="mb-4 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
                  <MessageCircle size={16} className="text-white" />
                </span>
                <div>
                  <p className="mono-label">// RECENT CHAT</p>
                  <h3 className="text-base font-bold text-white">آخرین پیام‌ها</h3>
                </div>
              </div>
              <span className="flex items-center gap-2">
                {unread > 0 && (
                  <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-white px-1.5 text-[11px] font-black text-black">
                    {unread}
                  </span>
                )}
                <ArrowUpRight size={15} className="text-fg-500" />
              </span>
            </div>

            {recentChats.length === 0 ? (
              <p className="py-6 text-center text-[11px] text-fg-500">هنوز پیامی نیست</p>
            ) : (
              <ul className="space-y-1.5">
                {recentChats.map((message) => (
                  <li
                    key={message.id}
                    className="flex items-center gap-2.5 rounded-2xl px-2 py-2"
                  >
                    {message.receiver_id === null && message.assignment_id === null ? (
                      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/[0.06]">
                        <MessageCircle size={15} className="text-white" />
                      </span>
                    ) : (
                      <Avatar
                        name={message.sender_username ?? "?"}
                        src={message.sender_avatar_url}
                        size="sm"
                      />
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span
                          className="truncate text-[12px] font-bold text-white"
                          dir="ltr"
                        >
                          {message.receiver_id === null && message.assignment_id === null
                            ? "گروه عمومی"
                            : message.sender_username ?? "کاربر"}
                        </span>
                        <span className="mono shrink-0 text-[9px] text-fg-500">
                          {chatTime(message.created_at)}
                        </span>
                      </span>
                      <span className="mt-0.5 block truncate text-[11px] text-fg-500">
                        {messagePreview(message)}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </button>
        </motion.div>

        {/* Recent comments */}
        <motion.div
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1], delay: 0.16 }}
          className="panel relative overflow-hidden rounded-3xl p-5 lg:col-span-5"
        >
          <div className="mb-4 flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05]">
              <MessageSquare size={16} className="text-white" />
            </span>
            <div>
              <p className="mono-label">// COMMENTS</p>
              <h3 className="text-base font-bold text-white">آخرین نظرات</h3>
            </div>
          </div>

          {comments.length === 0 ? (
            <p className="py-6 text-center text-[11px] text-fg-500">
              هنوز نظری روی تکالیف ثبت نشده
            </p>
          ) : (
            <ul className="space-y-2">
              {comments.map((comment) => (
                <li key={comment.id}>
                  <button
                    type="button"
                    onClick={() =>
                      comment.assignment_id &&
                      navigate(`/assignments/${comment.assignment_id}`)
                    }
                    className="flex w-full items-start gap-2.5 rounded-2xl border border-white/8 bg-white/[0.02] p-2.5 text-right transition hover:border-white/20 hover:bg-white/[0.05]"
                  >
                    <Avatar
                      name={comment.sender_username ?? "?"}
                      src={comment.sender_avatar_url}
                      size="xs"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-[11px] font-bold text-white" dir="ltr">
                          {comment.sender_username ?? "کاربر"}
                        </span>
                        <span className="mono shrink-0 text-[9px] text-fg-500">
                          {chatTime(comment.created_at)}
                        </span>
                      </span>
                      <span className="block truncate text-[11px] text-fg-300">
                        {messagePreview(comment)}
                      </span>
                      {comment.assignment_title && (
                        <span className="mt-1 block truncate text-[10px] text-fg-500">
                          روی: {comment.assignment_title}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </motion.div>
      </div>
    </div>
  );
}

function MiniStat({
  label,
  value,
  tone = "default",
  icon,
}: {
  label: string;
  value: number;
  tone?: "default" | "success" | "danger";
  icon?: ReactNode;
}) {
  const color =
    tone === "success"
      ? "text-success"
      : tone === "danger"
        ? "text-danger"
        : "text-white";
  return (
    <div className="panel relative overflow-hidden rounded-2xl px-3.5 py-3">
      <p className="flex items-center gap-1 text-[10px] text-fg-500">
        {icon}
        {label}
      </p>
      <p className={`mono mt-1 text-xl font-black tabular-nums ${color}`}>{value}</p>
    </div>
  );
}
