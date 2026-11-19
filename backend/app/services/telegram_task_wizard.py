import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models
from . import school_knowledge, telegram_bot

logger = logging.getLogger("archschool.telegram_wizard")

SUBTYPES = [
    ("written", "📝 تکلیف نوشتنی", "homework"),
    ("practical", "💻 پروژه عملی", "homework"),
    ("research", "🔬 تحقیق", "homework"),
    ("written_exam", "📋 پرسش کتبی", "exam"),
    ("oral", "🗣 پرسش شفاهی", "exam"),
    ("podmani", "📑 آزمون پودمانی", "exam"),
]

SUBTYPE_MAP = {s[0]: s[1] for s in SUBTYPES}

SUBJECTS = [
    ("web-design", "💻 طراحی وب", "محمدی‌فر"),
    ("math", "📐 ریاضی", "یوسفی"),
    ("chemistry", "🧪 شیمی", "گل‌محمدی"),
    ("content-creation", "🎨 تولید محتوا", "حیدری"),
    ("persian", "📖 فارسی", "عسگری"),
    ("human-env", "🌍 انسان و محیط", "عزیزی"),
    ("entrepreneurship", "💼 کارآفرینی", "مجیدی"),
    ("history", "📜 تاریخ", "نظم‌ده"),
    ("english", "🇬🇧 زبان انگلیسی", "علمدار"),
    ("religion", "🕌 دین و زندگی", "داوودی"),
    ("arabic", "🕋 عربی", "داوودی"),
    ("production-mgmt", "⚙️ مدیریت تولید", "م. محمدی"),
    ("media-literacy", "🧠 تفکر و رسانه", "محمدی"),
    ("sports", "🏃 تربیت بدنی", "عزیزی"),
]

SUBJECT_MAP = {s[0]: (s[1], s[2]) for s in SUBJECTS}

# Timetable class day for each subject (Saturday=0, Sunday=1, Monday=2, Tuesday=3, Wednesday=4)
SUBJECT_DAY_INDEX: Dict[str, int] = {
    "web-design": 0,
    "persian": 1,
    "human-env": 1,
    "religion": 1,
    "sports": 1,
    "arabic": 2,
    "entrepreneurship": 2,
    "history": 2,
    "english": 2,
    "content-creation": 3,
    "production-mgmt": 4,
    "media-literacy": 4,
    "math": 4,
    "chemistry": 4,
}


def get_start_of_class_week(now_iran: datetime) -> datetime:
    """Saturday 00:00:00 of the current class week in Iran time."""
    class_idx = (now_iran.weekday() + 2) % 7
    sat_date = (now_iran - timedelta(days=class_idx)).date()
    return datetime(sat_date.year, sat_date.month, sat_date.day)


def calculate_due_date(week_offset: int, day_index: int, now_iran: Optional[datetime] = None) -> datetime:
    """Returns UTC datetime corresponding to 23:59:00 Iran time on the chosen week & day."""
    now_iran = now_iran or school_knowledge.get_iran_now()
    sat = get_start_of_class_week(now_iran)
    target = sat + timedelta(days=week_offset * 7 + day_index)
    iran_due = datetime(target.year, target.month, target.day, 23, 59, 0)
    utc_due = iran_due - timedelta(hours=3.5)
    return utc_due


def build_step1_keyboard() -> Dict[str, Any]:
    """Step 1: Choose assignment topic/subtype."""
    buttons: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    for code, label, _ in SUBTYPES:
        row.append({"text": label, "callback_data": f"wiz:s2:{code}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([{"text": "❌ انصراف", "callback_data": "wiz:cancel"}])
    return {"inline_keyboard": buttons}


def build_step2_keyboard(subtype: str) -> Dict[str, Any]:
    """Step 2: Choose course/subject."""
    buttons: List[List[Dict[str, str]]] = []
    row: List[Dict[str, str]] = []
    for s_id, s_name, _ in SUBJECTS:
        row.append({"text": s_name, "callback_data": f"wiz:s3:{subtype}:{s_id}"})
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        {"text": "🔙 مرحله قبل", "callback_data": "wiz:s1"},
        {"text": "❌ انصراف", "callback_data": "wiz:cancel"},
    ])
    return {"inline_keyboard": buttons}


