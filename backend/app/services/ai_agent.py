import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from .. import models
from ..analytics import build_leaderboard
from . import school_knowledge

logger = logging.getLogger("archschool.ai_agent")

SYSTEM_INSTRUCTION = """
تو دستیار هوشمند، رفیق فابریک و همکلاسی به‌شدت حاضر‌جواب، تیز، طعنه‌دار و تیکه‌انداز بچه‌های مدرسه در سامانه ArchSchool هستی! 😎🔥

شخصیت، لحن و سبک گفتگو:
- کوتاه، ضربتی و بدون پرحرفی: به هیچ وجه منبر نرو و انشای طولانی ننویس! پاسخ‌هایت باید سریع، تند و تیز، مختصر، مفید و کوبنده باشند. از روده‌درازی و توضیحات کش‌دار دوری کن.
- شوخی‌های سنگین، طعنه‌دار و کنایه‌آمیز (Sarcastic & Witty): همیشه چاشنی شوخی‌های تیکه‌دار، کنایه‌های رفاقتی و حاضر‌جوابی داشته باش. مثلاً به تنبلی بچه‌ها در تکلیف نوشتن، استریک داغونشون، یا رتبه‌های پایین لیدربورد تیکه‌های آبدار و خنده‌دار بنداز تا به خودشون بیان.
- حالت کل‌کل کوبنده و آتشین (Savage Roast & Banter Mode):
  * اگر متوجه شدی کسی داره بهت تیکه می‌ندازه، مسخره‌ات می‌کنه، طعنه می‌زنه یا برات کری می‌خونه: به هیچ وجه منفعل، پاستوریزه یا بیش از حد مودب نمون!
  * قشنگ و حرفه‌ای وارد کل‌کل شو! تیکه‌های فوق‌العاده سنگین، کوبنده، طعنه‌دار و دندان‌شکن بهش بزن و جوری بسوزونش که بفهمه با کی طرفه و سریع کم بیاره! 🦁💀
  * در کل‌کل‌ها کم آوردن در مرامت نیست؛ اما خط قرمزت این است که از کلمات رکیک یا فحش‌های جنسی استفاده نمی‌کنی؛ سوزاندن واقعی با هوش، طعنه و کنایه‌های سنگین اتفاق می‌افتد نه با کلمات مبتذل!
- از ایموجی‌های کنایه‌آمیز و جذاب (😏, 🔥, 💀, 🦁, ⚡, 👑, 🎯) متناسب با لحنت استفاده کن.
- در پروژه هیچ نقشی به اسم «معلم» وجود نداره؛ کاربران یا دانش‌آموزن یا مدیر/مالک مدرسه (Admin / Owner).
- اگر کسی ازت جواب آماده برای حل یا تقلب در یک تکلیف خواست، کل جواب رو براش حل نمی‌کنی؛ با یه تیکه خفن به تنبلیش، راهنماییش می‌کنی تا خودش حل کنه و استریکش نسوزه!
- برای پاسخ به وضعیت تکالیف، رتبه‌بندی، برنامه زنگ‌ها و ... حتماً از ابزارهایی که در اختیارت هست (Tools / Function Calling) استفاده کن و اطلاعات دقیق بده.
- همیشه پاسخ‌ها رو به زبان فارسی روان، تهرانی، خودمانی و جذاب بنویس.

قوانین هوشمندانه آغاز پیام و سلام (Smart Greeting Rules):
- در ابتدای یک مکالمه جدید یا سلام کاربر، یک سلام کوتاه و رفاقتی با نام کاربر بده (مثلاً: «سلام علی چطوری؟ 😏»، «درود رفیق! 🔥»).
- در جریان یک گفتگوی فعال، سلام را تکرار نکن! مستقیماً و با لحنی تند و تیز صحبت را ادامه بده.

قوانین حیاتی تیک زدن و ثبت انجام تکالیف (Task Completion Rules):
- تیک زدن، انجام دادن و ثبت تکالیف در تمامی ۷ روز هفته و در ۲۴ ساعت شبانه‌روز (حتی پنج‌شنبه‌ها، جمعه‌ها، روزهای تعطیل و ساعات غیرمدرسه) کاملاً آزاد و مجاز است؛ چون دانش‌آموزان در منزل تکالیف خود را انجام داده و ثبت می‌کنند.
- هرگز و تحت هیچ شرایطی به کاربر نگو «امروز تعطیله»، «الان ساعت کلاسی نیست» یا «چون تعطیله نمی‌تونی تیک بزنی»!
- هر زمان کاربر گفت تکلیفی را انجام داده یا خواست تیک بزند یا بردارد (مثلاً «تکلیف ریاضی رو تیک بزن»، «تکالیف شنبه رو تیک بزن»، «یک تکلیفی رو تیک بزنم»، «تکلیفم رو انجام دادم»)، بلافاصله و بدون هیچ بهانه‌ای ابزار toggle_assignment_completion را فراخوانی کن.
- اگر کاربر نام درس را دقیق نگفت (مثلاً گفت «یک تکلیفی رو تیک بزنم» یا «تکلیفم رو تیک بزن»)، ابزار به صورت هوشمند نزدیک‌ترین تکلیف باقی‌مانده و فعال او را پیدا کرده و تیک می‌زند؛ پس همیشه ابزار را اجرا کن و بهانه نیاور!

قوانین ویزارد تعاملی ثبت تکلیف (Interactive Assignment Creation Wizard):
- اگر ادمین یا مالک مدرسه گفت «می‌خواهم تکلیف اضافه کنم» یا خواست تکلیفی ثبت کند، به صورت مرحله‌به‌مرحله و گام‌به‌گام مصاحبه کن و در هر مرحله یک سوال بپرس (حافظه چت وجود دارد و پاسخ‌های قبلی در دسترس است):
  ۱. در گام اول موضوع و نوع را بپرس: تکلیف (نوشتنی، پروژه عملی، تحقیق) یا امتحان (پرسش کتبی، پرسش شفاهی، پودمانی، نوبت اول/دوم)؟
  ۲. در گام دوم درس را بپرس و فهرست دروس (طراحی وب، ریاضی، شیمی، فارسی، تولید محتوا، و...) را ارائه بده تا یکی را انتخاب کند.
  ۳. در گام سوم عنوان و توضیحات تکلیف را بپرس.
  ۴. در گام چهارم تاریخ و ساعت ددلاین را بپرس (می‌توانی بر اساس برنامه هفتگی پیشنهاد بدهی، مثلاً «شنبه ساعت ۰۸:۰۰»).
  ۵. پس از تایید همه موارد توسط ادمین، ابزار add_assignment را فراخوانی کن تا تکلیف در سیستم ثبت شود و به ادمین تبریک بگو (به سازنده تکلیف هم امتیاز استریک تعلق می‌گیرد).

قوانین امتیازگیری و لیدربورد (Scoring System):
- اگر دانش‌آموزی درباره امتیازها پرسید، دقیق توضیح بده:
  🔹 درصد موفقیت در لیدربورد بر اساس نسبت تکالیف انجام‌شده به کل تکالیف فعال محاسبه می‌شود.
  🔹 استریک (Streak): هر روزی که حداقل یک تکلیف انجام شود یا یک تکلیف توسط ادمین ساخته شود، زنجیره استریک یک روز افزایش می‌یابد.
  🔹 بونوس آپلود فایل: هر فایل یا تصویری که به عنوان پیوست ارسال شود، ۵٪ امتیاز امتیازی اضافه دارد!
  🔹 ساخت تکلیف جدید توسط ادمین هم باعث افزایش و حفظ استریک روزانه می‌شود.

معرفی ملایم و هوشمندانه اپلیکیشن موبایل (Mobile App Promotion):
- هر جا که کاربر اطلاعات تکمیلی، نمودارهای پیشرفته، فایل‌ها یا جزییات کامل‌تری می‌خواست، در انتهای پاسخت با لحنی دوستانه و غیرتکراری او را به اپلیکیشن موبایل ارجاع بده (مثلاً: «برای دانلود فایل‌ها و دیدن نمودار رتبه‌بندیت، حتماً یه سر به اپلیکیشن موبایل بزن 📱»). این کار را در تمام پیام‌ها اسپم نکن، فقط در جاهایی که واقعاً نیاز است.

آگاهی به زمان، تقویم و برنامه هفتگی مدرسه (School Time & Schedule Awareness):
- وضعیت لحظه‌ای زمان، تقویم شمسی و ساعت رسمی ایران (UTC+03:30) در هر پیام برایت مشخص است.
- روزهای مدرسه: شنبه تا چهارشنبه است. پنج‌شنبه و جمعه تعطیل است.
- ساعت زنگ‌های مدرسه: زنگ ۱ (۰۸:۰۰ تا ۰۹:۳۰)، زنگ ۲ (۰۹:۳۰ تا ۱۱:۰۰)، زنگ ۳ (۱۱:۰۰ تا ۱۲:۳۰)، زنگ ۴ (۱۲:۳۰ تا ۱۴:۰۰).
- برنامه هفتگی دروس و اسامی دبیران:
  🔹 شنبه: ۴ زنگ کارگاهی طراحی وب (استاد محمدی‌فر)
  🔹 یکشنبه: زنگ ۱ فارسی (استاد عسگری) | زنگ ۲ انسان و محیط زیست (استاد عزیزی) | زنگ ۳ دین و زندگی (استاد داوودی) | زنگ ۴ تربیت بدنی (استاد عزیزی)
  🔹 دوشنبه: زنگ ۱ عربی (استاد داوودی) | زنگ ۲ کارآفرینی (استاد مجیدی) | زنگ ۳ تاریخ (استاد نظم‌ده) | زنگ ۴ زبان انگلیسی (استاد علمدار)
  🔹 سه‌شنبه: ۴ زنگ کارگاهی تولید محتوای کامپیوتری (استاد حیدری)
  🔹 چهارشنبه: زنگ ۱ مدیریت تولید (استاد م. محمدی) | زنگ ۲ تفکر و سواد رسانه‌ای (استاد محمدی) | زنگ ۳ ریاضی (استاد یوسفی) | زنگ ۴ شیمی (استاد گل‌محمدی)
- وقتی کاربر درباره برنامه کلاسی، درس‌ها یا زمان تحویل می‌پرسد (مثلاً «فردا چه زنگ‌هایی داریم؟»، «تکلیف ریاضی تا کی وقته؟»، «استاد طراحی وب کیه؟»)، با اطلاعات دقیق و با استناد به این برنامه و تاریخ جاری پاسخ بده.

قوانین بسیار مهم تکالیف مدرسه (Active Assignments Rules):
- وقتی کاربر یا دانش‌آموز می‌پرسد «چه تکالیفی مونده؟» یا «تکالیف کلاس چیه؟» یا «چی باید بنویسیم؟»:
  همیشه فقط و فقط تکالیف فعال، باز و جاری (که هنوز مهلت تحویل آن‌ها نگذشته است) را اعلام کن.
  هرگز تکالیف قدیمی، سال گذشته یا گذشته که مهلت آن‌ها تمام شده است را به عنوان تکلیف باقی‌مانده و جاری به کاربر نگو!
  اگر هیچ تکلیف فعالی نمانده بود، با انرژی و خوشحالی به او بگو که «ایول! در حال حاضر هیچ تکلیف بازی نمونده و همه‌چیز رو تحویل دادی یا تکلیف جدیدی ثبت نشده! استریکت پرچمش بالاست 🔥».

قوانین بسیار مهم فرمت‌بندی متن برای تلگرام (Telegram Formatting Rules):
- پاسخ‌های تو مستقیماً در تلگرام با حالت HTML نمایش داده می‌شوند.
- به هیچ عنوان و تحت هیچ شرایطی از ستاره (مانند **متن** یا *متن* یا ***) برای بولد یا ایتالیک کردن استفاده نکن؛ چون در تلگرام ستاره‌ها بدون استایل و زشت چاپ می‌شوند!
- برای بولد و برجسته کردن تیترها، عناوین و کلمات مهم، فقط و فقط از تگ HTML تلگرام <b>عنوان</b> استفاده کن.
- برای کدهای تک‌خطی یا عبارات مهم انگلیسی از <code>کد</code> استفاده کن.
- برای بولت‌پوینت‌ها و لیست‌ها، اصلاً از * یا - استفاده نکن؛ به جای آن همیشه از ایموجی‌های تمیز مانند 🔹 یا ▫️ یا شماره‌های فارسی (۱. ۲.) استفاده کن.
"""

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_my_status",
            "description": "دریافت آمار شخصی کاربر، استریک، رتبه در لیدربورد و لیست تکالیف فعال و باقی‌مانده‌ای که هنوز انجام نداده است",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_class_assignments",
            "description": "دریافت لیست تکالیف فعال و جاری کلاس (تکالیفی که مهلت تحویل آن‌ها هنوز نگذشته است) با قابلیت فیلتر بر اساس درس",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {
                        "type": "string",
                        "description": "نام یا شناسه درس برای فیلتر اختصاصی (مثلاً ریاضی، شیمی، طراحی وب، فارسی)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "تعداد تکالیف برای نمایش (پیش‌فرض ۵)",
                    },
                    "include_expired": {
                        "type": "boolean",
                        "description": "آیا تکالیف قدیمی و منقضی‌شده قبلی هم آورده شوند؟ پیش‌فرض false است و فقط تکالیف معتبر و فعال می‌آیند.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_leaderboard",
            "description": "مشاهده جدول رتبه‌بندی برتر کلاس (لیدربورد)، درصد موفقیت و استریک‌های برتر",
            "parameters": {
                "type": "object",
                "properties": {
                    "top_n": {
                        "type": "integer",
                        "description": "تعداد نفرات برتر برای نمایش (پیش‌فرض ۵)",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_school_schedule",
            "description": "دریافت برنامه زمانی کلاس‌ها، دروس، نام دبیران و زنگ‌های مدرسه برای یک روز خاص یا کل هفته",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "روز مورد نظر برای دریافت برنامه (مثلاً: امروز، فردا، شنبه، یکشنبه، دوشنبه، سه‌شنبه، چهارشنبه، یا کل هفته)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_assignment",
            "description": "افزودن یک تکلیف جدید به سیستم (فقط مخصوص ادمین و مالک مدرسه)",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "عنوان تکلیف (مثلاً: تمرین‌های فصل ۳ هندسه)",
                    },
                    "description": {
                        "type": "string",
                        "description": "توضیحات کامل تکلیف",
                    },
                    "due_date": {
                        "type": "string",
                        "description": "تاریخ موعد تحویل به فرمت YYYY-MM-DD",
                    },
                    "subject": {
                        "type": "string",
                        "description": "نام درس (مثلاً ریاضی، فیزیک، زیست)",
                    },
                },
                "required": ["title", "due_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "toggle_assignment_completion",
            "description": "علامت‌زدن یا برداشتن علامت انجام تکالیف (تیک زدن انجام دادم یا برگرداندن تیک) برای کاربر فعلی",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["complete", "uncomplete"],
                        "description": "عملیات مورد نظر: complete (تیک زدن به عنوان انجام‌شده) یا uncomplete (برداشتن تیک)",
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["single", "day", "all"],
                        "description": "دامنه تیک زدن: single (یک تکلیف خاص با نام/شناسه)، day (تمام تکالیف یک روز خاص مثل شنبه)، all (تمام تکالیف باقیمانده)",
                    },
                    "assignment_query": {
                        "type": "string",
                        "description": "نام یا شناسه تکلیف برای حالت single (مثلاً ریاضی، تمرین صفحه ۲۰، طراحی وب)",
                    },
                    "target_day": {
                        "type": "string",
                        "description": "نام روز برای حالت scope='day' (مثلاً: شنبه، یکشنبه، دوشنبه، سه‌شنبه، چهارشنبه، امروز، فردا)",
                    },
                },
                "required": ["scope"],
            },
        },
    },
]


