import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { motion } from "framer-motion";
import {
  ArrowRight,
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
import Avatar from "./Avatar";

const IMAGE_RE = /\.(png|jpe?g|gif|webp|avif|bmp)(\?|$)/i;

function formatTime(value: string) {
  return new Date(value).toLocaleTimeString("fa-IR", {
    hour: "2-digit",
    minute: "2-digit",
  });
}

const ChatBubble = memo(function ChatBubble({
  message,
  own,
  showAvatar,
  showName,
}: {
  message: Message;
  own: boolean;
  showAvatar: boolean;
  showName: boolean;
}) {
  const media = resolveMediaUrl(message.file_url);
  const isImage = !!message.file_url && IMAGE_RE.test(message.file_url);
  const name = message.sender_username || "کاربر";

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      className={`flex w-full items-end gap-2 ${own ? "justify-end" : "justify-start"}`}
    >
      {!own && (
        <span className="w-8 shrink-0">
          {showAvatar && <Avatar name={name} size="xs" />}
        </span>
      )}

      <div
        className={`relative max-w-[82%] overflow-hidden rounded-2xl border px-3 py-2 sm:max-w-[72%] ${
          own
            ? "rounded-bl-md border-white/20 bg-gradient-to-br from-white to-white/85 text-black shadow-[0_10px_30px_-16px_rgba(255,255,255,0.75)]"
            : "rounded-br-md border-white/10 bg-white/[0.055] text-fg-100"
        }`}
      >
        {!own && showName && (
          <p className="mb-1 text-[11px] font-bold text-white/80">{name}</p>
        )}

        {message.file_url && isImage && (
          <a href={media} target="_blank" rel="noreferrer" className="mb-1.5 block">
            <img
              src={media}
              alt=""
              loading="lazy"
              className="max-h-72 w-full rounded-xl border border-black/10 object-cover"
            />
          </a>
        )}

        {message.file_url && !isImage && (
          <a
            href={media}
            target="_blank"
            rel="noreferrer"
            className={`mb-1.5 flex items-center gap-2 rounded-xl border px-2.5 py-2 text-[12px] font-medium ${
              own
                ? "border-black/10 bg-black/[0.05] text-black"
                : "border-white/10 bg-white/[0.04] text-fg-100"
            }`}
          >
            <FileText size={16} className="shrink-0 opacity-70" />
            <span className="truncate" dir="ltr">
              {message.file_url.split("/").pop() || "فایل"}
            </span>
          </a>
        )}

        {message.content && (
          <p className="whitespace-pre-wrap break-words text-[13px] leading-6">
            {message.content}
          </p>
        )}

        <span
          className={`mt-1 block text-left font-mono text-[9px] tabular-nums ${
            own ? "text-black/45" : "text-fg-500"
          }`}
          dir="ltr"
        >
          {formatTime(message.created_at)}
        </span>
      </div>
    </motion.div>
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

  useEffect(() => {
    if (loading) return;
    const el = scrollerRef.current;
    if (!el) return;
    if (nearBottomRef.current) {
      requestAnimationFrame(() => {
        el.scrollTop = el.scrollHeight;
      });
    }
  }, [messages, loading]);

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
      className={`glass relative flex min-h-0 flex-col overflow-hidden rounded-3xl border border-white/10 bg-black/40 ${
        compact ? "h-[460px] sm:h-[540px]" : "h-full"
      }`}
    >
      {/* هدر */}
      <header className="glass-top-highlight relative z-10 flex shrink-0 items-center gap-3 border-b border-white/10 bg-black/50 px-3 py-3 backdrop-blur-xl sm:px-4">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="icon-btn shrink-0 md:hidden"
            aria-label="بازگشت"
          >
            <ArrowRight size={17} />
          </button>
        )}

        {avatarName ? (
          <Avatar name={avatarName} size="sm" />
        ) : (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/12 bg-white/[0.05] text-white">
            {headerIcon ?? <MessageCircle size={17} />}
          </span>
        )}

        <div className="min-w-0 flex-1">
          <h2 className="truncate text-sm font-bold text-white">{title}</h2>
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
            el.scrollHeight - el.scrollTop - el.clientHeight < 120;
        }}
        className="relative min-h-0 flex-1 overflow-y-auto overscroll-contain px-3 py-4 sm:px-4"
      >
        <div className="pointer-events-none absolute inset-0 grid-bg opacity-[0.12]" />

        {loading ? (
          <div className="relative flex h-full items-center justify-center gap-2 text-xs text-fg-500">
            <Loader2 size={16} className="animate-spin" />
            در حال بارگذاری گفتگو…
          </div>
        ) : messages.length === 0 ? (
          <div className="relative flex h-full flex-col items-center justify-center gap-2 text-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-2xl border border-white/10 bg-white/[0.03]">
              <MessageCircle size={22} className="text-fg-500" />
            </span>
            <p className="text-sm font-semibold text-fg-300">هنوز پیامی نیست</p>
            <p className="max-w-[240px] text-[11px] leading-5 text-fg-500">
              اولین پیام را بفرست تا گفتگو شروع شود.
            </p>
          </div>
        ) : (
          <div className="relative flex flex-col gap-2.5">
            {messages.map((message, index) => {
              const previous = messages[index - 1];
              const own = message.sender_id === user?.id;
              const showAvatar =
                !previous || previous.sender_id !== message.sender_id;
              return (
                <ChatBubble
                  key={message.id}
                  message={message}
                  own={own}
                  showAvatar={showAvatar}
                  showName={showAvatar}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* ورودی */}
      <div className="shrink-0 border-t border-white/10 bg-black/55 p-2.5 sm:p-3">
        {error && (
          <p className="mb-2 rounded-lg border border-danger/25 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
            {error}
          </p>
        )}

        <div className="flex items-end gap-2">
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
            className="icon-btn h-10 w-10 shrink-0 disabled:opacity-50"
            title="پیوست فایل"
            aria-label="پیوست فایل"
          >
            {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={17} />}
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
            className="input max-h-32 min-h-10 flex-1 resize-none py-2.5 leading-5"
          />

          <button
            type="button"
            onClick={handleSend}
            disabled={!text.trim() || sending}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white text-black shadow-[0_0_24px_-8px_rgba(255,255,255,0.9)] transition hover:bg-white/90 disabled:opacity-40 disabled:shadow-none"
            aria-label="ارسال"
          >
            {sending ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Send size={16} className="-scale-x-100" />
            )}
          </button>
        </div>
      </div>
    </section>
  );
}
