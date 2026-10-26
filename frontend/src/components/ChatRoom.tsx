import {
  Fragment,
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode, RefObject } from "react";
import { AnimatePresence, motion, useMotionValue, useTransform } from "framer-motion";
import {
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  Copy,
  CornerUpLeft,
  FileText,
  Forward,
  Globe2,
  Info,
  Loader2,
  MessageCircle,
  MoreVertical,
  Paperclip,
  Pencil,
  Pin,
  PinOff,
  Search,
  Send,
  Smile,
  Trash2,
  X,
} from "lucide-react";
import {
  clearChat,
  deleteMessage,
  editMessage,
  fetchMessages,
  fetchTeam,
  markMessageRead,
  pinMessage,
  readRoomBatch,
  resolveMediaUrl,
  sendMessage,
  unpinMessage,
  uploadFile,
} from "../api/client";
import type { Message, PublicUser } from "../api/client";
import { useAuth } from "../contexts/AuthContext";
import { useChatSocket } from "../hooks/useChatSocket";
import type { ChatSocketEvent } from "../hooks/useChatSocket";
import { useIsMobileWidth } from "../hooks/useMediaQuery";
import { chatDayLabel, chatTime } from "../lib/chat";
import Avatar from "./Avatar";
import UserProfileModal from "./UserProfileModal";
import { openImageGallery } from "./ImageViewer";
import { markRoomRead, setActiveRoom } from "../lib/unread";

const IMAGE_RE = /\.(png|jpe?g|jfif|gif|webp|avif|bmp)(\?|$)/i;
const UPLOAD_ACCEPT = "image/*,video/*,application/pdf";
const EMOJIS = [
  "😀", "😂", "🥹", "😍", "😎", "🤔", "😴", "🤯",
  "👍", "🙏", "👏", "🔥", "💯", "🎉", "❤️", "✅",
  "📚", "📝", "✏️", "📐", "🎨", "⏰", "☕", "🚀",
];

interface MenuState {
  x: number;
  y: number;
  message: Message;
}

function previewText(
  message: { content?: string | null; file_url?: string | null } | null | undefined
) {
  if (!message) return "";
  if (message.content) return message.content;
  if (message.file_url) return "📎 فایل ضمیمه";
  return "";
}

function useOutside<T extends HTMLElement>(
  ref: RefObject<T | null>,
  onOutside: () => void,
  active: boolean
) {
  useEffect(() => {
    if (!active) return;
    function handle(event: MouseEvent | TouchEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        onOutside();
      }
    }
    document.addEventListener("mousedown", handle);
    document.addEventListener("touchstart", handle);
    return () => {
      document.removeEventListener("mousedown", handle);
      document.removeEventListener("touchstart", handle);
    };
  }, [ref, onOutside, active]);
}

const MessageBubble = memo(function MessageBubble({
  message,
  own,
  showTail,
  showName,
  animate,
  highlighted,
  onContext,
  onReply,
  onPressStart,
  onPressEnd,
  onProfile,
  onOpenImage,
  onSeenInfo,
}: {
  message: Message;
  own: boolean;
  showTail: boolean;
  showName: boolean;
  animate: "pop" | "in" | null;
  highlighted: boolean;
  onContext: (message: Message, x: number, y: number) => void;
  onReply: (message: Message) => void;
  onPressStart: (message: Message, x: number, y: number) => void;
  onPressEnd: () => void;
  onProfile: (id: number) => void;
  onOpenImage: (message: Message) => void;
  onSeenInfo: (message: Message) => void;
}) {
  const media = resolveMediaUrl(message.file_url);
  const isImage = !!message.file_url && IMAGE_RE.test(message.file_url);
  const [imageFailed, setImageFailed] = useState(false);
  const showImage = !!message.file_url && isImage && !imageFailed;
  const name = message.sender_username || "کاربر";
  // One reader is enough for the second tick; the sheet lists them all.
  const seenCount = message.seen_by?.length ?? 0;

  return (
    <div
      className={`relative select-none rounded-2xl px-3 pt-2 pb-5 ${
        own
          ? "bubble-own rounded-br-sm text-white"
          : "bubble-other rounded-bl-sm text-fg-100"
      } ${showTail ? (own ? "bubble-tail-own" : "bubble-tail-other") : ""} ${
        animate === "pop" ? "msg-pop" : animate === "in" ? "msg-in" : ""
      } ${highlighted ? "ring-2 ring-[#3390ec]" : ""}`}
      onContextMenu={(event) => {
        event.preventDefault();
        onContext(message, event.clientX, event.clientY);
      }}
      onTouchStart={(event) => {
        const touch = event.touches[0];
        onPressStart(message, touch.clientX, touch.clientY);
      }}
      onTouchEnd={onPressEnd}
      onTouchMove={onPressEnd}
      onTouchCancel={onPressEnd}
    >
      {/* اکشن‌های هاور (دسکتاپ) */}
      <div
        className={`absolute top-1/2 hidden -translate-y-1/2 items-center gap-0.5 rounded-full border border-white/10 bg-[#1c2733] px-1 py-0.5 shadow-lg md:flex ${
          own ? "-left-16" : "-right-16"
        } opacity-0 transition group-hover:opacity-100`}
      >
        <button
          type="button"
          onClick={() => onReply(message)}
          className="flex h-8 w-8 items-center justify-center rounded-full text-fg-300 transition hover:bg-white/10 hover:text-white"
          title="پاسخ"
        >
          <CornerUpLeft size={15} />
        </button>
        <button
          type="button"
          onClick={(event) => {
            const rect = event.currentTarget.getBoundingClientRect();
            onContext(message, rect.left - 160, rect.bottom + 4);
          }}
          className="flex h-8 w-8 items-center justify-center rounded-full text-fg-300 transition hover:bg-white/10 hover:text-white"
          title="گزینه‌های بیشتر"
        >
          <ChevronDown size={15} />
        </button>
      </div>

      {!own && showName && (
        <button
          type="button"
          onClick={() => onProfile(message.sender_id)}
          className="mb-0.5 block text-[12px] font-bold text-[#6cb2ea] hover:underline"
        >
          {name}
        </button>
      )}

      {message.reply_to && (
        <div className="mb-1 overflow-hidden rounded-md border-r-2 border-[#4fa3e3] bg-black/20 py-1 pr-2 pl-1.5">
          <p className="text-[11px] font-bold text-[#6cb2ea]">
            {message.reply_to.sender_username || "کاربر"}
          </p>
          <p className="truncate text-[11px] text-fg-300">
            {previewText(message.reply_to)}
          </p>
        </div>
      )}

      {showImage && (
        <button
          type="button"
          onClick={() => onOpenImage(message)}
          aria-label="نمایش تصویر"
          className="mb-1 block w-full cursor-zoom-in"
        >
          <img
            src={media}
            alt=""
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            className="max-h-72 w-full rounded-lg object-cover"
            onError={() => {
              console.warn("[chat] image failed to load, falling back to file", {
                url: media,
                fileUrl: message.file_url,
              });
              setImageFailed(true);
            }}
          />
        </button>
      )}

      {message.file_url && !showImage && (
        <a
          href={media}
          target="_blank"
          rel="noreferrer"
          className="mb-1 flex items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-2.5 py-2 text-[12px] font-medium text-fg-100"
        >
          <FileText size={16} className="shrink-0 opacity-70" />
          <span className="truncate" dir="ltr">
            {message.file_url.split("/").pop() || "فایل"}
          </span>
        </a>
      )}

      {message.content && (
        <p
          dir="auto"
          className="max-w-full text-[14.5px] leading-relaxed break-words whitespace-pre-wrap"
        >
          {message.content}
        </p>
      )}

      <span
        className={`absolute bottom-1 right-2 flex items-center gap-1 font-mono text-[10px] tabular-nums ${
          own ? "text-white/55" : "text-fg-500"
        } ${message.file_url ? "rounded bg-black/40 px-1" : ""}`}
      >
        {message.edited_at && (
          <span className="font-sans text-[9px] opacity-80">ویرایش‌شده</span>
        )}
        <span className="flex items-center gap-0.5" dir="ltr">
          {chatTime(message.created_at)}
          {own && (
            <button
              type="button"
              onMouseDown={(event) => event.stopPropagation()}
              onClick={(event) => {
                event.stopPropagation();
                onSeenInfo(message);
              }}
              aria-label={
                seenCount > 0
                  ? `دیده‌شده توسط ${seenCount} نفر`
                  : "ارسال شد"
              }
              title={seenCount > 0 ? `${seenCount} نفر دیده‌اند` : "ارسال شد"}
              className={`-mr-0.5 flex items-center rounded px-0.5 transition hover:text-white ${
                seenCount > 0 ? "text-[#4fa3e3]" : ""
              }`}
            >
              {seenCount > 0 ? <CheckCheck size={12} /> : <Check size={11} />}
            </button>
          )}
        </span>
      </span>
    </div>
  );
});

