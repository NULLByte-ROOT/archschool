from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


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

SUBJECT_DATA: List[Dict[str, str]] = [
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

WEEKLY_SCHEDULE: Dict[str, Dict[str, Any]] = {
    "sat": {
        "day_id": "sat",
        "day_fa": "شنبه",
        "is_school_day": True,
        "periods": [
            {"period": 1, "subject": "طراحی وب", "subject_id": "web-design", "teacher": "محمدی‌فر", "time": "08:00 تا 09:30"},
            {"period": 2, "subject": "طراحی وب", "subject_id": "web-design", "teacher": "محمدی‌فر", "time": "09:30 تا 11:00"},
            {"period": 3, "subject": "طراحی وب", "subject_id": "web-design", "teacher": "محمدی‌فر", "time": "11:00 تا 12:30"},
            {"period": 4, "subject": "طراحی وب", "subject_id": "web-design", "teacher": "محمدی‌فر", "time": "12:30 تا 14:00"},
        ],
        "note": "کارگاه عملی ۴ زنگ پیوسته طراحی وب",
    },
    "sun": {
        "day_id": "sun",
        "day_fa": "یکشنبه",
        "is_school_day": True,
        "periods": [
            {"period": 1, "subject": "فارسی", "subject_id": "persian", "teacher": "عسگری", "time": "08:00 تا 09:30"},
            {"period": 2, "subject": "انسان و محیط زیست", "subject_id": "human-env", "teacher": "عزیزی", "time": "09:30 تا 11:00"},
            {"period": 3, "subject": "دین و زندگی", "subject_id": "religion", "teacher": "داوودی", "time": "11:00 تا 12:30"},
            {"period": 4, "subject": "تربیت بدنی", "subject_id": "sports", "teacher": "عزیزی", "time": "12:30 تا 14:00"},
        ],
    },
    "mon": {
        "day_id": "mon",
        "day_fa": "دوشنبه",
        "is_school_day": True,
        "periods": [
            {"period": 1, "subject": "عربی", "subject_id": "arabic", "teacher": "داوودی", "time": "08:00 تا 09:30"},
            {"period": 2, "subject": "کارآفرینی", "subject_id": "entrepreneurship", "teacher": "مجیدی", "time": "09:30 تا 11:00"},
            {"period": 3, "subject": "تاریخ", "subject_id": "history", "teacher": "نظم‌ده", "time": "11:00 تا 12:30"},
            {"period": 4, "subject": "زبان انگلیسی", "subject_id": "english", "teacher": "علمدار", "time": "12:30 تا 14:00"},
        ],
    },
    "tue": {
        "day_id": "tue",
        "day_fa": "سه‌شنبه",
        "is_school_day": True,
        "periods": [
            {"period": 1, "subject": "تولید محتوای کامپیوتری", "subject_id": "content-creation", "teacher": "حیدری", "time": "08:00 تا 09:30"},
            {"period": 2, "subject": "تولید محتوای کامپیوتری", "subject_id": "content-creation", "teacher": "حیدری", "time": "09:30 تا 11:00"},
            {"period": 3, "subject": "تولید محتوای کامپیوتری", "subject_id": "content-creation", "teacher": "حیدری", "time": "11:00 تا 12:30"},
            {"period": 4, "subject": "تولید محتوای کامپیوتری", "subject_id": "content-creation", "teacher": "حیدری", "time": "12:30 تا 14:00"},
        ],
        "note": "کارگاه عملی ۴ زنگ پیوسته تولید محتوای کامپیوتری",
    },
    "wed": {
        "day_id": "wed",
        "day_fa": "چهارشنبه",
        "is_school_day": True,
        "periods": [
            {"period": 1, "subject": "مدیریت تولید", "subject_id": "production-mgmt", "teacher": "م. محمدی", "time": "08:00 تا 09:30"},
            {"period": 2, "subject": "تفکر و سواد رسانه‌ای", "subject_id": "media-literacy", "teacher": "محمدی", "time": "09:30 تا 11:00"},
            {"period": 3, "subject": "ریاضی", "subject_id": "math", "teacher": "یوسفی", "time": "11:00 تا 12:30"},
            {"period": 4, "subject": "شیمی", "subject_id": "chemistry", "teacher": "گل‌محمدی", "time": "12:30 تا 14:00"},
        ],
    },
    "thu": {
        "day_id": "thu",
        "day_fa": "پنج‌شنبه",
        "is_school_day": False,
        "periods": [],
        "note": "تعطیل",
    },
    "fri": {
        "day_id": "fri",
        "day_fa": "جمعه",
        "is_school_day": False,
        "periods": [],
        "note": "تعطیل آخر هفته",
    },
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
        rel = f"دیروز موعدش گذشت (منقضی)"
    else:
        rel = f"{abs(day_diff)} روز پیش موعدش گذشت (منقضی)"

    return rel


def resolve_subject(subject_query: str) -> Optional[Dict[str, str]]:
    """Resolve user-entered subject name or ID to subject dict."""
    if not subject_query:
        return None
    clean = subject_query.strip().lower()
    for s in SUBJECT_DATA:
        if clean in s["name"].lower() or clean == s["id"] or clean in s["name_en"].lower():
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
    while True:
        candidate = now + timedelta(days=offset)
        c_key, c_fa = WEEKDAYS_MAP.get(candidate.weekday(), ("", ""))
        if WEEKLY_SCHEDULE.get(c_key, {}).get("is_school_day"):
            next_school_day = c_fa
            next_school_key = c_key
            next_school_schedule = WEEKLY_SCHEDULE[c_key]["periods"]
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
