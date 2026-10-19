import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Crown,
  Globe2,
  Loader2,
  MessageCircle,
  Search,
  Users,
} from "lucide-react";
import { fetchTeam } from "../api/client";
import type { PublicUser } from "../api/client";
import Avatar from "../components/Avatar";
import ChatRoom from "../components/ChatRoom";
import Corners from "../components/Corners";
import { useAuth } from "../contexts/AuthContext";

export default function ChatPage() {
  const { user } = useAuth();
  const [team, setTeam] = useState<PublicUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [mobileChatOpen, setMobileChatOpen] = useState(
    () => searchParams.has("with") || searchParams.get("room") === "global"
  );

  useEffect(() => {
    let active = true;
    fetchTeam()
      .then((data) => {
        if (active) setTeam(data);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "خطا در بارگذاری کاربران");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const withId = Number(searchParams.get("with")) || null;
  const selectedUser = useMemo(
    () => team.find((member) => member.id === withId) ?? null,
    [team, withId]
  );
  const activeGlobal = !selectedUser;
  const activeRoom = selectedUser
    ? `dm:${Math.min(user?.id ?? 0, selectedUser.id)}:${Math.max(
        user?.id ?? 0,
        selectedUser.id
      )}`
    : "global";

  const others = useMemo(
    () => team.filter((member) => member.id !== user?.id),
    [team, user?.id]
  );

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return others;
    return others.filter((member) =>
      member.username.toLowerCase().includes(needle)
    );
  }, [others, query]);

  function openGlobal() {
    setSearchParams({ room: "global" });
    setMobileChatOpen(true);
  }

  function openPrivate(member: PublicUser) {
    setSearchParams({ with: String(member.id) });
    setMobileChatOpen(true);
  }

  return (
    <div className="flex h-full min-h-0 gap-3 overflow-hidden">
      {/* ستون گفتگوها */}
      <motion.aside
        initial={{ opacity: 0, x: 18 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
        className={`${
          mobileChatOpen ? "hidden" : "flex"
        } glass relative h-full w-full shrink-0 flex-col overflow-hidden rounded-3xl border border-white/10 bg-black/40 md:flex md:w-72 lg:w-80`}
      >
        <Corners />

        <header className="glass-top-highlight shrink-0 border-b border-white/10 px-4 py-4">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-2xl border border-white/15 bg-white/[0.06]">
                <MessageCircle size={18} className="text-white" />
              </span>
              <div>
                <h1 className="text-base font-black text-white">پیام‌ها</h1>
                <p className="mono text-[9px] tracking-[0.18em] text-fg-500">
                  // ARCHSCHOOL CHAT
                </p>
              </div>
            </div>
            <span className="badge">
              <span className="dot" />
              {others.length + 1}
            </span>
          </div>

          <div className="relative mt-4">
            <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-fg-500">
              <Search size={14} />
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="جستجوی هم‌کلاسی…"
              className="input h-10 pr-9 text-[12px]"
            />
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
          {/* گروه عمومی */}
          <button
            type="button"
            onClick={openGlobal}
            className={`group relative mb-1 flex w-full items-center gap-3 overflow-hidden rounded-2xl border p-3 text-right transition ${
              activeGlobal
                ? "border-white/20 bg-white/[0.07] shadow-[0_0_30px_-18px_rgba(255,255,255,0.8)]"
                : "border-transparent hover:border-white/10 hover:bg-white/[0.035]"
            }`}
          >
            <span className="relative flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/25 bg-gradient-to-br from-white/20 to-white/[0.03]">
              <Globe2 size={20} className="text-white" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-1.5">
                <span className="truncate text-[13px] font-bold text-white">
                  گروه عمومی
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 font-mono text-[8px] text-fg-500">
                  GROUP
                </span>
              </span>
              <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-fg-500">
                <Users size={10} />
                همه بچه‌های کلاس
              </span>
            </span>
            {activeGlobal && (
              <span className="absolute top-1/2 right-0 h-6 w-[3px] -translate-y-1/2 rounded-full bg-white shadow-[0_0_10px_#fff]" />
            )}
          </button>

          <p className="mono-label px-3 py-2">// DIRECT MESSAGES</p>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-10 text-[11px] text-fg-500">
              <Loader2 size={14} className="animate-spin" />
              در حال بارگذاری…
            </div>
          ) : error ? (
            <p className="rounded-xl border border-danger/20 bg-danger/5 p-3 text-[11px] leading-5 text-danger">
              {error}
            </p>
          ) : filtered.length === 0 ? (
            <p className="px-3 py-8 text-center text-[11px] text-fg-500">
              {others.length === 0 ? "هنوز هم‌کلاسی دیگری نیست" : "کاربری پیدا نشد"}
            </p>
          ) : (
            <div className="space-y-1">
              {filtered.map((member) => {
                const active = selectedUser?.id === member.id;
                return (
                  <button
                    key={member.id}
                    type="button"
                    onClick={() => openPrivate(member)}
                    className={`group relative flex w-full items-center gap-3 overflow-hidden rounded-2xl border p-2.5 text-right transition ${
                      active
                        ? "border-white/20 bg-white/[0.07]"
                        : "border-transparent hover:border-white/10 hover:bg-white/[0.035]"
                    }`}
                  >
                    <span className="relative">
                      <Avatar name={member.username} size="sm" />
                      <span className="absolute -bottom-0.5 -left-0.5 h-2.5 w-2.5 rounded-full border-2 border-black bg-success" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate text-[12px] font-semibold text-white" dir="ltr">
                          {member.username}
                        </span>
                        {member.is_admin && (
                          <Crown size={11} className="shrink-0 text-warning" />
                        )}
                      </span>
                      <span className="mt-0.5 block font-mono text-[9px] text-fg-500">
                        {member.points} PTS
                      </span>
                    </span>
                    <span className="h-1.5 w-1.5 rounded-full bg-success opacity-70" />
                    {active && (
                      <span className="absolute top-1/2 right-0 h-6 w-[3px] -translate-y-1/2 rounded-full bg-white" />
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <footer className="shrink-0 border-t border-white/8 p-3">
          <div className="flex items-center gap-2.5 rounded-2xl border border-white/8 bg-white/[0.03] p-2.5">
            <Avatar name={user?.username ?? "?"} size="sm" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-[11px] font-semibold text-white" dir="ltr">
                {user?.username}
              </p>
              <p className="font-mono text-[9px] text-fg-500">
                {user?.points ?? 0} POINTS
              </p>
            </div>
            <span className="h-2 w-2 rounded-full bg-success shadow-[0_0_8px_#34d399]" />
          </div>
        </footer>
      </motion.aside>

      {/* ناحیه گفتگو */}
      <motion.main
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.25 }}
        className={`${
          mobileChatOpen ? "flex" : "hidden"
        } min-h-0 min-w-0 flex-1 md:flex`}
      >
        {selectedUser ? (
          <ChatRoom
            key={activeRoom}
            room={activeRoom}
            title={selectedUser.username}
            subtitle="پیام خصوصی"
            avatarName={selectedUser.username}
            peerId={selectedUser.id}
            onBack={() => setMobileChatOpen(false)}
          />
        ) : (
          <ChatRoom
            key="global"
            room="global"
            title="گروه عمومی"
            subtitle="همه بچه‌های کلاس"
            headerIcon={<Globe2 size={17} />}
            onBack={() => setMobileChatOpen(false)}
          />
        )}
      </motion.main>
    </div>
  );
}