def build_step3_keyboard(subtype: str, subject_id: str) -> Tuple[str, Dict[str, Any]]:
    """Step 3: Choose proposed deadline presets (mirrors the mobile app logic)."""
    now_iran = school_knowledge.get_iran_now()
    current_class_idx = (now_iran.weekday() + 2) % 7
    subject_day = SUBJECT_DAY_INDEX.get(subject_id, 0)

    # In mobile app: upcoming is this week (offset 0) if day is still ahead, else next week (offset 1)
    upcoming_offset = 0 if subject_day > current_class_idx else 1

    # Preset 0: The upcoming class date
    due_p0 = calculate_due_date(upcoming_offset, subject_day, now_iran)
    label_p0 = school_knowledge.format_iran_datetime(due_p0).replace(" ساعت 23:59", " (۲۳:۵۹)")

    # Preset 1: 1 week after that
    due_p1 = calculate_due_date(upcoming_offset + 1, subject_day, now_iran)
    label_p1 = school_knowledge.format_iran_datetime(due_p1).replace(" ساعت 23:59", " (۲۳:۵۹)")

    # Preset 2: 2 weeks after that
    due_p2 = calculate_due_date(upcoming_offset + 2, subject_day, now_iran)
    label_p2 = school_knowledge.format_iran_datetime(due_p2).replace(" ساعت 23:59", " (۲۳:۵۹)")

    # Preset 3: Saturday next week
    due_p3 = calculate_due_date(1, 0, now_iran)
    label_p3 = "شنبه هفته آینده (۲۳:۵۹)"

    sub_label = SUBTYPE_MAP.get(subtype, "تکلیف")
    subj_name, teacher = SUBJECT_MAP.get(subject_id, ("عمومی", ""))
    clean_sub = sub_label.split(" ", 1)[-1]
    clean_subj = subj_name.split(" ", 1)[-1]
    auto_title = f"{clean_sub} {clean_subj}"

    text = (
        f"📋 <b>افزودن تکلیف جدید به سامانه</b>\n\n"
        f"موضوع: <b>{clean_sub}</b> ✅\n"
        f"درس: <b>{clean_subj}</b> (استاد {teacher}) ✅\n"
        f"عنوان پیش‌فرض: <b>{auto_title}</b>\n\n"
        f"<b>گام ۳ از ۳:</b> مهلت تحویل پیشنهادی را انتخاب کنید:\n"
        f"<i>(کپشن و عنوان دقیقاً مثل اپلیکیشن به صورت خودکار ثبت می‌شود)</i>"
    )

    iso_p0 = due_p0.strftime("%Y%m%d%H%M")
    iso_p1 = due_p1.strftime("%Y%m%d%H%M")
    iso_p2 = due_p2.strftime("%Y%m%d%H%M")
    iso_p3 = due_p3.strftime("%Y%m%d%H%M")

    buttons = [
        [{"text": f"✦ پیشنهادی درس: {label_p0}", "callback_data": f"wiz:save:{subtype}:{subject_id}:{iso_p0}"}],
        [{"text": f"📅 {label_p1}", "callback_data": f"wiz:save:{subtype}:{subject_id}:{iso_p1}"}],
        [{"text": f"📅 {label_p2}", "callback_data": f"wiz:save:{subtype}:{subject_id}:{iso_p2}"}],
        [{"text": f"📅 {label_p3}", "callback_data": f"wiz:save:{subtype}:{subject_id}:{iso_p3}"}],
        [{"text": "⚪ بدون مهلت تحویل", "callback_data": f"wiz:save:{subtype}:{subject_id}:none"}],
        [
            {"text": "🔙 مرحله قبل", "callback_data": f"wiz:s2:{subtype}"},
            {"text": "❌ انصراف", "callback_data": "wiz:cancel"},
        ],
    ]

    return text, {"inline_keyboard": buttons}


