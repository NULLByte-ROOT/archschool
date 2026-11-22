"""Default prompts and configurations for ArchSchool AI.

By default, prompt strings are empty so the AI model uses its standard behavior
unless custom instructions or persona anchors are configured in the Admin Panel.
"""

DEFAULT_SYSTEM_PROMPT = ""
DEFAULT_PERSONA_ANCHOR = ""
DEFAULT_FOLLOWUP_ANCHOR = ""
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1000

# Event Triggers & Automatic Notifications Default Prompts
DEFAULT_NOTIFY_TOP1_ENABLED = True
DEFAULT_NOTIFY_TOP1_PROMPT = (
    "به عنوان هوش مصنوعی ربات مدرسه، با لحنی پرانرژی، هیجان‌انگیز، خودمانی و جذاب، "
    "اعلام کن که صدرنشین و رتبه ۱ لیدربورد کلاس تغییر کرده است. "
    "نام پادشاه جدید جدول، استریک و درصد را بگو، به نفر قبلی تیکه رفاقتی بنداز "
    "و بقیه همکلاسی‌ها را ترغیب کن تا عقب نمانند و رقابت کنند."
)

DEFAULT_NOTIFY_NEW_ASSIGNMENT_ENABLED = True
DEFAULT_NOTIFY_NEW_ASSIGNMENT_PROMPT = (
    "به عنوان هوش مصنوعی ربات مدرسه، تکلیف یا یادآوری جدید ثبت‌شده در اپلیکیشن را به بچه‌ها اطلاع بده. "
    "با لحنی رفاقتی و ترغیب‌کننده، نام درس، عنوان تکلیف، مهلت تحویل و توضیحات را بگو "
    "و بچه‌ها را تشویق کن سریع‌تر در اپلیکیشن تیک آن را ثبت کنند."
)

DEFAULT_NOTIFY_DEADLINE_ENABLED = True
DEFAULT_NOTIFY_DEADLINE_PROMPT = (
    "به عنوان هوش مصنوعی ربات مدرسه، نزدیک شدن ددلاین تکلیف را با لحنی هشداردهنده اما دوستانه و بامزه یادآوری کن. "
    "زمان باقیمانده، نام درس و تکلیف را ذکر کن و یادآوری کن که برای حفظ درصد و استریک روزانه‌شان سریع‌تر دست‌به‌کار شوند."
)

DEFAULT_NOTIFY_OVERDUE_PV_ENABLED = True
DEFAULT_NOTIFY_OVERDUE_PV_PROMPT = (
    "به عنوان هوش مصنوعی ربات مدرسه، در چت خصوصی (پیوی) به دانش‌آموزی که مهلت تکلیفش تمام شده و هنوز انجام نداده پیام بده. "
    "با لحنی پیگیر، صمیمی و پرسشگر بگو که مهلت تکلیف به پایان رسیده و بپرس آیا انجام داده یا نه و چرا هنوز ثبت نکرده است."
)

DEFAULT_NOTIFY_OVERDUE_GROUP_ENABLED = True
DEFAULT_NOTIFY_OVERDUE_GROUP_PROMPT = (
    "به عنوان هوش مصنوعی ربات مدرسه، در گروه کلاس دانش‌آموزانی که مهلت تکلیفشان منقضی شده را صدا بزن. "
    "با لحنی خودمانی، بامزه و کمی جدی بگو که سریعاً بیایند پیوی ربات چون با آن‌ها کار مهمی داری و باید وضعیت تکلیفشان را مشخص کنند."
)