/**
 * موبایلباز: پوشش swipe-to-reply.
 * حباب را می‌توان به چپ یا راست کشید؛ پس از عبور از آستانه، پاسخ فعال می‌شود
 * (مثل تلگرام). روی دسکتاپ هیچ چیزی رندر نمی‌شود تا UI فعلی دست‌نخورده بماند.
 *
 * The motion values / drag springs only exist inside `SwipeInner`, which the
 * desktop build never mounts — previously every one of the (up to 150)
 * messages created a motion value, four transforms and its own matchMedia
 * listener even though swiping is mobile-only.
 */
function SwipeInner({
  message,
  children,
  onReply,
  className = "",
}: {
  message: Message;
  children: React.ReactNode;
  onReply: (message: Message) => void;
  className?: string;
}) {
  const x = useMotionValue(0);

  const rightHintOpacity = useTransform(x, [10, 44], [0, 1]);
  const rightHintScale = useTransform(x, [10, 56], [0.5, 1]);
  const leftHintOpacity = useTransform(x, [-44, -10], [1, 0]);
  const leftHintScale = useTransform(x, [-56, -10], [1, 0.5]);

  return (
    <motion.div
      style={{ x, position: "relative" }}
      className={className}
      drag="x"
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={0.3}
      dragMomentum={false}
      dragDirectionLock
      onDragEnd={(_, info) => {
        if (Math.abs(info.offset.x) > 56) onReply(message);
      }}
    >
      {/* نشان «پاسخ» پشت حباب، در جهت کشیدن */}
      <motion.span
        style={{ opacity: rightHintOpacity, scale: rightHintScale }}
        className="pointer-events-none absolute inset-y-0 -right-1 flex items-center text-[#3390ec]"
        aria-hidden
      >
        <CornerUpLeft size={18} />
      </motion.span>
      <motion.span
        style={{ opacity: leftHintOpacity, scale: leftHintScale }}
        className="pointer-events-none absolute inset-y-0 -left-1 flex items-center text-[#3390ec]"
        aria-hidden
      >
        <CornerUpLeft size={18} />
      </motion.span>
      {children}
    </motion.div>
  );
}

function SwipeableMessage({
  swipe,
  message,
  children,
  onReply,
  className = "",
}: {
  swipe: boolean;
  message: Message;
  children: React.ReactNode;
  onReply: (message: Message) => void;
  className?: string;
}) {
  if (!swipe) {
    // حتی بدون قابلیت کشیدن، عرض حباب باید روی همین flex item محدود شود
    // (محدودکردن درصدی روی خود حباب، داخل یک آیتم با عرض نامشخص، باکس را جمع می‌کند)
    return <div className={className}>{children}</div>;
  }
  return (
    <SwipeInner message={message} onReply={onReply} className={className}>
      {children}
    </SwipeInner>
  );
}

