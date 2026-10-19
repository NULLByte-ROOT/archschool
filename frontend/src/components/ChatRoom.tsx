import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  ChevronRight,
  FileText,
  Loader2,
  MessageCircle,
  Paperclip,
  Send,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  fetchMessages,
  resolveMediaUrl,
  sendMessage,
  uploadFile,
} from "../api/client";
import type { Message } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useChatSocket } from "../hooks/useChatSocket";
import { chatDayLabel, chatTime } from "../lib/chat";
import Avatar from "./Avatar";

const IMAGE_RE = /\.(png|jpe?g|gif|webp|avif|bmp)(\?|$)/i;

const MessageBubble = memo(function MessageBubble({
  message,
  own,
  showTail,
  showName,
  animate,
}: {
  message: Message;
  own: boolean;
  showTail: boolean;
  showName: boolean;
  animate: boolean;
}) {
  const media = resolveMediaUrl(message.file_url);
  const isImage = !!message.file_url && IMAGE_RE.test(message.file_url);
  const name = message.sender_username || "کاربر";

  return (
    <div className={`flex w-full items-end ${own ? "justify-end" : "justify-start"}`}>
      {!own && (
        <span className="w-7 shrink-0 self-end">
          {showName && <Avatar name={name} size="xs" />}
        </span>
      )}

      <div
        className={`relative max-w-[84%] min-w-0 rounded-2xl px-3 py-1.5 sm:max-w-[74%] ${
          own
            ? "bubble-own rounded-bl-md text-white"
            : "bubble-other rounded-br-md text-fg-100"
        } ${showTail ? (own ? "bubble-tail-own" : "bubble-tail-other") : ""} ${
          animate ? "msg-in" : ""
        }`}
      >
        {!own && showName && (
          <p className="mb-0.5 text-[11px] font-bold text-[#7cb8e8]">{name}</p>
        )}

        {message.file_url && isImage && (
          <a href={media} target="_blank" rel="noreferrer" className="mb-1 block">
            <img
              src={media}
              alt=""
              loading="lazy"
              decoding="async"
              className="max-h-72 w-full rounded-xl object-cover"
            />
          </a>
        )}

        {message.file_url && !isImage && (
          <a
            href={media}
            target="_blank"
            rel="noreferrer"
            className="mb-1 flex items-center gap-2 rounded-xl border border-white/10 bg-black/20 px-2.5 py-2 text-[12px] font-medium text-fg-100"
          >
            <FileText size={16} className="shrink-0 opacity-70" />
            <span className="truncate" dir="ltr">
              {message.file_url.split("/").pop() || "فایل"}
            </span>
          </a>
        )}

        {message.content && (
          <p className="text-[13.5px] leading-6 whitespace-pre-wrap break-words">
            {message.content}
          </p>
        )}

        <span
          className={`mt-0.5 block text-left font-mono text-[9px] tabular-nums ${
            own ? "text-white/55" : "text-fg-500"
          }`}
          dir="ltr"
        >
          {chatTime(message.created_at)}
        </span>
      </div>
    </div>
  );
});