async def start_add_task_wizard(
    token: str,
    chat_id: int | str,
    user: Optional[models.User],
    reply_to_message_id: Optional[int] = None,
) -> bool:
    """Send Step 1 of the assignment creation wizard."""
    if not user or not (user.is_admin or user.role in ("admin", "owner")):
        msg = (
            "⚠️ <b>دسترسی مدیریتی لازم است</b>\n\n"
            "فقط مدیران و مالک مدرسه (Admin / Owner) در سامانه ArchSchool مجاز به افزودن تکلیف هستند."
        )
        return await telegram_bot.send_telegram_message(
            token, chat_id, msg, reply_to_message_id=reply_to_message_id
        )

    text = (
        "📋 <b>افزودن تکلیف جدید به سامانه</b>\n\n"
        "<b>گام ۱ از ۳:</b> موضوع و نوع تکلیف را از گزینه‌های زیر انتخاب کنید:"
    )
    kb = build_step1_keyboard()
    return await telegram_bot.send_telegram_message(
        token, chat_id, text, reply_markup=kb, reply_to_message_id=reply_to_message_id
    )


async def handle_wizard_callback(
    db: Session,
    user: Optional[models.User],
    data: str,
    chat_id: int,
    message_id: int,
    query_id: str,
    token: str,
) -> bool:
    """Process clicks on wizard inline buttons."""
    # 1. Cancel
    if data == "wiz:cancel":
        await telegram_bot.answer_callback_query(token, query_id, text="عملیات لغو شد.")
        return await telegram_bot.edit_telegram_message(
            token, chat_id, message_id, "❌ عملیات افزودن تکلیف لغو شد."
        )

    # Check permission
    if not user or not (user.is_admin or user.role in ("admin", "owner")):
        await telegram_bot.answer_callback_query(
            token, query_id, text="⚠️ فقط ادمین یا مالک مدرسه مجاز به افزودن تکلیف هستند.", show_alert=True
        )
        return True

    # 2. Step 1 (Back to step 1)
    if data == "wiz:s1":
        await telegram_bot.answer_callback_query(token, query_id)
        text = (
            "📋 <b>افزودن تکلیف جدید به سامانه</b>\n\n"
            "<b>گام ۱ از ۳:</b> موضوع و نوع تکلیف را انتخاب کنید:"
        )
        return await telegram_bot.edit_telegram_message(
            token, chat_id, message_id, text, reply_markup=build_step1_keyboard()
        )

    # 3. Step 2 (Subtype selected) -> Choose subject
    if data.startswith("wiz:s2:"):
        subtype = data.split(":", 2)[2]
        await telegram_bot.answer_callback_query(token, query_id)
        sub_label = SUBTYPE_MAP.get(subtype, "تکلیف").split(" ", 1)[-1]
        text = (
            f"📋 <b>افزودن تکلیف جدید به سامانه</b>\n"
            f"موضوع: <b>{sub_label}</b> ✅\n\n"
            f"<b>گام ۲ از ۳:</b> درس مورد نظر را انتخاب کنید:"
        )
        return await telegram_bot.edit_telegram_message(
            token, chat_id, message_id, text, reply_markup=build_step2_keyboard(subtype)
        )

    # 4. Step 3 (Subject selected) -> Choose due date
    if data.startswith("wiz:s3:"):
        parts = data.split(":")
        subtype = parts[2]
        subject_id = parts[3]
        await telegram_bot.answer_callback_query(token, query_id)
        text, kb = build_step3_keyboard(subtype, subject_id)
        return await telegram_bot.edit_telegram_message(
            token, chat_id, message_id, text, reply_markup=kb
        )

    # 5. Final Save
    if data.startswith("wiz:save:"):
        parts = data.split(":")
        subtype = parts[2]
        subject_id = parts[3]
        due_iso = parts[4]

        due_dt = None
        due_display = "بدون مهلت تحویل"
        if due_iso != "none":
            try:
                due_dt = datetime.strptime(due_iso, "%Y%m%d%H%M")
                due_display = school_knowledge.format_iran_datetime(due_dt)
            except Exception:
                due_dt = None

        sub_label = SUBTYPE_MAP.get(subtype, "تکلیف")
        subj_name, teacher = SUBJECT_MAP.get(subject_id, ("عمومی", ""))
        clean_sub = sub_label.split(" ", 1)[-1]
        clean_subj = subj_name.split(" ", 1)[-1]
        auto_title = f"{clean_sub} {clean_subj}"

        new_assignment = models.Assignment(
            title=auto_title,
            description="",
            due_date=due_dt,
            subject_id=subject_id,
            category=clean_subj,
            course=clean_subj,
            subtype=subtype,
            owner_id=user.id,
            creator_id=user.id,
        )
        db.add(new_assignment)
        # Reward creator with +1 daily activity point
        from ..routers.assignments import _record_daily_activity
        _record_daily_activity(db, user.id, datetime.utcnow(), +1)
        db.commit()
        db.refresh(new_assignment)

        await telegram_bot.answer_callback_query(
            token, query_id, text="🎉 تکلیف با موفقیت ثبت شد!"
        )

        confirm_msg = (
            f"🎉 <b>تکلیف جدید با موفقیت در سامانه ثبت شد!</b>\n\n"
            f"📌 عنوان: <b>{auto_title}</b>\n"
            f"📚 درس: <b>{clean_subj}</b> (استاد {teacher})\n"
            f"⏰ مهلت تحویل: <b>{due_display}</b>\n"
            f"👤 ثبت‌کننده: <b>{user.username}</b> (+۱ امتیاز فعالیت روزانه به شما تعلق گرفت 🔥)\n\n"
            f"<i>برای مشاهده و پیوست تصاویر به اپلیکیشن ArchSchool مراجعه کنید.</i>"
        )
        return await telegram_bot.edit_telegram_message(
            token, chat_id, message_id, confirm_msg
        )

    return False


