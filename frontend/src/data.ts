// ------------------------------------------------------------------
//  برنامه هفتگی کلاس یازدهم شبکه ۱
// ------------------------------------------------------------------

export interface Subject {
  /** کلید یکتا برای اتصال رویدادها */
  id: string;
  /** نام درس (فارسی) */
  name: string;
  /** نام درس (انگلیسی) */
  nameEn: string;
  /** نام دبیر */
  teacher: string;
}

export type Cell =
  | { kind: "class"; span: number; subject: Subject }
  | { kind: "multi"; span: number; subjects: Subject[] }
  | { kind: "free"; span: number };

export interface Day {
  id: string;
  name: string;
  short: string;
  cells: Cell[];
}

// ---------- درس‌ها ----------
export const SUBJECTS = {
  webDesign: { id: "web-design", name: "طراحی وب", nameEn: "Web Design", teacher: "محمدی‌فر" },
  persian: { id: "persian", name: "فارسی", nameEn: "Persian", teacher: "عسگری" },
  humanEnv: { id: "human-env", name: "انسان و محیط زیست", nameEn: "Human & Environment", teacher: "عزیزی" },
  religion: { id: "religion", name: "دین و زندگی", nameEn: "Religion", teacher: "داوودی" },
  sports: { id: "sports", name: "تربیت بدنی", nameEn: "Sports", teacher: "عزیزی" },
  arabic: { id: "arabic", name: "عربی", nameEn: "Arabic", teacher: "داوودی" },
  entrepreneurship: { id: "entrepreneurship", name: "کارآفرینی", nameEn: "Entrepreneurship", teacher: "مجیدی" },
  history: { id: "history", name: "تاریخ", nameEn: "History", teacher: "نظم‌ده" },
  english: { id: "english", name: "زبان انگلیسی", nameEn: "English", teacher: "علمدار" },
  contentCreation: { id: "content-creation", name: "تولید محتوای کامپیوتری", nameEn: "Computer Content Creation", teacher: "حیدری" },
  production: { id: "production-mgmt", name: "مدیریت تولید", nameEn: "Production Management", teacher: "م. محمدی" },
  mediaLiteracy: { id: "media-literacy", name: "تفکر و سواد رسانه‌ای", nameEn: "Thinking & Media Literacy", teacher: "محمدی" },
  math: { id: "math", name: "ریاضی", nameEn: "Math", teacher: "یوسفی" },
  chemistry: { id: "chemistry", name: "شیمی", nameEn: "Chemistry", teacher: "گل‌محمدی" },
} satisfies Record<string, Subject>;

const S = SUBJECTS;

// ---------- برنامه (شنبه تا چهارشنبه، ۴ زنگ) ----------
export const TIMETABLE: Day[] = [
  {
    id: "sat",
    name: "شنبه",
    short: "ش",
    cells: [{ kind: "class", span: 4, subject: S.webDesign }],
  },
  {
    id: "sun",
    name: "یکشنبه",
    short: "ی",
    cells: [
      { kind: "class", span: 1, subject: S.persian },
      { kind: "class", span: 1, subject: S.humanEnv },
      { kind: "class", span: 1, subject: S.religion },
      { kind: "class", span: 1, subject: S.sports },
    ],
  },
  {
    id: "mon",
    name: "دوشنبه",
    short: "د",
    cells: [
      { kind: "class", span: 1, subject: S.arabic },
      { kind: "class", span: 1, subject: S.entrepreneurship },
      { kind: "class", span: 1, subject: S.history },
      { kind: "class", span: 1, subject: S.english },
    ],
  },
  {
    id: "tue",
    name: "سه‌شنبه",
    short: "س",
    cells: [{ kind: "class", span: 4, subject: S.contentCreation }],
  },
  {
    id: "wed",
    name: "چهارشنبه",
    short: "چ",
    cells: [
      { kind: "class", span: 1, subject: S.production },
      { kind: "class", span: 1, subject: S.mediaLiteracy },
      { kind: "class", span: 1, subject: S.math },
      { kind: "class", span: 1, subject: S.chemistry },
    ],
  },
];

export const PERIOD_COUNT = 4;
export const PERIOD_LABELS = ["زنگ ۱", "زنگ ۲", "زنگ ۳", "زنگ ۴"];

/** دقیقه‌ی شروع/پایان هر زنگ از ۰۸:۰۰ تا ۱۴:۰۰ */
export const PERIOD_TIMES = [
  { start: 8 * 60, end: 9 * 60 + 30 },
  { start: 9 * 60 + 30, end: 11 * 60 },
  { start: 11 * 60, end: 12 * 60 + 30 },
  { start: 12 * 60 + 30, end: 14 * 60 },
];

export const SCHOOL_DAYS = ["sat", "sun", "mon", "tue", "wed"];
