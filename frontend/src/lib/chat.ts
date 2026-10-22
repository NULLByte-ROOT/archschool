import type { Message } from "../api/client";

function sameDay(a: Date, b: Date) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

/** ساعت کوتاه برای حباب پیام: ۱۴:۳۲ */
export function chatTime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleTimeString("fa-IR-u-nu-latn", { hour: "2-digit", minute: "2-digit" });
}

/** برچسب روز شناور: امروز / دیروز / تاریخ شمسی */
export function chatDayLabel(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (sameDay(date, today)) return "امروز";
  if (sameDay(date, yesterday)) return "دیروز";
  return date.toLocaleDateString("fa-IR-u-nu-latn", { day: "numeric", month: "long" });
}

/** زمان آخرین پیام در لیست گفتگوها: ۱۴:۳۲ / دیروز / ۱۲ مهر */
export function conversationTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);

  if (sameDay(date, today)) return chatTime(date);
  if (sameDay(date, yesterday)) return "دیروز";
  if (date.getFullYear() === today.getFullYear()) {
    return date.toLocaleDateString("fa-IR-u-nu-latn", { day: "numeric", month: "long" });
  }
  return date.toLocaleDateString("fa-IR-u-nu-latn", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
  });
}

/** پیش‌نمایش آخرین پیام برای لیست گفتگوها */
export function messagePreview(message?: Message | null): string {
  if (!message) return "هنوز پیامی نیست";
  if (message.content) return message.content;
  if (message.file_url) return "📎 فایل ضمیمه";
  return "هنوز پیامی نیست";
}