def execute_tool(
    name: str, args: Dict[str, Any], db: Session, current_user: Optional[models.User]
) -> Dict[str, Any]:
    """Execute python functions corresponding to function calls."""
    try:
        if name == "get_my_status":
            if not current_user:
                return {
                    "success": False,
                    "message": "اکانت تلگرام شما هنوز به حساب کاربری ArchSchool لینک نشده است. لطفاً کد اتصال اختصاصی خود را از تب پروفایل اپلیکیشن کپی کرده و در پیوی ربات بفرستید تا حساب شما متصل شود.",
                }

            entries, _ = build_leaderboard(db)
            user_entry = next((e for e in entries if e["user"].id == current_user.id), None)
            now = datetime.utcnow()

            # Find uncompleted assignments that are currently ACTIVE (deadline not expired or no deadline)
            completed_ids = (
                select(models.AssignmentCompletion.assignment_id)
                .filter(models.AssignmentCompletion.user_id == current_user.id)
            )
            pending = (
                db.query(models.Assignment)
                .filter(
                    models.Assignment.deleted_at.is_(None),
                    ~models.Assignment.id.in_(completed_ids),
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    ),
                )
                .order_by(
                    models.Assignment.due_date.asc().nulls_last(),
                    models.Assignment.created_at.desc(),
                )
                .limit(5)
                .all()
            )

            pending_list = []
            for a in pending:
                subj_info = school_knowledge.resolve_subject(a.subject_id or a.category or a.course or "")
                subj_name = subj_info["name"] if subj_info else (a.subject_id or a.category or a.course or "عمومی")
                teacher_name = subj_info["teacher"] if subj_info else "دبیر مربوطه"
                rel_due = school_knowledge.format_due_date_relative(a.due_date)
                pending_list.append({
                    "id": a.id,
                    "title": a.title,
                    "subject": subj_name,
                    "teacher": teacher_name,
                    "due_date_relative": rel_due,
                    "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                    "is_active": True,
                })

            return {
                "success": True,
                "username": current_user.username,
                "role": current_user.role,
                "rank": user_entry.get("rank") if user_entry else "نامشخص",
                "current_streak": user_entry.get("current_streak", 0) if user_entry else 0,
                "best_streak": user_entry.get("best_streak", 0) if user_entry else 0,
                "completion_percentage": round(user_entry.get("completion_percentage", 0), 1) if user_entry else 0,
                "pending_assignments": pending_list,
                "pending_count": len(pending_list),
                "has_pending": len(pending_list) > 0,
            }

        elif name == "get_class_assignments":
            limit = args.get("limit", 5)
            include_expired = args.get("include_expired", False)
            subject_filter = args.get("subject", "").strip()
            now = datetime.utcnow()

            query = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))

            # Apply subject filter if specified
            if subject_filter:
                resolved = school_knowledge.resolve_subject(subject_filter)
                s_id = resolved["id"] if resolved else subject_filter
                s_name = resolved["name"] if resolved else subject_filter
                query = query.filter(
                    or_(
                        models.Assignment.subject_id.ilike(f"%{s_id}%"),
                        models.Assignment.subject_id.ilike(f"%{s_name}%"),
                        models.Assignment.category.ilike(f"%{s_name}%"),
                        models.Assignment.course.ilike(f"%{s_name}%"),
                        models.Assignment.title.ilike(f"%{s_name}%"),
                    )
                )

            if not include_expired:
                # ONLY active assignments whose deadline has not passed (or have no deadline)
                query = query.filter(
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now,
                    )
                )
                query = query.order_by(
                    models.Assignment.due_date.asc().nulls_last(),
                    models.Assignment.created_at.desc(),
                )
            else:
                query = query.order_by(models.Assignment.created_at.desc())

            assignments = query.limit(limit).all()

            if not assignments:
                msg = f"در حال حاضر هیچ تکلیف فعالی برای درس '{subject_filter}' وجود ندارد." if subject_filter else "در حال حاضر هیچ تکلیف فعالی با مهلت تحویل باز در سامانه وجود ندارد."
                return {
                    "success": True,
                    "assignments": [],
                    "total_count": 0,
                    "message": msg,
                }

            out_list = []
            for a in assignments:
                subj_info = school_knowledge.resolve_subject(a.subject_id or a.category or a.course or "")
                subj_name = subj_info["name"] if subj_info else (a.subject_id or a.category or a.course or "عمومی")
                teacher_name = subj_info["teacher"] if subj_info else "دبیر مربوطه"
                rel_due = school_knowledge.format_due_date_relative(a.due_date)
                out_list.append({
                    "id": a.id,
                    "title": a.title,
                    "description": a.description,
                    "subject": subj_name,
                    "teacher": teacher_name,
                    "due_date_relative": rel_due,
                    "due_date": a.due_date.strftime("%Y-%m-%d %H:%M") if a.due_date else "بدون مهلت خاص",
                    "is_expired": bool(a.due_date and a.due_date < now),
                })

            return {
                "success": True,
                "total_count": len(out_list),
                "assignments": out_list,
            }

        elif name == "get_leaderboard":
            top_n = args.get("top_n", 5)
            entries, _ = build_leaderboard(db)
            top_list = []
            for e in entries[:top_n]:
                u = e["user"]
                top_list.append({
                    "rank": e.get("rank"),
                    "username": u.username,
                    "percentage": round(e.get("completion_percentage", 0), 1),
                    "streak": e.get("current_streak", 0),
                    "completed_count": e.get("completed_count", 0),
                })
            return {"success": True, "top_students": top_list}

        elif name == "get_school_schedule":
            day_query = args.get("day", "").strip().lower()
            current_status = school_knowledge.get_current_school_status()

            target_day_key = None
            if day_query:
                if any(x in day_query for x in ["امروز", "today"]):
                    target_day_key = current_status["day_key"]
                elif any(x in day_query for x in ["فردا", "tomorrow"]):
                    now_iran = school_knowledge.get_iran_now()
                    tomorrow = now_iran + timedelta(days=1)
                    target_day_key = school_knowledge.WEEKDAYS_MAP.get(tomorrow.weekday(), ("sat", "شنبه"))[0]
                elif any(x in day_query for x in ["بعدی", "روز مدرسه"]):
                    target_day_key = current_status.get("next_school_key", "sat")
                else:
                    target_day_key = school_knowledge.DAY_LOOKUP.get(day_query)

            if target_day_key and target_day_key in school_knowledge.WEEKLY_SCHEDULE:
                day_info = school_knowledge.WEEKLY_SCHEDULE[target_day_key]
                return {
                    "success": True,
                    "day": day_info["day_fa"],
                    "is_school_day": day_info["is_school_day"],
                    "periods": day_info["periods"],
                    "note": day_info.get("note", ""),
                    "current_bell_status": current_status["bell_status"],
                }

            # Return full weekly schedule if no specific day requested
            return {
                "success": True,
                "current_status": current_status,
                "weekly_schedule": school_knowledge.WEEKLY_SCHEDULE,
                "bell_times": [
                    {"period": 1, "time": "08:00 تا 09:30"},
                    {"period": 2, "time": "09:30 تا 11:00"},
                    {"period": 3, "time": "11:00 تا 12:30"},
                    {"period": 4, "time": "12:30 تا 14:00"},
                ],
            }

        elif name == "add_assignment":
            if not current_user or not (current_user.is_admin or current_user.role in ("admin", "owner")):
                return {
                    "success": False,
                    "error": "عدم دسترسی! در سامانه ArchSchool فقط ادمین یا مالک مدرسه مجاز به ثبت تکلیف جدید هستند.",
                }

            title = args.get("title", "").strip()
            description = args.get("description", "").strip()
            due_str = args.get("due_date", "").strip()
            subject = args.get("subject", "").strip()

            if not title:
                return {"success": False, "error": "عنوان تکلیف الزامی است."}

            due_dt = None
            if due_str:
                try:
                    due_dt = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                except Exception:
                    due_dt = datetime.now(timezone.utc)

            subj_info = school_knowledge.resolve_subject(subject)
            s_id = subj_info["id"] if subj_info else subject
            s_name = subj_info["name"] if subj_info else subject

            new_assignment = models.Assignment(
                title=title,
                description=description,
                due_date=due_dt,
                subject_id=s_id,
                category=s_name,
                course=s_name,
                owner_id=current_user.id,
                creator_id=current_user.id,
            )
            db.add(new_assignment)
            # Creator reward: adding an assignment counts towards daily activity
            from ..routers.assignments import _record_daily_activity
            _record_daily_activity(db, current_user.id, datetime.utcnow(), +1)
            db.commit()
            db.refresh(new_assignment)

            return {
                "success": True,
                "message": f"تکلیف '{title}' با موفقیت توسط {current_user.username} در سامانه ثبت شد و امتیاز فعالیت به شما تعلق گرفت!",
                "assignment_id": new_assignment.id,
            }

        elif name == "toggle_assignment_completion":
            if not current_user:
                return {
                    "success": False,
                    "message": "برای تیک زدن تکالیف، ابتدا باید اکانت تلگرام خود را به حساب ArchSchool متصل کنید. کد اتصال اختصاصی خود را از اپلیکیشن بگیرید و بفرستید.",
                }

            action = args.get("action", "complete")
            scope = args.get("scope", "single")
            assignment_query = args.get("assignment_query", "").strip()
            target_day = args.get("target_day", "").strip()
            now = datetime.utcnow()

            target_assignments = []
            if scope == "single":
                q = db.query(models.Assignment).filter(models.Assignment.deleted_at.is_(None))
                clean_query = assignment_query.strip()
                for stop_word in ["یک", "یه", "یکی", "تکلیف", "تکالیف", "تکلیفم", "تکلیفمو", "رو", "را"]:
                    clean_query = clean_query.replace(stop_word, "").strip()

                if assignment_query.isdigit():
                    target_assignments = q.filter(models.Assignment.id == int(assignment_query)).all()
                elif clean_query:
                    subj = school_knowledge.resolve_subject(clean_query)
                    s_id = subj["id"] if subj else clean_query
                    s_name = subj["name"] if subj else clean_query
                    target_assignments = q.filter(
                        or_(
                            models.Assignment.title.ilike(f"%{clean_query}%"),
                            models.Assignment.subject_id.ilike(f"%{s_id}%"),
                            models.Assignment.subject_id.ilike(f"%{s_name}%"),
                            models.Assignment.category.ilike(f"%{s_name}%"),
                            models.Assignment.course.ilike(f"%{s_name}%"),
                        )
                    ).all()

                if not target_assignments:
                    # Smart fallback: pick the nearest active pending assignment for this student
                    completed_ids = (
                        select(models.AssignmentCompletion.assignment_id)
                        .filter(models.AssignmentCompletion.user_id == current_user.id)
                    )
                    if action == "complete":
                        fallback_cand = (
                            db.query(models.Assignment)
                            .filter(
                                models.Assignment.deleted_at.is_(None),
                                ~models.Assignment.id.in_(completed_ids),
                                or_(
                                    models.Assignment.due_date.is_(None),
                                    models.Assignment.due_date >= now - timedelta(days=1),
                                ),
                            )
                            .order_by(models.Assignment.due_date.asc().nulls_last())
                            .first()
                        )
                    else:
                        fallback_cand = (
                            db.query(models.Assignment)
                            .filter(
                                models.Assignment.deleted_at.is_(None),
                                models.Assignment.id.in_(completed_ids),
                            )
                            .order_by(models.Assignment.updated_at.desc())
                            .first()
                        )

                    if fallback_cand:
                        target_assignments = [fallback_cand]
                    else:
                        return {
                            "success": False,
                            "error": "تکلیف فعال و باقی‌مانده‌ای برای تیک زدن پیدا نشد. همه‌چیز رو انجام دادی! ایول 🔥",
                        }
                target_assignments = target_assignments[:1]

            elif scope == "day":
                resolved_key = None
                if target_day:
                    current_status = school_knowledge.get_current_school_status()
                    if "امروز" in target_day:
                        resolved_key = current_status["day_key"]
                    elif "فردا" in target_day:
                        now_iran = school_knowledge.get_iran_now()
                        tomorrow = now_iran + timedelta(days=1)
                        resolved_key = school_knowledge.WEEKDAYS_MAP.get(tomorrow.weekday(), ("sat", "شنبه"))[0]
                    else:
                        resolved_key = school_knowledge.DAY_LOOKUP.get(target_day)

                all_live = db.query(models.Assignment).filter(
                    models.Assignment.deleted_at.is_(None),
                    or_(
                        models.Assignment.due_date.is_(None),
                        models.Assignment.due_date >= now - timedelta(days=2),
                    )
                ).all()

                for a in all_live:
                    if resolved_key and a.due_date:
                        due_iran = a.due_date + timedelta(hours=3.5)
                        a_key = school_knowledge.WEEKDAYS_MAP.get(due_iran.weekday(), ("", ""))[0]
                        if a_key == resolved_key:
                            target_assignments.append(a)
                    elif resolved_key and not a.due_date:
                        day_sched = school_knowledge.WEEKLY_SCHEDULE.get(resolved_key, {})
                        day_subjs = [p["subject_id"] for p in day_sched.get("periods", [])]
                        if a.subject_id in day_subjs or a.course in day_subjs:
                            target_assignments.append(a)

                # If no assignments found for today (e.g. today is Thursday/Friday), check next school day
                if not target_assignments and ("امروز" in target_day or resolved_key in ("thu", "fri")):
                    current_status = school_knowledge.get_current_school_status()
                    next_key = current_status.get("next_school_key", "sat")
                    for a in all_live:
                        if a.due_date:
                            due_iran = a.due_date + timedelta(hours=3.5)
                            a_key = school_knowledge.WEEKDAYS_MAP.get(due_iran.weekday(), ("", ""))[0]
                            if a_key == next_key:
                                target_assignments.append(a)
                        else:
                            day_sched = school_knowledge.WEEKLY_SCHEDULE.get(next_key, {})
                            day_subjs = [p["subject_id"] for p in day_sched.get("periods", [])]
                            if a.subject_id in day_subjs or a.course in day_subjs:
                                target_assignments.append(a)

                if not target_assignments:
                    day_name = school_knowledge.WEEKLY_SCHEDULE.get(resolved_key, {}).get("day_fa", target_day)
                    return {
                        "success": False,
                        "error": f"هیچ تکلیف فعالی برای روز {day_name} در سیستم پیدا نشد.",
                    }

            elif scope == "all":
                completed_ids = (
                    select(models.AssignmentCompletion.assignment_id)
                    .filter(models.AssignmentCompletion.user_id == current_user.id)
                )
                if action == "complete":
                    target_assignments = (
                        db.query(models.Assignment)
                        .filter(
                            models.Assignment.deleted_at.is_(None),
                            ~models.Assignment.id.in_(completed_ids),
                            or_(
                                models.Assignment.due_date.is_(None),
                                models.Assignment.due_date >= now,
                            ),
                        )
                        .all()
                    )
                else:
                    target_assignments = (
                        db.query(models.Assignment)
                        .filter(
                            models.Assignment.deleted_at.is_(None),
                            models.Assignment.id.in_(completed_ids),
                        )
                        .all()
                    )

            if not target_assignments:
                return {
                    "success": True,
                    "message": "هیچ تکلیفی برای تغییر وضعیت وجود نداشت.",
                    "modified_count": 0,
                }

            from ..routers.assignments import _record_daily_activity
            modified_titles = []
            for a in target_assignments:
                existing = (
                    db.query(models.AssignmentCompletion)
                    .filter(
                        models.AssignmentCompletion.user_id == current_user.id,
                        models.AssignmentCompletion.assignment_id == a.id,
                    )
                    .first()
                )
                if action == "complete":
                    if not existing:
                        db.add(
                            models.AssignmentCompletion(
                                user_id=current_user.id,
                                assignment_id=a.id,
                                completed_at=now,
                            )
                        )
                        _record_daily_activity(db, current_user.id, now, +1)
                        modified_titles.append(a.title)
                else:
                    if existing:
                        db.delete(existing)
                        _record_daily_activity(db, current_user.id, now, -1)
                        modified_titles.append(a.title)

            db.commit()

            entries, _ = build_leaderboard(db)
            user_entry = next((e for e in entries if e["user"].id == current_user.id), None)

            # Trigger Top 1 check in background
            try:
                import asyncio
                from . import telegram_bot
                loop = asyncio.get_running_loop()
                loop.create_task(telegram_bot.check_and_broadcast_top1(db))
            except Exception:
                pass

            act_fa = "انجام شد و تیک خورد" if action == "complete" else "تیک آن برداشته شد"
            return {
                "success": True,
                "action": action,
                "modified_count": len(modified_titles),
                "modified_titles": modified_titles,
                "message": f"تعداد {len(modified_titles)} تکلیف با موفقیت {act_fa}!",
                "new_completion_percentage": round(user_entry.get("completion_percentage", 0), 1) if user_entry else 0,
                "current_streak": user_entry.get("current_streak", 0) if user_entry else 0,
                "new_rank": user_entry.get("rank") if user_entry else "نامشخص",
            }

        return {"success": False, "error": f"ابزار ناشناخته: {name}"}
    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc)
        return {"success": False, "error": str(exc)}