function ContextMenu({
  menu,
  canDelete,
  canEdit,
  onClose,
  onReply,
  onCopy,
  onForward,
  onPin,
  onEdit,
  onDelete,
}: {
  menu: MenuState;
  canDelete: boolean;
  canEdit: boolean;
  onClose: () => void;
  onReply: () => void;
  onCopy: () => void;
  onForward: () => void;
  onPin: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const width = 200;
  const height = ((canDelete ? 5 : 4) + (canEdit ? 1 : 0)) * 40 + 12;
  const left = Math.min(Math.max(8, menu.x), window.innerWidth - width - 8);
  const top = Math.min(Math.max(8, menu.y), window.innerHeight - height - 8);

  const item =
    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[12.5px] text-fg-100 transition hover:bg-white/[0.07]";
  const icon = "h-4 w-4 shrink-0 text-fg-500";

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.96 }}
      transition={{ duration: 0.12, ease: "easeOut" }}
      style={{ top, left, width, transformOrigin: "top right" }}
      className="fixed z-50 rounded-xl border border-white/10 bg-[#1c2733] p-1.5 shadow-2xl will-change-transform"
    >
      <button type="button" className={item} onClick={onReply}>
        <CornerUpLeft className={icon} /> پاسخ
      </button>
      <button type="button" className={item} onClick={onCopy}>
        <Copy className={icon} /> کپی متن
      </button>
      {canEdit && (
        <button
          type="button"
          className={item}
          onClick={() => {
            onEdit();
            onClose();
          }}
        >
          <Pencil className={icon} /> ویرایش پیام
        </button>
      )}
      <button type="button" className={item} onClick={onForward}>
        <Forward className={icon} /> ارسال به…
      </button>
      <button type="button" className={item} onClick={onPin}>
        {menu.message.is_pinned ? (
          <PinOff className={icon} />
        ) : (
          <Pin className={icon} />
        )}
        {menu.message.is_pinned ? "برداشتن سنجاق" : "سنجاق"}
      </button>
      {canDelete && (
        <button
          type="button"
          className={`${item} text-danger hover:bg-danger/10`}
          onClick={() => {
            onDelete();
            onClose();
          }}
        >
          <Trash2 className="h-4 w-4 shrink-0 text-danger" /> حذف
        </button>
      )}
    </motion.div>
  );
}

interface ChatItem {
  message: Message;
  own: boolean;
  showTail: boolean;
  showName: boolean;
  day: string | null;
  animate: "pop" | "in" | null;
}

/**
 * Isolated so that typing in the composer never re-renders the message list.
 */
