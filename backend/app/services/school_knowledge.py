from datetime import datetime, timedelta
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("archschool.school_knowledge")

CONFIG_PATH = Path(os.environ.get("SCHOOL_CONFIG_PATH") or (Path(__file__).resolve().parent.parent / "school_config.json"))


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    """Convert Gregorian (gy, gm, gd) to Jalali (jy, jm, jd)."""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy if gm > 2 else gy - 1
    days = (
        365 * gy
        + (gy2 + 4) // 4
        - (gy2 + 100) // 100
        + (gy2 + 400) // 400
        - 80
        + gd
        + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


PERSIAN_MONTHS = [
    "",
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]

# Mapping Python weekday (Mon=0..Sun=6) to (day_id, Persian_day_name)
WEEKDAYS_MAP: Dict[int, Tuple[str, str]] = {
    5: ("sat", "شنبه"),
    6: ("sun", "یکشنبه"),
    0: ("mon", "دوشنبه"),
    1: ("tue", "سه‌شنبه"),
    2: ("wed", "چهارشنبه"),
    3: ("thu", "پنج‌شنبه"),
    4: ("fri", "جمعه"),
}

DAY_LOOKUP = {
    "sat": "sat", "شنبه": "sat",
    "sun": "sun", "یکشنبه": "sun",
    "mon": "mon", "دوشنبه": "mon",
    "tue": "tue", "سه شنبه": "tue", "سه‌شنبه": "tue",
    "wed": "wed", "چهارشنبه": "wed",
    "thu": "thu", "پنج شنبه": "thu", "پنج‌شنبه": "thu",
    "fri": "fri", "جمعه": "fri",
}

# In-memory storage dynamically initialized from school_config.json
SUBJECT_DATA: List[Dict[str, str]] = []
CATEGORY_DATA: List[Dict[str, Any]] = []
SUBJECT_BY_ID: Dict[str, Dict[str, str]] = {}
SUBJECT_BY_NAME: Dict[str, Dict[str, str]] = {}
WEEKLY_SCHEDULE: Dict[str, Dict[str, Any]] = {}


def load_school_config() -> Dict[str, Any]:
    """Load school subjects, categories, and schedule from school_config.json."""
    global SUBJECT_DATA, CATEGORY_DATA, SUBJECT_BY_ID, SUBJECT_BY_NAME, WEEKLY_SCHEDULE

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            SUBJECT_DATA = data.get("subjects", [])
            CATEGORY_DATA = data.get("categories", [])
            WEEKLY_SCHEDULE = data.get("weekly_schedule", {})
        except Exception as exc:
            logger.error("Failed to read %s: %s", CONFIG_PATH, exc)

    if not SUBJECT_DATA:
        # Built-in fallback
        SUBJECT_DATA = [
            {"id": "web-design", "name": "طراحی وب", "name_en": "Web Design", "teacher": "محمدی‌فر"},
            {"id": "persian", "name": "فارسی", "name_en": "Persian", "teacher": "عسگری"},
            {"id": "human-env", "name": "انسان و محیط زیست", "name_en": "Human & Environment", "teacher": "عزیزی"},
            {"id": "religion", "name": "دین و زندگی", "name_en": "Religion", "teacher": "داوودی"},
            {"id": "sports", "name": "تربیت بدنی", "name_en": "Sports", "teacher": "عزیزی"},
            {"id": "arabic", "name": "عربی", "name_en": "Arabic", "teacher": "داوودی"},
            {"id": "entrepreneurship", "name": "کارآفرینی", "name_en": "Entrepreneurship", "teacher": "مجیدی"},
            {"id": "history", "name": "تاریخ", "name_en": "History", "teacher": "نظم‌ده"},
            {"id": "english", "name": "زبان انگلیسی", "name_en": "English", "teacher": "علمدار"},
            {"id": "content-creation", "name": "تولید محتوای کامپیوتری", "name_en": "Computer Content Creation", "teacher": "حیدری"},
            {"id": "production-mgmt", "name": "مدیریت تولید", "name_en": "Production Management", "teacher": "م. محمدی"},
            {"id": "media-literacy", "name": "تفکر و سواد رسانه‌ای", "name_en": "Thinking & Media Literacy", "teacher": "محمدی"},
            {"id": "math", "name": "ریاضی", "name_en": "Math", "teacher": "یوسفی"},
            {"id": "chemistry", "name": "شیمی", "name_en": "Chemistry", "teacher": "گل‌محمدی"},
        ]

    SUBJECT_BY_ID = {s["id"]: s for s in SUBJECT_DATA}
    SUBJECT_BY_NAME = {s["name"]: s for s in SUBJECT_DATA}

    return {
        "subjects": SUBJECT_DATA,
        "categories": CATEGORY_DATA,
        "weekly_schedule": WEEKLY_SCHEDULE,
    }


def save_school_config(new_config: Dict[str, Any]) -> Dict[str, Any]:
    """Save updated subjects, categories, and schedule to JSON and reload in-memory state."""
    global SUBJECT_DATA, CATEGORY_DATA, SUBJECT_BY_ID, SUBJECT_BY_NAME, WEEKLY_SCHEDULE

    if "subjects" in new_config:
        SUBJECT_DATA = new_config["subjects"]
    if "categories" in new_config:
        CATEGORY_DATA = new_config["categories"]
    if "weekly_schedule" in new_config:
        WEEKLY_SCHEDULE = new_config["weekly_schedule"]

    SUBJECT_BY_ID = {s["id"]: s for s in SUBJECT_DATA}
    SUBJECT_BY_NAME = {s["name"]: s for s in SUBJECT_DATA}

    full_payload = {
        "subjects": SUBJECT_DATA,
        "categories": CATEGORY_DATA,
        "weekly_schedule": WEEKLY_SCHEDULE,
    }

    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(full_payload, f, ensure_ascii=False, indent=2)
        logger.info("Successfully updated school config at %s", CONFIG_PATH)
    except Exception as exc:
        logger.error("Failed to write %s: %s", CONFIG_PATH, exc)
        raise

    return full_payload


# Initialize on import
load_school_config()


def get_iran_now() -> datetime:
    """Current naive datetime in Iran standard time (UTC+03:30)."""
    return datetime.utcnow() + timedelta(hours=3.5)


def format_iran_datetime(dt: datetime) -> str:
    """Return formatted Persian calendar string for a UTC datetime."""
    iran_dt = dt + timedelta(hours=3.5)
    jy, jm, jd = gregorian_to_jalali(iran_dt.year, iran_dt.month, iran_dt.day)
    _, day_fa = WEEKDAYS_MAP.get(iran_dt.weekday(), ("", ""))
    month_fa = PERSIAN_MONTHS[jm] if 1 <= jm <= 12 else ""
    return f"{day_fa} {jd} {month_fa} {jy} ساعت {iran_dt.strftime('%H:%M')}"


def format_due_date_relative(due_utc: Optional[datetime], now_iran: Optional[datetime] = None) -> str:
    """Format due date with relative Persian description."""
    if not due_utc:
        return "بدون موعد زمانی خاص"

    now = now_iran or get_iran_now()
    due_iran = due_utc + timedelta(hours=3.5)

    jy, jm, jd = gregorian_to_jalali(due_iran.year, due_iran.month, due_iran.day)
    _, day_fa = WEEKDAYS_MAP.get(due_iran.weekday(), ("", ""))
    month_fa = PERSIAN_MONTHS[jm] if 1 <= jm <= 12 else ""
    time_str = due_iran.strftime("%H:%M")

    # Difference in calendar days
    today_date = now.date()
    due_date = due_iran.date()
    day_diff = (due_date - today_date).days

    if day_diff == 0:
        rel = f"امروز ({day_fa}) تا ساعت {time_str}"
    elif day_diff == 1:
        rel = f"فردا ({day_fa}) تا ساعت {time_str}"
    elif day_diff == 2:
        rel = f"پس‌فردا ({day_fa}) تا ساعت {time_str}"
    elif day_diff > 2:
        rel = f"{day_fa} {jd} {month_fa} تا ساعت {time_str} ({day_diff} روز دیگر)"
    elif day_diff == -1:
        rel = "دیروز موعدش گذشت (منقضی)"
    else:
        rel = f"{abs(day_diff)} روز پیش موعدش گذشت (منقضی)"

    return rel


def resolve_target_day_bounds(
    target_day: Optional[str] = None,
) -> Tuple[datetime, datetime, str, str]:
    """Resolve a user-specified day query (e.g. 'امروز', 'فردا', 'شنبه') into UTC start/end datetime bounds,
    Persian day label, and weekday key.
    """
    now_iran = get_iran_now()
    clean = (target_day or "").strip().lower()

    target_iran_date = now_iran.date()
    day_label_prefix = ""

    if not clean or "امروز" in clean:
        target_iran_date = now_iran.date()
        day_label_prefix = "امروز"
    elif "پس‌فردا" in clean or "پس فردا" in clean:
        target_iran_date = now_iran.date() + timedelta(days=2)
        day_label_prefix = "پس‌فردا"
    elif "فردا" in clean:
        target_iran_date = now_iran.date() + timedelta(days=1)
        day_label_prefix = "فردا"
    else:
        day_map = {
            "شنبه": 5,
            "یکشنبه": 6,
            "دوشنبه": 0,
            "سه‌شنبه": 1,
            "سه شنبه": 1,
            "چهارشنبه": 2,
            "پنج‌شنبه": 3,
            "پنج شنبه": 3,
            "جمعه": 4,
        }
        matched_target_weekday = None
        for name, wd in day_map.items():
            if name in clean:
                matched_target_weekday = wd
                break

        if matched_target_weekday is not None:
            current_weekday = now_iran.weekday()
            days_ahead = (matched_target_weekday - current_weekday) % 7
            target_iran_date = now_iran.date() + timedelta(days=days_ahead)
            if days_ahead == 0:
                day_label_prefix = "امروز"
            elif days_ahead == 1:
                day_label_prefix = "فردا"
            elif days_ahead == 2:
                day_label_prefix = "پس‌فردا"

    iran_start = datetime.combine(target_iran_date, datetime.min.time())
    iran_end = datetime.combine(target_iran_date, datetime.max.time())

    start_utc = iran_start - timedelta(hours=3.5)
    end_utc = iran_end - timedelta(hours=3.5)

    jy, jm, jd = gregorian_to_jalali(target_iran_date.year, target_iran_date.month, target_iran_date.day)
    d_key, d_fa = WEEKDAYS_MAP.get(target_iran_date.weekday(), ("sat", "شنبه"))
    m_fa = PERSIAN_MONTHS[jm] if 1 <= jm <= 12 else ""

    if day_label_prefix:
        full_label = f"{day_label_prefix} ({d_fa}، {jd} {m_fa})"
    else:
        full_label = f"{d_fa} ({jd} {m_fa})"

    return start_utc, end_utc, full_label, d_key


def resolve_subject(subject_query: str) -> Optional[Dict[str, str]]:
    """Resolve user-entered subject name or ID to subject dict."""
    if not subject_query:
        return None
    clean = subject_query.strip().lower()
    for s in SUBJECT_DATA:
        if clean in s["name"].lower() or clean == s.get("id", "").lower() or clean in s.get("name_en", "").lower():
            return s
        if s["name"].lower() in clean:
            return s
    return None


def get_current_school_status(now: Optional[datetime] = None) -> Dict[str, Any]:
    """Calculate current day, week progress, school period, and next school day."""
    now = now or get_iran_now()
    day_key, day_fa = WEEKDAYS_MAP.get(now.weekday(), ("thu", "پنج‌شنبه"))
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    month_fa = PERSIAN_MONTHS[jm] if 1 <= jm <= 12 else ""
    time_str = now.strftime("%H:%M")

    # Tomorrow
    tomorrow = now + timedelta(days=1)
    t_key, t_fa = WEEKDAYS_MAP.get(tomorrow.weekday(), ("", ""))

    # Next school day (Sat..Wed)
    offset = 1
    next_school_day = "شنبه"
    next_school_schedule = []
    while offset <= 7:
        candidate = now + timedelta(days=offset)
        c_key, c_fa = WEEKDAYS_MAP.get(candidate.weekday(), ("", ""))
        if WEEKLY_SCHEDULE.get(c_key, {}).get("is_school_day"):
            next_school_day = c_fa
            next_school_schedule = WEEKLY_SCHEDULE[c_key].get("periods", [])
            break
        offset += 1

    # Check school bell for today if school day
    is_school_day = WEEKLY_SCHEDULE.get(day_key, {}).get("is_school_day", False)
    bell_status = "خارج از روزهای مدرسه حضوری (ثبت و تحویل تکالیف در منزل ۲۴ ساعته فعال است)"
    current_period = None

    if is_school_day:
        minutes = now.hour * 60 + now.minute
        # 08:00 (480) to 14:00 (840)
        if minutes < 480:
            bell_status = "قبل از شروع کلاس‌های حضوری (کلاس‌ها ساعت ۰۸:۰۰ شروع می‌شوند)"
        elif 480 <= minutes < 570:
            bell_status = "زنگ اول (۰۸:۰۰ تا ۰۹:۳۰)"
            current_period = 1
        elif 570 <= minutes < 660:
            bell_status = "زنگ دوم (۰۹:۳۰ تا ۱۱:۰۰)"
            current_period = 2
        elif 660 <= minutes < 750:
            bell_status = "زنگ سوم (۱۱:۰۰ تا ۱۲:۳۰)"
            current_period = 3
        elif 750 <= minutes < 840:
            bell_status = "زنگ چهارم (۱۲:۳۰ تا ۱۴:۰۰)"
            current_period = 4
        else:
            bell_status = "کلاس‌های حضوری امروز به پایان رسیده است (ثبت و تحویل تکالیف در منزل فعال است)"

    return {
        "current_time": time_str,
        "today_fa": f"{day_fa} {jd} {month_fa} {jy}",
        "day_fa": day_fa,
        "day_key": day_key,
        "is_school_day": is_school_day,
        "bell_status": bell_status,
        "current_period": current_period,
        "today_schedule": WEEKLY_SCHEDULE.get(day_key, {}).get("periods", []),
        "tomorrow_fa": t_fa,
        "tomorrow_schedule": WEEKLY_SCHEDULE.get(t_key, {}).get("periods", []),
        "next_school_day": next_school_day,
        "next_school_schedule": next_school_schedule,
    }


def get_school_knowledge_prompt() -> str:
    """Dynamic context describing current modular subjects, teachers, and schedule."""
    lines = ["📚 لیست دروس، موضوعات و دبیران کلاس (کاملاً ماژولار و به‌روزشده):"]
    for s in SUBJECT_DATA:
        teacher = s.get("teacher", "نامشخص")
        name = s.get("name", "")
        lines.append(f"- درس «{name}» (دبیر: {teacher})")

    lines.append("\n🗓 برنامه هفتگی کلاس‌ها:")
    for d_key in ("sat", "sun", "mon", "tue", "wed"):
        day_info = WEEKLY_SCHEDULE.get(d_key, {})
        d_name = day_info.get("day_fa", d_key)
        periods = day_info.get("periods", [])
        period_desc = ", ".join(f"زنگ {p.get('period')}: {p.get('subject')} ({p.get('teacher')})" for p in periods)
        lines.append(f"- {d_name}: {period_desc if periods else 'تعطیل'}")

    return "\n".join(lines)
