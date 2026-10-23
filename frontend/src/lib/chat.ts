import type { Message } from "../api/client";

/**
 * Intl formatting is the slowest thing in the chat hot path: `chatDayLabel`
 * runs once per message every time the (up to 150-item) list is re-grouped —
 * i.e. on every single incoming message — and each `toLocaleDateString` builds
 * a fresh Persian-calendar formatter. Every formatted value only depends on the
 * timestamp (and, for "today/yesterday", on the current calendar day), so it is
 * memoised here and reused forever.
 */
const CACHE_LIMIT = 3000;
const timeCache = new Map<string, string>();
const dayCache = new Map<string, string>();

function cacheGet(cache: Map<string, string>, key: string): string | undefined {
  return cache.get(key);
}

function cacheSet(cache: Map<string, string>, key: string, value: string): string {
  if (cache.size >= CACHE_LIMIT) cache.clear();
  cache.set(key, value);
  return value;
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

function sameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** ساعت کوتاه برای حباب پیام: ۱۴:۳۲ */
export function chatTime(value: string | Date): string {
  const key = typeof value === "string" ? value : `ts:${value.getTime()}`;
  const cached = cacheGet(timeCache, key);
  if (cached !== undefined) return cached;
  const date = typeof value === "string" ? new Date(value) : value;
  return cacheSet(
    timeCache,
    key,
    date.toLocaleTimeString("fa-IR-u-nu-latn", { hour: "2-digit", minute: "2-digit" })
  );
}

function dayLabelOf(date: Date): string {
  return date.toLocaleDateString("fa-IR-u-nu-latn", { day: "numeric", month: "long" });
}

/** برچسب روز شناور: امروز / دیروز / تاریخ شمسی */
export function chatDayLabel(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  const today = new Date();
  if (sameDay(date, today)) return "امروز";
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (sameDay(date, yesterday)) return "دیروز";

  const key = `day|${dayKey(date)}`;
  const cached = cacheGet(dayCache, key);
  if (cached !== undefined) return cached;
  return cacheSet(dayCache, key, dayLabelOf(date));
}

/** زمان آخرین پیام در لیست گفتگوها: ۱۴:۳۲ / دیروز / ۱۲ مهر */
export function conversationTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const today = new Date();
  if (sameDay(date, today)) return chatTime(value);
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (sameDay(date, yesterday)) return "دیروز";
  if (date.getFullYear() === today.getFullYear()) return chatDayLabel(date);

  const key = `full|${dayKey(date)}`;
  const cached = cacheGet(dayCache, key);
  if (cached !== undefined) return cached;
  return cacheSet(
    dayCache,
    key,
    date.toLocaleDateString("fa-IR-u-nu-latn", {
      year: "numeric",
      month: "numeric",
      day: "numeric",
    })
  );
}

/** پیش‌نمایش آخرین پیام برای لیست گفتگوها */
export function messagePreview(message?: Message | null): string {
  if (!message) return "هنوز پیامی نیست";
  if (message.content) return message.content;
  if (message.file_url) return "📎 فایل ضمیمه";
  return "هنوز پیامی نیست";
}