const MessageList = memo(function MessageList({
  items,
  loading,
  highlightId,
  scrollerRef,
  nearBottomRef,
  swipe,
  onContext,
  onReply,
  onPressStart,
  onPressEnd,
  onProfile,
  onOpenImage,
  onSeenInfo,
}: {
  items: ChatItem[];
  loading: boolean;
  highlightId: number | null;
  scrollerRef: RefObject<HTMLDivElement | null>;
  nearBottomRef: RefObject<boolean>;
  swipe: boolean;
  onContext: (message: Message, x: number, y: number) => void;
  onReply: (message: Message) => void;
  onPressStart: (message: Message, x: number, y: number) => void;
  onPressEnd: () => void;
  onProfile: (id: number) => void;
  onOpenImage: (message: Message) => void;
  onSeenInfo: (message: Message) => void;
}) {
  return (
    <div
      ref={scrollerRef}
      onScroll={(event) => {
        const el = event.currentTarget;
        nearBottomRef.current =
          el.scrollHeight - el.scrollTop - el.clientHeight < 160;
      }}
      className="chat-body chat-scroll relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto overscroll-contain bg-black px-2 py-3 sm:px-3 [-webkit-overflow-scrolling:touch]"
    >
      {loading ? (
        <div className="relative flex h-full items-center justify-center gap-2 text-xs text-fg-500">
          <Loader2 size={16} className="animate-spin" />
          در حال بارگذاری گفتگو…
        </div>
      ) : items.length === 0 ? (
        <div className="relative flex h-full flex-col items-center justify-center gap-2 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 bg-white/[0.03]">
            <MessageCircle size={22} className="text-fg-500" />
          </span>
          <p className="text-sm font-semibold text-fg-300">هنوز پیامی نیست</p>
          <p className="max-w-[240px] text-[11px] leading-5 text-fg-500">
            اولین پیام را بفرست یا روی یک پیام نگه دار تا گزینه‌ها باز شود.
          </p>
        </div>
      ) : (
        <div className="relative flex flex-col gap-2">
          {items.map((item) => (
            <Fragment key={item.message.id}>
              {item.day && (
                <div className="sticky top-1 z-10 mx-auto w-fit rounded-full bg-black/70 px-3 py-1 text-[10px] font-semibold text-fg-300">
                  {item.day}
                </div>
              )}
              <div
                id={`msg-${item.message.id}`}
                className={`group flex w-full items-end gap-1.5 ${
                  item.own ? "justify-start" : "justify-end"
                }`}
              >
                <SwipeableMessage
                  swipe={swipe}
                  message={item.message}
                  onReply={onReply}
                  className={`min-w-0 ${
                    item.own
                      ? "max-w-[calc(100%_-_2.5rem)] sm:max-w-[72%]"
                      : "max-w-[calc(100%_-_2.5rem)] sm:max-w-[68%]"
                  }`}
                >
                  <MessageBubble
                    message={item.message}
                    own={item.own}
                    showTail={item.showTail}
                    showName={item.showName}
                    animate={item.animate}
                    highlighted={highlightId === item.message.id}
                    onContext={onContext}
                    onReply={onReply}
                    onPressStart={onPressStart}
                    onPressEnd={onPressEnd}
                    onProfile={onProfile}
                    onOpenImage={onOpenImage}
                    onSeenInfo={onSeenInfo}
                  />
                </SwipeableMessage>
                {!item.own && (
                  <span className="flex w-8 shrink-0 items-end justify-center">
                    {item.showName && (
                      <button
                        type="button"
                        onClick={() => onProfile(item.message.sender_id)}
                        className="block rounded-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-white/40"
                        aria-label="مشاهده پروفایل"
                      >
                        <Avatar
                          name={item.message.sender_username ?? "کاربر"}
                          src={item.message.sender_avatar_url}
                          size="xs"
                        />
                      </button>
                    )}
                  </span>
                )}
              </div>
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
});

/**
 * Owns the draft text locally so a keystroke only re-renders the composer.
 */
const ChatComposer = memo(function ChatComposer({
  error,
  replyTo,
  sending,
  uploading,
  onSend,
  onFile,
  onCancelReply,
}: {
  error: string | null;
  replyTo: Message | null;
  sending: boolean;
  uploading: boolean;
  onSend: (content: string) => Promise<boolean>;
  onFile: (file: File | undefined) => void;
  onCancelReply: () => void;
}) {
  const [text, setText] = useState("");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (replyTo) textareaRef.current?.focus();
  }, [replyTo]);

  async function submit() {
    const content = text.trim();
    if (!content || sending) return;
    setText("");
    setEmojiOpen(false);
    const ok = await onSend(content);
    if (!ok) setText(content);
  }

  return (
    <div className="chat-composer pb-safe relative z-10 shrink-0 border-t border-white/10 bg-[#0b0b0e] px-2 pt-2 sm:px-3">
      {error && (
        <p className="mb-2 rounded-lg border border-danger/25 bg-danger/10 px-2.5 py-1.5 text-[11px] text-danger">
          {error}
        </p>
      )}

      {replyTo && (
        <div className="mb-2 flex items-center gap-2 rounded-lg border-r-2 border-[#4fa3e3] bg-white/[0.04] px-2.5 py-1.5">
          <CornerUpLeft size={15} className="shrink-0 text-[#6cb2ea]" />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-bold text-[#6cb2ea]">
              پاسخ به {replyTo.sender_username || "کاربر"}
            </p>
            <p className="truncate text-[11px] text-fg-500">{previewText(replyTo)}</p>
          </div>
          <button
            type="button"
            onClick={onCancelReply}
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-fg-500 transition hover:bg-white/10 sm:h-8 sm:w-8"
            aria-label="بستن پاسخ"
          >
            <X size={16} />
          </button>
        </div>
      )}

      <div className="flex items-end gap-1.5 pb-2">
        <input
          ref={fileInputRef}
          type="file"
          accept={UPLOAD_ACCEPT}
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            onFile(file);
            event.target.value = "";
          }}
        />

        <div className="relative flex min-w-0 flex-1 items-end rounded-full border border-white/10 bg-white/[0.04] px-1">
          <button
            type="button"
            onClick={() => setEmojiOpen((value) => !value)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-500 transition hover:text-white"
            aria-label="ایموجی"
          >
            <Smile size={20} />
          </button>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder="پیامت را بنویس…"
            className="max-h-28 min-h-11 min-w-0 flex-1 resize-none rounded-full bg-transparent py-3 pr-2 text-base leading-5 text-white outline-none placeholder:text-fg-500 md:max-h-32 md:text-[13.5px]"
          />

          <AnimatePresence>
            {emojiOpen && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 8 }}
                transition={{ duration: 0.14 }}
                className="absolute bottom-full right-0 mb-2 grid w-[min(17rem,calc(100vw-2rem))] grid-cols-6 gap-1 rounded-xl border border-white/10 bg-[#1c2733] p-2 shadow-2xl will-change-transform"
              >
                {EMOJIS.map((emoji) => (
                  <button
                    key={emoji}
                    type="button"
                    onClick={() => {
                      setText((value) => value + emoji);
                      textareaRef.current?.focus();
                    }}
                    className="flex h-10 w-10 items-center justify-center rounded-lg text-lg transition hover:bg-white/10"
                  >
                    {emoji}
                  </button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {text.trim() ? (
          <button
            type="button"
            onClick={submit}
            disabled={sending}
            className="send-btn flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#3390ec] text-white transition active:scale-95 disabled:opacity-60"
            aria-label="ارسال"
          >
            {sending ? (
              <Loader2 size={18} className="animate-spin" />
            ) : (
              <Send size={19} className="-scale-x-100" />
            )}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-300 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
            title="پیوست فایل"
            aria-label="پیوست فایل"
          >
            {uploading ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <Paperclip size={21} />
            )}
          </button>
        )}
      </div>
    </div>
  );
});

function ChatRoom({
  room,
  title,
  subtitle,
  avatarName,
  avatarSrc,
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
  avatarSrc?: string | null;
  headerIcon?: ReactNode;
  peerId?: number;
  assignmentId?: number;
  compact?: boolean;
  onBack?: () => void;
}) {
  const { user, isAdmin } = useAuth();
  const isMobileWidth = useIsMobileWidth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [moreOpen, setMoreOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [forwardFor, setForwardFor] = useState<Message | null>(null);
  const [forwardTeam, setForwardTeam] = useState<PublicUser[]>([]);
  const [profileId, setProfileId] = useState<number | null>(null);
  const [infoMessage, setInfoMessage] = useState<Message | null>(null);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const pressTimer = useRef<number | undefined>(undefined);
  const nearBottomRef = useRef(true);
  const initialScrollRef = useRef(true);
  const roomKeyRef = useRef(room);

  const scope = assignmentId ? "assignment" : peerId ? "private" : "global";

  const showToast = useCallback((message: string) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 1800);
  }, []);

  /**
   * Union of two message lists, ordered by `created_at` then `id`.
   *
   * The socket can deliver a message *before* the initial REST page resolves
   * (and again after a reconnect). Replacing the state with the fetch result
   * would silently drop those messages, leaving the chat stale until the user
   * refreshes — so every load merges instead of overwriting.
   */
  const mergeMessages = useCallback((prev: Message[], incoming: Message[]) => {
    if (!incoming.length) return prev;
    const known = new Set(prev.map((item) => item.id));
    const merged = prev.slice();
    let changed = false;
    for (const item of incoming) {
      if (known.has(item.id)) continue;
      known.add(item.id);
      merged.push(item);
      changed = true;
    }
    if (!changed) return prev;
    merged.sort((a, b) => {
      const ta = Date.parse(a.created_at);
      const tb = Date.parse(b.created_at);
      if (Number.isFinite(ta) && Number.isFinite(tb) && ta !== tb) return ta - tb;
      return a.id - b.id;
    });
    return merged;
  }, []);

  const appendMessage = useCallback(
    (message: Message) => {
      setMessages((prev) => mergeMessages(prev, [message]));
      // The room is open: everything arriving in it is instantly read.
      markRoomRead(room);
      // A single receipt (instead of a full batch) keeps the sender's double
      // tick immediate for every message that arrives while we are looking.
      if (message.sender_id !== user?.id) {
        void markMessageRead(message.id).catch(() => {
          // Reconnect/poll paths reconcile the tick; never block the list.
        });
      }
    },
    [mergeMessages, room, user?.id]
  );

  const handleEvent = useCallback(
    (event: ChatSocketEvent) => {
      if (event.type === "delete") {
        const id = (event.data as { id?: number } | undefined)?.id;
        if (id) setMessages((prev) => prev.filter((item) => item.id !== id));
      } else if (event.type === "clear") {
        setMessages([]);
      } else if (event.type === "edit") {
        const data = event.data as Message | undefined;
        if (!data) return;
        setMessages((prev) =>
          prev.map((item) => (item.id === data.id ? data : item))
        );
      } else if (event.type === "read") {
        const data = event.data as
          | {
              reader_id?: number;
              reader_username?: string | null;
              read_at?: string;
              message_ids?: number[];
            }
          | undefined;
        if (!data?.message_ids?.length) return;
        // Our own receipt is already implied by the single tick.
        if (data.reader_id === user?.id) return;
        const ids = new Set(data.message_ids);
        const receipt = {
          username: data.reader_username ?? null,
          read_at: data.read_at ?? new Date().toISOString(),
        };
        setMessages((prev) =>
          prev.map((item) => {
            if (!ids.has(item.id)) return item;
            const existing = item.seen_by ?? [];
            if (
              existing.some(
                (entry) =>
                  entry.username === receipt.username &&
                  entry.read_at === receipt.read_at
              )
            ) {
              return item;
            }
            return { ...item, seen_by: [...existing, receipt] };
          })
        );
      } else if (event.type === "pin") {
        const data = event.data as Message | undefined;
        if (!data) return;
        setMessages((prev) =>
          prev.map((item) => {
            if (item.id === data.id) return { ...item, is_pinned: data.is_pinned };
            if (data.is_pinned) return { ...item, is_pinned: false };
            return item;
          })
        );
      }
    },
    [user?.id]
  );

  const refreshMessages = useCallback(() => {
    fetchMessages({ scope, peerId, assignmentId, limit: 150 })
      .then((data) => setMessages((prev) => mergeMessages(prev, data)))
      .catch(() => {
        // Transient failure: keep what we have and try again on the next
        // (re)connect instead of blanking the conversation.
      });
  }, [scope, peerId, assignmentId, mergeMessages]);

  const { connected, status, attempt, send } = useChatSocket(
    room,
    appendMessage,
    handleEvent,
    // After every (re)connect the latest page is re-fetched and merged, so
    // anything broadcast while the socket was down is recovered without a
    // page reload.
    { onOpen: refreshMessages }
  );

  useEffect(() => {
    let active = true;
    if (roomKeyRef.current !== room) {
      roomKeyRef.current = room;
      setMessages([]);
    }
    // Opening a room = reading it: zero its badge right away, then let the
    // server persist the bookmark. Leaving the room clears "active".
    setActiveRoom(room);
    markRoomRead(room);
    // Persist one receipt per unread message so every sender's tick upgrades
    // to double, live, without a refresh.
    void readRoomBatch(room).catch(() => {
      // Offline: the next open retries.
    });
    fetchMessages({ scope, peerId, assignmentId, limit: 150 })
      .then((data) => {
        if (active) setMessages((prev) => mergeMessages(prev, data));
      })
      .catch((e: unknown) => {
        if (active) setError(e instanceof Error ? e.message : "خطا در بارگذاری گفتگو");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      if (roomKeyRef.current === room) setActiveRoom(null);
    };
  }, [scope, peerId, assignmentId, room, mergeMessages]);

  // Safety net: if the socket is not up (proxy hiccup, blocked upgrade, tab
  // resumed after being suspended), poll the REST endpoint so new messages
  // still show up without a page reload. Merging keeps it duplicate-free.
  useEffect(() => {
    if (connected) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshMessages();
    }, 10_000);
    return () => window.clearInterval(id);
  }, [connected, refreshMessages]);

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

  // بستن منوی سه‌نقطه با کلیک بیرون
  useOutside(moreRef, () => setMoreOpen(false), moreOpen);

  // بستن منوی کانتکست با Escape / اسکرول
  useEffect(() => {
    if (!menu) return;
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") setMenu(null);
    }
    function handleScroll() {
      setMenu(null);
    }
    document.addEventListener("keydown", handleKey);
    window.addEventListener("wheel", handleScroll, { passive: true });
    window.addEventListener("touchmove", handleScroll, { passive: true });
    return () => {
      document.removeEventListener("keydown", handleKey);
      window.removeEventListener("wheel", handleScroll);
      window.removeEventListener("touchmove", handleScroll);
    };
  }, [menu]);

  // اولین نتیجه جستجو (محاسبه‌شده، بدون setState در افکت)
  const highlightId = useMemo(() => {
    const needle = searchQuery.trim().toLowerCase();
    if (!needle) return null;
    const match = messages.find((message) =>
      message.content.toLowerCase().includes(needle)
    );
    return match?.id ?? null;
  }, [searchQuery, messages]);

  // گالری تصاویرِ همین اتاق برای نمایشگر تصویر سراسری
  const galleryImages = useMemo(() => {
    return messages
      .filter(
        (message) => message.file_url && IMAGE_RE.test(message.file_url)
      )
      .map((message) => ({
        src: resolveMediaUrl(message.file_url) ?? "",
        alt: message.sender_username || "تصویر گفتگو",
      }))
      .filter((image) => image.src !== "");
  }, [messages]);

  const openRoomImage = useCallback(
    (message: Message) => {
      if (!message.file_url) return;
      const src = resolveMediaUrl(message.file_url);
      if (!src) return;
      const index = galleryImages.findIndex(
        (image) => image.src === src
      );
      openImageGallery(galleryImages, index >= 0 ? index : 0);
    },
    [galleryImages]
  );

  // پرش به نتیجه جستجو (فقط به‌روزرسانی DOM)
  useEffect(() => {
    if (!highlightId) return;
    document
      .getElementById(`msg-${highlightId}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [highlightId]);

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
        animate:
          index === messages.length - 1
            ? own
              ? ("pop" as const)
              : ("in" as const)
            : null,
      };
    });
  }, [messages, user?.id]);

  const pinned = useMemo(
    () => messages.find((message) => message.is_pinned) ?? null,
    [messages]
  );

  const payloadBase = useMemo(
    () =>
      assignmentId
        ? { assignment_id: assignmentId }
        : peerId
          ? { receiver_id: peerId }
          : {},
    [assignmentId, peerId]
  );

  const handlePressStart = useCallback(
    (message: Message, x: number, y: number) => {
      window.clearTimeout(pressTimer.current);
      pressTimer.current = window.setTimeout(() => {
        setMenu({ message, x, y });
        if (typeof navigator.vibrate === "function") navigator.vibrate(12);
      }, 450);
    },
    []
  );

  const handlePressEnd = useCallback(() => {
    window.clearTimeout(pressTimer.current);
  }, []);

  const openMenu = useCallback((message: Message, x: number, y: number) => {
    setMenu({ message, x, y });
  }, []);

  const startReply = useCallback((message: Message) => {
    setReplyTo(message);
    setMenu(null);
  }, []);

  const deliver = useCallback(
    async (payload: { content: string; file_url?: string | null }) => {
      const body = {
        ...payloadBase,
        ...payload,
        reply_to_id: replyTo?.id ?? null,
      };
      if (!send({ type: "message", ...body })) {
        const message = await sendMessage(body);
        appendMessage(message);
      }
    },
    [appendMessage, payloadBase, replyTo, send]
  );

  const handleSend = useCallback(
    async (content: string): Promise<boolean> => {
      if (!content.trim() || sending) return false;
      setError(null);
      setSending(true);
      const reply = replyTo;
      setReplyTo(null);
      try {
        await deliver({ content });
        nearBottomRef.current = true;
        return true;
      } catch (e) {
        setReplyTo(reply);
        setError(e instanceof Error ? e.message : "ارسال پیام ناموفق بود");
        return false;
      } finally {
        setSending(false);
      }
    },
    [deliver, replyTo, sending]
  );

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file || uploading) return;
      console.info("[chat] attachment selected", {
        name: file.name,
        type: file.type,
        size: file.size,
      });
      setUploading(true);
      setError(null);
      try {
        const uploaded = await uploadFile(file);
        await deliver({ content: "", file_url: uploaded.url });
        setReplyTo(null);
        nearBottomRef.current = true;
      } catch (e) {
        console.error("[chat] attachment upload failed", e);
        setError(e instanceof Error ? e.message : "آپلود فایل ناموفق بود");
      } finally {
        setUploading(false);
      }
    },
    [deliver, uploading]
  );

  const cancelReply = useCallback(() => setReplyTo(null), []);

  async function handleCopy(message: Message) {
    setMenu(null);
    const value = message.content || resolveMediaUrl(message.file_url);
    try {
      await navigator.clipboard.writeText(value);
      showToast("متن کپی شد");
    } catch {
      showToast("کپی ناموفق بود");
    }
  }

  async function handlePin(message: Message) {
    setMenu(null);
    try {
      if (message.is_pinned) {
        await unpinMessage(message.id);
        setMessages((prev) =>
          prev.map((item) =>
            item.id === message.id ? { ...item, is_pinned: false } : item
          )
        );
      } else {
        await pinMessage(message.id);
        setMessages((prev) =>
          prev.map((item) =>
            item.id === message.id
              ? { ...item, is_pinned: true }
              : { ...item, is_pinned: false }
          )
        );
      }
    } catch (e) {
      showToast(e instanceof Error ? e.message : "سنجاق ناموفق بود");
    }
  }

  async function handleEdit(message: Message) {
    const next = window.prompt("متن جدید پیام:", message.content);
    if (next === null) return;
    const content = next.trim();
    if (!content && !message.file_url) {
      showToast("متن پیام خالی است");
      return;
    }
    try {
      const updated = await editMessage(message.id, content);
      setMessages((prev) =>
        prev.map((item) => (item.id === message.id ? updated : item))
      );
      showToast("پیام ویرایش شد");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "ویرایش ناموفق بود");
    }
  }

  async function handleDelete(message: Message) {
    try {
      await deleteMessage(message.id);
      setMessages((prev) => prev.filter((item) => item.id !== message.id));
      showToast("پیام حذف شد");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "حذف ناموفق بود");
    }
  }

  async function handleClearChat() {
    setMoreOpen(false);
    if (
      !window.confirm(
        "کل گفتگو برای همه پاک شود؟ این کار قابل بازگشت نیست."
      )
    ) {
      return;
    }
    try {
      await clearChat({ scope, peerId, assignmentId });
      setMessages([]);
      showToast("گفتگو پاک شد");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "پاک کردن ناموفق بود");
    }
  }

  function openForward(message: Message) {
    setMenu(null);
    setForwardFor(message);
    if (forwardTeam.length === 0) {
      fetchTeam()
        .then(setForwardTeam)
        .catch(() => setForwardTeam([]));
    }
  }

  async function forwardTo(peer: number | null) {
    if (!forwardFor) return;
    try {
      await sendMessage({
        content: forwardFor.content,
        file_url: forwardFor.file_url ?? undefined,
        receiver_id: peer,
      });
      showToast("ارسال شد");
    } catch (e) {
      showToast(e instanceof Error ? e.message : "ارسال ناموفق بود");
    } finally {
      setForwardFor(null);
    }
  }

  const connectionLabel = connected
    ? "آنلاین"
    : status === "reconnecting"
      ? attempt > 1
        ? `اتصال مجدد (${attempt})…`
        : "اتصال مجدد…"
      : status === "offline"
        ? "آفلاین"
        : status === "auth-failed"
          ? "ورود مجدد…"
          : "در حال اتصال…";
  const connectionTone = connected
    ? "text-[#4dcd5e]"
    : status === "offline" || status === "auth-failed"
      ? "text-danger"
      : "text-fg-500";
  const connectionDot = connected
    ? "bg-[#4dcd5e]"
    : status === "offline" || status === "auth-failed"
      ? "bg-danger"
      : "bg-fg-500";

  return (
    <section
      className={`chat-room relative flex min-h-0 w-full flex-col overflow-hidden bg-black ${
        compact
          ? "h-[460px] rounded-3xl border border-white/10 sm:h-[540px]"
          : "h-full rounded-none border-0 md:rounded-3xl md:border md:border-white/10 md:bg-black/40"
      }`}
    >
      {/* هدر */}
      <header className="chat-header relative z-20 flex shrink-0 items-center gap-2 border-b border-white/10 bg-[#0b0b0e] px-2 py-2 sm:px-3">
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
          <Avatar name={avatarName} src={avatarSrc} size="sm" />
        ) : (
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-white/12 bg-white/[0.05] text-white">
            {headerIcon ?? <MessageCircle size={18} />}
          </span>
        )}

        <div className="min-w-0 flex-1">
          <h2 className="truncate text-[15px] font-bold text-white">{title}</h2>
          <p className="flex items-center gap-1.5 truncate text-[11px]">
            <span
              className={`h-1.5 w-1.5 rounded-full ${connectionDot}`}
            />
            <span className={connectionTone}>{connectionLabel}</span>
            {subtitle && <span className="truncate text-fg-500">· {subtitle}</span>}
          </p>
        </div>

        {isAdmin && (
          <button
            type="button"
            onClick={handleClearChat}
            className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full text-fg-500 transition hover:bg-danger/15 hover:text-danger sm:flex"
            aria-label="پاک کردن کل گفتگو"
            title="پاک کردن کل گفتگو"
          >
            <Trash2 size={18} />
          </button>
        )}

        <button
          type="button"
          onClick={() => {
            setSearchOpen((value) => !value);
            setMoreOpen(false);
          }}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-300 transition hover:bg-white/10 hover:text-white sm:h-10 sm:w-10"
          aria-label="جستجو"
        >
          <Search size={18} />
        </button>

        <div className="relative" ref={moreRef}>
          <button
            type="button"
            onClick={() => setMoreOpen((value) => !value)}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-fg-300 transition hover:bg-white/10 hover:text-white sm:h-10 sm:w-10"
            aria-label="گزینه‌های بیشتر"
          >
            <MoreVertical size={18} />
          </button>
          <AnimatePresence>
            {moreOpen && (
              <motion.div
                initial={{ opacity: 0, scale: 0.94 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.96 }}
                transition={{ duration: 0.12 }}
                className="absolute top-11 left-0 z-40 w-44 rounded-xl border border-white/10 bg-[#1c2733] p-1.5 shadow-2xl will-change-transform"
              >
                <button
                  type="button"
                  onClick={() => {
                    setSearchOpen(true);
                    setMoreOpen(false);
                  }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[12.5px] text-fg-100 transition hover:bg-white/[0.07]"
                >
                  <Search size={15} className="text-fg-500" /> جستجو در گفتگو
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMessages([]);
                    setMoreOpen(false);
                    showToast("نمایش گفتگو پاک شد");
                  }}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[12.5px] text-fg-300 transition hover:bg-white/[0.07]"
                >
                  <X size={15} /> پاک کردن نمایش
                </button>
                {isAdmin && (
                  <button
                    type="button"
                    onClick={handleClearChat}
                    className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-[12.5px] text-danger transition hover:bg-danger/10"
                  >
                    <Trash2 size={15} /> پاک کردن کل گفتگو
                  </button>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </header>

      {searchOpen && (
        <div className="chat-subbar relative z-10 shrink-0 border-b border-white/10 bg-[#0b0b0e] px-3 py-2">
          <input
            autoFocus
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="جستجو در پیام‌ها…"
            className="input h-11 w-full text-[16px] md:h-9 md:text-[12px]"
          />
        </div>
      )}

      {pinned && (
        <button
          type="button"
          onClick={() =>
            document
              .getElementById(`msg-${pinned.id}`)
              ?.scrollIntoView({ behavior: "smooth", block: "center" })
          }
          className="chat-subbar relative z-10 flex shrink-0 items-center gap-2 border-b border-white/10 bg-[#141418] px-3 py-2 text-right transition hover:bg-white/[0.04]"
        >
          <Pin size={14} className="shrink-0 rotate-45 text-[#6cb2ea]" />
          <span className="min-w-0 flex-1">
            <span className="block text-[10px] font-bold text-[#6cb2ea]">
              پیام سنجاق‌شده
            </span>
            <span className="block truncate text-[11px] text-fg-300">
              {previewText(pinned)}
            </span>
          </span>
        </button>
      )}

      {/* پیام‌ها */}
      <MessageList
        items={items}
        loading={loading}
        highlightId={highlightId}
        scrollerRef={scrollerRef}
        nearBottomRef={nearBottomRef}
        swipe={isMobileWidth}
        onContext={openMenu}
        onReply={startReply}
        onPressStart={handlePressStart}
        onPressEnd={handlePressEnd}
        onProfile={setProfileId}
        onOpenImage={openRoomImage}
        onSeenInfo={setInfoMessage}
      />

      {/* ورودی */}
      <ChatComposer
        error={error}
        replyTo={replyTo}
        sending={sending}
        uploading={uploading}
        onSend={handleSend}
        onFile={handleFile}
        onCancelReply={cancelReply}
      />

      {/* منوی کانتکست */}
      <AnimatePresence>
        {menu && (
          <>
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.1 }}
              className="fixed inset-0 z-40"
              onMouseDown={() => setMenu(null)}
              onTouchStart={() => setMenu(null)}
              onContextMenu={(event) => {
                event.preventDefault();
                setMenu(null);
              }}
            />
            <ContextMenu
              menu={menu}
              canDelete={isAdmin || menu.message.sender_id === user?.id}
              canEdit={menu.message.sender_id === user?.id}
              onClose={() => setMenu(null)}
              onReply={() => startReply(menu.message)}
              onCopy={() => handleCopy(menu.message)}
              onForward={() => openForward(menu.message)}
              onPin={() => handlePin(menu.message)}
              onEdit={() => handleEdit(menu.message)}
              onDelete={() => handleDelete(menu.message)}
            />
          </>
        )}
      </AnimatePresence>

      {/* انتخاب مخاطب برای ارسال */}
      <AnimatePresence>
        {forwardFor && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.14 }}
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-4"
            onClick={() => setForwardFor(null)}
          >
            <motion.div
              initial={{ y: 40, scale: 0.98 }}
              animate={{ y: 0, scale: 1 }}
              exit={{ y: 40, opacity: 0 }}
              transition={{ duration: 0.16, ease: "easeOut" }}
              onClick={(event) => event.stopPropagation()}
              className="max-h-[70dvh] w-full max-w-sm overflow-hidden rounded-t-2xl border border-white/10 bg-[#1c2733] sm:rounded-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <h3 className="text-sm font-bold text-white">ارسال به…</h3>
                <button
                  type="button"
                  onClick={() => setForwardFor(null)}
                  className="flex h-10 w-10 items-center justify-center rounded-full text-fg-500 hover:bg-white/10 sm:h-8 sm:w-8"
                  aria-label="بستن"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="chat-scroll max-h-[52dvh] overflow-y-auto p-1.5">
                <button
                  type="button"
                  onClick={() => forwardTo(null)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-right transition hover:bg-white/[0.06]"
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-full border border-white/20 bg-gradient-to-br from-white/20 to-white/[0.03]">
                    <Globe2 size={18} className="text-white" />
                  </span>
                  <span className="text-[13px] font-semibold text-white">گروه عمومی</span>
                </button>
                {forwardTeam
                  .filter((member) => member.id !== user?.id)
                  .map((member) => (
                    <button
                      key={member.id}
                      type="button"
                      onClick={() => forwardTo(member.id)}
                      className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-right transition hover:bg-white/[0.06]"
                    >
                      <Avatar name={member.username} src={member.avatar_url} size="sm" />
                      <span
                        className="truncate text-[13px] font-semibold text-white"
                        dir="ltr"
                      >
                        {member.username}
                      </span>
                    </button>
                  ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {profileId !== null && (
        <UserProfileModal
          key={profileId}
          userId={profileId}
          onClose={() => setProfileId(null)}
        />
      )}

      {/* مشاهده‌کنندگان پیام — from the tick */}
      <AnimatePresence>
        {infoMessage && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center sm:p-4"
            onMouseDown={() => setInfoMessage(null)}
            onTouchStart={() => setInfoMessage(null)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98 }}
              transition={{ duration: 0.15 }}
              onClick={(event) => event.stopPropagation()}
              className="w-full max-w-sm overflow-hidden rounded-t-2xl border border-white/10 bg-[#1c2733] sm:rounded-2xl"
            >
              <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
                <h3 className="flex items-center gap-2 text-sm font-bold text-white">
                  <Info size={15} className="text-[#4fa3e3]" /> مشاهده پیام
                </h3>
                <button
                  type="button"
                  onClick={() => setInfoMessage(null)}
                  className="flex h-9 w-9 items-center justify-center rounded-full text-fg-500 hover:bg-white/10"
                  aria-label="بستن"
                >
                  <X size={16} />
                </button>
              </div>
              <div className="chat-scroll max-h-[52dvh] overflow-y-auto p-2">
                {(infoMessage.seen_by ?? []).length === 0 ? (
                  <p className="px-3 py-6 text-center text-[12.5px] text-fg-300">
                    هنوز کسی این پیام را ندیده است.
                  </p>
                ) : (
                  (infoMessage.seen_by ?? []).map((entry, index) => (
                    <div
                      key={`${entry.username}-${entry.read_at}-${index}`}
                      className="flex items-center gap-3 rounded-xl px-3 py-2"
                    >
                      <Avatar name={entry.username ?? "کاربر"} size="sm" />
                      <div className="min-w-0 flex-1">
                        <p
                          className="truncate text-[13px] font-semibold text-white"
                          dir="ltr"
                        >
                          {entry.username || "کاربر"}
                        </p>
                        <p className="text-[11px] text-fg-500">
                          {chatDayLabel(entry.read_at)}، {chatTime(entry.read_at)}
                        </p>
                      </div>
                      <CheckCheck size={15} className="text-[#4fa3e3]" />
                    </div>
                  ))
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* توست */}
      <AnimatePresence>
        {toast && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.18 }}
            className="pointer-events-none fixed bottom-24 left-1/2 z-50 -translate-x-1/2 rounded-full bg-black/85 px-4 py-2 text-[12px] font-medium text-white shadow-lg"
          >
            {toast}
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

/**
 * A chat room is expensive (socket, message list, composer, portals). Memoising
 * it means typing in the conversation search — or any other unrelated state
 * change in ChatPage — no longer re-renders the whole open conversation. All of
 * its props are stable (`key` forces a remount when the room changes).
 */
export default memo(ChatRoom);