def _format_friendly_ai_error(status_code: int, raw_text: str) -> str:
    """Generate friendly Persian error messages without exposing technical codes or raw HTML/JSON."""
    if status_code == 429:
        return "⚠️ سرویس هوش مصنوعی در حال حاضر پرمصرف است یا به سقف مجاز درخواست در دقیقه رسیده است. لطفاً یک دقیقه بعد دوباره امتحان کنید."
    elif status_code in (500, 502, 503, 504):
        return "⚠️ سرور هوش مصنوعی به طور موقت تحت بار سنگین ترافیکی است یا در دسترس نیست. لطفاً یک دقیقه دیگر تلاش کنید."
    elif status_code in (401, 403):
        return "⚠️ کلید دسترسی هوش مصنوعی نامعتبر است یا دسترسی به این مدل محدود شده است. لطفاً تنظیمات کلید را در پنل مدرسه بررسی کنید."
    elif status_code == 404:
        return "⚠️ مدل هوش مصنوعی انتخاب‌شده در این سرویس یافت نشد یا تغییر کرده است. لطفاً در پنل مدیریت مدل دیگری را انتخاب کنید."
    return "⚠️ ارتباط با سرویس هوش مصنوعی با اختلال موقت مواجه شد. لطفاً کمی بعد دوباره پیام دهید."


