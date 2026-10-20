import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Crown,
  Globe2,
  Loader2,
  MessageCircle,
  Search,
} from "lucide-react";
import { fetchChatOverview, fetchTeam } from "../api/client";
import type { ChatOverview, Message, PublicUser } from "../api/client";
import Avatar from "../components/Avatar";
import ChatRoom from "../components/ChatRoom";
import Corners from "../components/Corners";
import { useAuth } from "../contexts/AuthContext";
import { useIsMobileWidth } from "../hooks/useMediaQuery";
import { conversationTime, messagePreview } from "../lib/chat";

interface Conversation {
  key: string;
  kind: "global" | "dm";
  member?: PublicUser;
  last?: Message | null;
}

export default function ChatPage() {
  const { user } = useAuth();
  const isMobile = useIsMobileWidth();
  const [team, setTeam] = useState<PublicUser[]>([]);
  const [overview, setOverview] = useState<ChatOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const [mobileChatOpen, setMobileChatOpen] = useState(
    () => searchParams.has("with") || searchParams.get("room") === "global"
  );

  useEffect(() => {
    let active = true;
    Promise.all([fetchTeam(), fetchChatOverview()])
      .then(([members, data]) => {
        if (!active) return;
        setTeam(members);
        setOverview(data);
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

  useEffect(() => {
    if (!user?.id) return;
    try {
      localStorage.setItem(`chat-seen:${user.id}`, String(Date.now()));
    } catch {
      // ignore
    }
  }, [user?.id]);

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

  const conversations = useMemo<Conversation[]>(() => {
    const directs = new Map<number, Message>();
    overview?.directs.forEach((item) => directs.set(item.peer_id, item.message));

    const dms: Conversation[] = others.map((member) => ({
      key: `dm-${member.id}`,
      kind: "dm",
      member,
      last: directs.get(member.id) ?? null,
    }));

    dms.sort((a, b) => {
      const at = a.last ? new Date(a.last.created_at).getTime() : 0;
      const bt = b.last ? new Date(b.last.created_at).getTime() : 0;
      if (at !== bt) return bt - at;
      return (a.member?.username ?? "").localeCompare(b.member?.username ?? "");
    });

    return [
      { key: "global", kind: "global", last: overview?.global_message ?? null },
      ...dms,
    ];
  }, [others, overview]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return conversations;
    return conversations.filter((conversation) => {
      if (conversation.kind === "global") return "گروه عمومی".includes(needle);
      return (conversation.member?.username ?? "").toLowerCase().includes(needle);
    });
  }, [conversations, query]);

  function openGlobal() {
    setSearchParams({ room: "global" });
    setMobileChatOpen(true);
  }

  function openPrivate(member: PublicUser) {
    setSearchParams({ with: String(member.id) });
    setMobileChatOpen(true);
  }

  const listVisible = !isMobile || !mobileChatOpen;
  const chatVisible = !isMobile || mobileChatOpen;

  return (
    <div className="flex h-full min-h-0 gap-3 overflow-hidden">
      {listVisible && (
        <aside className="chat-list flex h-full w-full shrink-0 flex-col overflow-hidden rounded-none border-0 bg-black md:w-72 md:rounded-3xl md:border md:border-white/10 md:bg-black/40 md:glass lg:w-80">
          <Corners />

          <header className="sticky top-0 z-10 shrink-0 border-b border-white/10 bg-black px-3 py-3 md:glass-top-highlight md:bg-transparent md:px-4 md:py-4">
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

            <div className="relative mt-3 md:mt-4">
              <span className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-fg-500">
                <Search size={14} />
              </span>
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="جستجوی گفتگو…"
                className="input h-11 pr-9 text-[16px] md:h-10 md:text-[12px]"
              />
            </div>
          </header>

          <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain md:p-2.5">
            {loading ? (
              <div className="flex items-center justify-center gap-2 py-10 text-[11px] text-fg-500">
                <Loader2 size={14} className="animate-spin" />
                در حال بارگذاری…
              </div>
            ) : error ? (
              <p className="m-3 rounded-xl border border-danger/20 bg-danger/5 p-3 text-[11px] leading-5 text-danger">
                {error}
              </p>
            ) : filtered.length === 0 ? (
              <p className="px-3 py-8 text-center text-[11px] text-fg-500">
                {others.length === 0 ? "هنوز گفتگویی نیست" : "گفتگویی پیدا نشد"}
              </p>
            ) : (
              <div className="divide-y divide-white/[0.06] md:space-y-1 md:divide-y-0">
                {filtered.map((conversation) => {
                  const isGlobal = conversation.kind === "global";
                  const member = conversation.member;
                  const active = isGlobal
                    ? activeGlobal
                    : selectedUser?.id === member?.id;
                  const name = isGlobal ? "گروه عمومی" : member?.username ?? "";

                  return (
                    <button
                      key={conversation.key}
                      type="button"
                      onClick={() =>
                        isGlobal ? openGlobal() : member && openPrivate(member)
                      }
                      className={`group relative flex w-full items-center gap-3 px-3 py-2.5 text-right transition active:bg-white/[0.07] md:rounded-2xl md:px-2.5 md:hover:bg-white/[0.035] ${
                        active ? "bg-white/[0.05] md:bg-white/[0.07]" : ""
                      }`}
                    >
                      {isGlobal ? (
                        <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/25 bg-gradient-to-br from-white/20 to-white/[0.03] md:h-11 md:w-11">
                          <Globe2 size={20} className="text-white" />
                        </span>
                      ) : (
                        <span className="relative shrink-0">
                          <Avatar name={name} src={member?.avatar_url} size="md" />
                          <span className="absolute -bottom-0.5 -left-0.5 h-3 w-3 rounded-full border-2 border-black bg-success" />
                        </span>
                      )}

                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="flex items-center justify-between gap-2">
                          <span
                            className="flex min-w-0 items-center gap-1.5 truncate text-[14px] font-bold text-white md:text-[12.5px]"
                            dir={isGlobal ? "rtl" : "ltr"}
                          >
                            <span className="truncate">{name}</span>
                            {member?.is_admin && (
                              <Crown size={11} className="shrink-0 text-warning" />
                            )}
                          </span>
                          <span className="shrink-0 font-mono text-[10px] tabular-nums text-fg-500">
                            {conversationTime(conversation.last?.created_at)}
                          </span>
                        </span>
                        <span className="mt-0.5 block truncate text-[12px] text-fg-500">
                          {messagePreview(conversation.last)}
                        </span>
                      </span>

                      {active && (
                        <span className="absolute top-1/2 right-0 hidden h-6 w-[3px] -translate-y-1/2 rounded-full bg-white md:block" />
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          <footer className="hidden shrink-0 border-t border-white/8 p-3 md:block">
            <div className="flex items-center gap-2.5 rounded-2xl border border-white/8 bg-white/[0.03] p-2.5">
              <Avatar name={user?.username ?? "?"} src={user?.avatar_url} size="sm" />
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
        </aside>
      )}

      {chatVisible && (
        <main
          className={`min-h-0 min-w-0 flex-1 ${isMobile ? "chat-enter" : ""}`}
        >
          {selectedUser ? (
            <ChatRoom
              key={activeRoom}
              room={activeRoom}
              title={selectedUser.username}
              subtitle="پیام خصوصی"
              avatarName={selectedUser.username}
              avatarSrc={selectedUser.avatar_url}
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
        </main>
      )}
    </div>
  );
}