export default function ChatRoom({
  room,
  title,
  subtitle,
  avatarName,
  headerIcon,
  peerId,
  assignmentId,
  compact = false,
  onBack,
}: {
  room: string;
  title: string;
  subtitle?: string;
  avatarName?: string;
  headerIcon?: ReactNode;
  peerId?: number;
  assignmentId?: number;
  compact?: boolean;
  onBack?: () => void;
}) {
  const { user } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const nearBottomRef = useRef(true);
  const initialScrollRef = useRef(true);

  const scope = assignmentId ? "assignment" : peerId ? "private" : "global";

  const appendMessage = useCallback((message: Message) => {
    setMessages((prev) =>
      prev.some((item) => item.id === message.id) ? prev : [...prev, message]
    );
  }, []);

  const { connected, send } = useChatSocket(room, appendMessage);

  useEffect(() => {
    let active = true;
    fetchMessages({ scope, peerId, assignmentId, limit: 150 })
      .then((data) => {
        if (active) setMessages(data);
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "خطا در بارگذاری گفتگو");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [scope, peerId, assignmentId, room]);

  // اسکرول: بار اول بدون انیمیشن، بعد از آن نرم
  useEffect(() => {
    if (loading) return;
    const el = scrollerRef.current;
    if (!el) return;
    if (initialScrollRef.current) {
      el.scrollTop = el.scrollHeight;
      initialScrollRef.current = false;
      return;
    }
    if (nearBottomRef.current) {
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    }
  }, [messages, loading]);

  const items = useMemo(() => {
    return messages.map((message, index) => {
      const previous = messages[index - 1];
      const dayChanged =
        !previous ||
        chatDayLabel(previous.created_at) !== chatDayLabel(message.created_at);
      const firstOfGroup =
        !previous || previous.sender_id !== message.sender_id || dayChanged;
      const own = message.sender_id === user?.id;
      return {
        message,
        own,
        showTail: firstOfGroup,
        showName: firstOfGroup && !own,
        day: dayChanged ? chatDayLabel(message.created_at) : null,
        animate: index === messages.length - 1,
      };
    });
  }, [messages, user?.id]);

  const payloadBase = useMemo(
    () =>
      assignmentId
        ? { assignment_id: assignmentId }
        : peerId
          ? { receiver_id: peerId }
          : {},
    [assignmentId, peerId]
  );

  async function deliver(payload: { content: string; file_url?: string }) {
    if (send({ type: "message", ...payloadBase, ...payload })) return;
    const message = await sendMessage({ ...payloadBase, ...payload });
    appendMessage(message);
  }

  async function handleSend() {
    const content = text.trim();
    if (!content || sending) return;
    setText("");
    setError(null);
    setSending(true);
    try {
      await deliver({ content });
    } catch (e) {
      setText(content);
      setError(e instanceof Error ? e.message : "ارسال پیام ناموفق بود");
    } finally {
      setSending(false);
    }
  }

  async function handleFile(file: File | undefined) {
    if (!file || uploading) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await uploadFile(file);
      await deliver({ content: "", file_url: uploaded.url });
    } catch (e) {
      setError(e instanceof Error ? e.message : "آپلود فایل ناموفق بود");
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }

  return (
    <section
      className={`relative flex min-h-0 w-full flex-col overflow-hidden bg-black ${
        compact
          ? "h-[460px] rounded-3xl border border-white/10 sm:h-[540px]"
          : "h-full rounded-none border-0 md:rounded-3xl md:border md:border-white/10 md:bg-black/40"
      }`}
    >
      {/* هدر */}
      <header className="relative z-10 flex shrink-0 items-center gap-2 border-b border-white/10 bg-black px-2 py-2 sm:px-4 md:bg-black/50 md:backdrop-blur-xl">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-300 transition active:bg-white/10 md:hidden"
            aria-label="بازگشت"
          >
            <ChevronRight size={22} />
          </button>
        )}

        {avatarName ? (
          <Avatar name={avatarName} size="sm" />
        ) : (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-white/12 bg-white/[0.05] text-white">
            {headerIcon ?? <MessageCircle size={17} />}
          </span>
        )}

        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[15px] font-bold text-white">{title}</h2>
          <p className="flex items-center gap-1.5 truncate text-[10px] text-fg-500">
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                connected ? "bg-success shadow-[0_0_8px_#34d399]" : "bg-fg-500"
              }`}
            />
            {connected ? "آنلاین" : "در حال اتصال…"}
            {subtitle && <span className="truncate">· {subtitle}</span>}
          </p>
        </div>

        <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-[9px] text-fg-500 sm:flex">
          {connected ? <Wifi size={11} /> : <WifiOff size={11} />}
          {messages.length} MSG
        </span>
      </header>

      {/* پیام‌ها */}
      <div
        ref={scrollerRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          nearBottomRef.current =
            el.scrollHeight - el.scrollTop - el.clientHeight < 140;
        }}
        className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-3 [-webkit-overflow-scrolling:touch]"
      >
        <div className="pointer-events-none absolute inset-0 grid-bg opacity-[0.1]" />

        {loading ? (
          <div className="relative flex h-full items-center justify-center gap-2 text-xs text-fg-500">
            <Loader2 size={16} className="animate-spin" />
            در حال بارگذاری گفتگو…
          </div>
        ) : messages.length === 0 ? (
          <div className="relative flex h-full flex-col items-center justify-center gap-2 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
              <MessageCircle size={22} className="text-fg-500" />
            </span>
            <p className="text-sm font-semibold text-fg-300">هنوز پیامی نیست</p>
            <p className="max-w-[240px] text-[11px] leading-5 text-fg-500">
              اولین پیام را بفرست تا گفتگو شروع شود.
            </p>
          </div>
        ) : (
          <div className="relative flex flex-col gap-1">
            {items.map((item) => (
              <Fragment key={item.message.id}>
                {item.day && (
                  <div className="sticky top-1 z-10 mx-auto w-fit rounded-full bg-black/75 px-3 py-1 text-[10px] font-semibold text-fg-300">
                    {item.day}
                  </div>
                )}
                <MessageBubble
                  message={item.message}
                  own={item.own}
                  showTail={item.showTail}
                  showName={item.showName}
                  animate={item.animate}
                />
              </Fragment>
            ))}
          </div>
        )}
      </div>

      {/* ورودی */}
      <div className="pb-safe shrink-0 border-t border-white/10 bg-black px-2 pt-2 sm:px-3 md:bg-black/55">
        {error && (
          <p className="mb-2 rounded-lg border border-danger/25 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
            {error}
          </p>
        )}

        <div className="flex items-end gap-1.5 pb-2">
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            onChange={(e) => handleFile(e.target.files?.[0])}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-300 transition active:bg-white/10 disabled:opacity-50"
            title="پیوست فایل"
            aria-label="پیوست فایل"
          >
            {uploading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Paperclip size={21} />
            )}
          </button>

          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder="پیامت را بنویس…"
            className="input max-h-28 min-h-11 min-w-0 flex-1 resize-none rounded-full py-3 text-base leading-5 md:max-h-32 md:min-h-10 md:text-[13px]"
          />

          <button
            type="button"
            onClick={handleSend}
            disabled={!text.trim() || sending}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#2b5278] text-white transition active:scale-95 disabled:bg-white/10 disabled:text-fg-500"
            aria-label="ارسال"
          >
            {sending ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={18} className="-scale-x-100" />
            )}
          </button>
        </div>
      </div>
    </section>
  );
}