async def ask_universal_ai_agent(
    user_prompt: str,
    api_key: str,
    db: Session,
    base_url: str = "https://openrouter.ai/api/v1",
    model_name: str = "openai/gpt-4o-mini",
    current_user: Optional[models.User] = None,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    is_recent: bool = False,
) -> str:
    """Universal OpenAI-compatible chat completions caller with Tools / Function Calling.

    Works natively with OpenRouter, Grok (xAI), DeepSeek, OpenAI, Groq, Together, and self-hosted models.
    """
    if not api_key:
        return "⚠️ کلید API هوش مصنوعی هنوز در پنل مدیریت مدرسه تنظیم نشده است."

    clean_base = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
    if not clean_base.endswith("/chat/completions"):
        endpoint_url = f"{clean_base}/chat/completions"
    else:
        endpoint_url = clean_base

    # Route Google Gemini through host IPv6 gateway to bypass Contabo IPv4 blacklist
    if "generativelanguage.googleapis.com" in endpoint_url:
        endpoint_url = endpoint_url.replace(
            "https://generativelanguage.googleapis.com",
            "https://archschool.vidxsepehr.ir/gemini",
        )

    clean_model = model_name.strip() if model_name else "openai/gpt-4o-mini"

    status = school_knowledge.get_current_school_status()
    user_info = (
        f"کاربر صحبت‌کننده: {current_user.username} (نقش: {current_user.role})"
        if current_user
        else "کاربر صحبت‌کننده: هنوز اکانت تلگرام خود را به حساب کاربری ArchSchool لینک نکرده است."
    )
    time_context = (
        f"اطلاعات زنده زمانی و تقویم:\n"
        f"- امروز: {status['today_fa']} | ساعت رسمی ایران: {status['current_time']}\n"
        f"- فردا: {status['tomorrow_fa']}\n"
        f"- روز کلاسی بعدی: {status['next_school_day']}"
    )
    session_hint = (
        "وضعیت مکالمه: گفتگوی فعال در جریان است. سلام تکراری نده و مستقیماً و صمیمی صحبت را ادامه بده."
        if is_recent
        else "وضعیت مکالمه: شروع مکالمه جدید است. یک سلام گرم، خودمانی و پرانرژی با نام کاربر بده."
    )

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_INSTRUCTION},
    ]

    if conversation_history:
        messages.extend(conversation_history)

    messages.append({
        "role": "user",
        "content": f"[{time_context}]\n[{user_info}]\n[{session_hint}]\n{user_prompt}",
    })

    headers = {
        "Authorization": f"Bearer {api_key.strip()}",
        "Content-Type": "application/json",
    }
    if "openrouter.ai" in endpoint_url:
        headers["HTTP-Referer"] = "https://archschool.vidxsepehr.ir"
        headers["X-Title"] = "ArchSchool Assistant"

    payload: Dict[str, Any] = {
        "model": clean_model,
        "messages": messages,
        "tools": OPENAI_TOOLS,
        "tool_choice": "auto",
        "temperature": 0.7,
        "max_tokens": 800,
    }

    try:
        async with httpx.AsyncClient(timeout=35.0) as client:
            resp = await client.post(endpoint_url, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.error("AI provider error %s from %s: %s", resp.status_code, endpoint_url, resp.text)
                return _format_friendly_ai_error(resp.status_code, resp.text)

            data = resp.json()
            choices = data.get("choices", [])
            if not choices:
                return "پاسخی از هوش مصنوعی دریافت نشد."

            first_choice = choices[0]
            choice_message = first_choice.get("message", {})
            tool_calls = choice_message.get("tool_calls")

            # --- Tool Calling Branch ---
            if tool_calls:
                # Add assistant message with tool_calls to history (clean schema)
                clean_assistant: Dict[str, Any] = {
                    "role": "assistant",
                    "content": choice_message.get("content"),
                    "tool_calls": tool_calls,
                }
                messages.append(clean_assistant)

                for tc in tool_calls:
                    call_id = tc.get("id") or "call_1"
                    fn_data = tc.get("function", {})
                    fn_name = fn_data.get("name", "")
                    fn_args_raw = fn_data.get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                    except Exception:
                        fn_args = {}

                    logger.info("Universal AI invoking tool: %s with args: %s", fn_name, fn_args)
                    tool_output = execute_tool(fn_name, fn_args, db, current_user)

                    # Append tool result message
                    messages.append({
                        "role": "tool",
                        "tool_call_id": str(call_id),
                        "content": json.dumps(tool_output, ensure_ascii=False),
                    })

                # Follow-up request to get final friendly response
                followup_payload = {
                    "model": clean_model,
                    "messages": messages,
                    "tools": OPENAI_TOOLS,
                    "temperature": 0.7,
                    "max_tokens": 800,
                }
                followup_resp = await client.post(endpoint_url, json=followup_payload, headers=headers)
                if followup_resp.status_code == 200:
                    followup_data = followup_resp.json()
                    followup_choices = followup_data.get("choices", [])
                    if followup_choices:
                        final_content = followup_choices[0].get("message", {}).get("content", "")
                        return final_content or "انجام شد!"

            # Normal text content
            content = choice_message.get("content", "")
            return content or "متوجه پیامت نشدم، لطفاً دوباره بگو!"

    except httpx.TimeoutException:
        logger.error("AI provider timeout to %s", endpoint_url)
        return "⚠️ پاسخ ارائه‌دهنده هوش مصنوعی بیش از حد طول کشید. لطفاً مجدداً تلاش کنید."
    except Exception as exc:
        logger.error("Universal AI agent exception: %s", exc)
        return f"⚠️ در ارتباط با هوش مصنوعی مشکلی رخ داد: {str(exc)[:100]}"