async def handle_toggle_callback(
    db: Session,
    user: Optional[models.User],
    data: str,
    chat_id: int,
    message_id: int,
    query_id: str,
    token: str,
) -> bool:
    """Handle instant toggling of assignments via inline buttons."""
    if not user:
        await telegram_bot.answer_callback_query(
            token, query_id, text="ابتدا حسابت رو با ارسال کد اتصال وصل کن!", show_alert=True
        )
        return True

    assignment_id_str = data.replace("task_toggle:", "").strip()
    from . import ai_agent
    res = ai_agent.execute_tool(
        "toggle_assignment_completion",
        {"action": "complete", "scope": "single", "assignment_query": assignment_id_str},
        db,
        user,
    )

    if res.get("success"):
        titles = ", ".join(res.get("modified_titles", []))
        pct = res.get("new_completion_percentage", 0)
        streak = res.get("current_streak", 0)
        toast = f"✅ تکلیف {titles} تیک خورد!\nپیشرفت: {pct}٪ | استریک: {streak} روز"
        await telegram_bot.answer_callback_query(token, query_id, text=toast, show_alert=True)
        # Edit the message to reflect success
        updated_text = (
            f"✅ <b>تکلیف {titles} با موفقیت تیک خورد و ثبت شد!</b> 🔥\n\n"
            f"📊 درصد کل تکالیف انجام‌شده شما: <b>{pct}٪</b>\n"
            f"🔥 استریک جاری شما: <b>{streak} روز</b>\n"
            f"<i>برای مشاهده نمودارها و لیدربورد به اپلیکیشن سر بزنید.</i>"
        )
        await telegram_bot.edit_telegram_message(token, chat_id, message_id, updated_text)
        return True
    else:
        err = res.get("error", "خطا در تیک زدن تکلیف")
        await telegram_bot.answer_callback_query(token, query_id, text=f"❌ {err}", show_alert=True)
        return True
