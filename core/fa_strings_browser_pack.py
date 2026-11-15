"""Persian texts of Settings > App tools > Browser online update (screens/browser_pack_screen.py)."""

BP_EXACT = {
    "Browser online update": "به‌روزرسانی آنلاین مرورگر",
    "Running: built-in version": "در حال اجرا: نسخه داخلی برنامه",
    "Check for update": "بررسی به‌روزرسانی",
    "Apply now": "اعمال همین الان",
    "Go back to the previous version": "بازگشت به نسخه قبلی",
    "Use the built-in version": "استفاده از نسخه داخلی",
    "Automatic check: ON": "بررسی خودکار: روشن",
    "Automatic check: OFF": "بررسی خودکار: خاموش",
    "Checking for a new version...": "در حال بررسی نسخه جدید...",
    "Already up to date": "به‌روز است",
    "No online browser version is published yet": "هنوز نسخه آنلاینی برای مرورگر منتشر نشده است",
    "There is no previous version": "نسخه قبلی وجود ندارد",
    "Ready: built-in version (tap Apply now)": "آماده: نسخه داخلی (روی «اعمال همین الان» بزنید)",
    "Applied: built-in version": "اعمال شد: نسخه داخلی",
    "Went back: built-in version": "بازگشت انجام شد: نسخه داخلی",
    "Using: built-in version": "اکنون نسخه داخلی استفاده می‌شود",
    "just now": "همین الان",
    "The browser's Python code (tabs, lists, sort, file types, cookies, menus) can be updated from GitHub "
    "without a new APK. A downloaded version is checked first; if it fails, the built-in version is used. "
    "Changes to the native part (Java) still need a new APK.":
        "کد پایتون مرورگر (تب‌ها، لیست‌ها، مرتب‌سازی، نوع فایل‌ها، کوکی‌ها، منوها) بدون APK جدید از GitHub "
        "به‌روز می‌شود. نسخه‌ی دانلودشده اول بررسی می‌شود؛ اگر مشکل داشت، نسخه داخلی استفاده می‌شود. "
        "تغییر بخش بومی (Java) هنوز APK جدید می‌خواهد.",
}

BP_PATTERNS = [
    (r"Running: online version (.+)", "در حال اجرا: نسخه آنلاین {0}"),
    (r"Ready: (.+) \(tap Apply now\)", "آماده: {0} (روی «اعمال همین الان» بزنید)"),
    (r"Last check: (.+)", "آخرین بررسی: {0}"),
    (r"(\d+) min ago", "{0} دقیقه پیش"),
    (r"(\d+) h ago", "{0} ساعت پیش"),
    (r"(\d+) days ago", "{0} روز پیش"),
    (r"Last problem: (.+)", "آخرین مشکل: {0}"),
    (r"New version downloaded: (.+)", "نسخه جدید دانلود شد: {0}"),
    (r"This version was refused: (.+)", "این نسخه پذیرفته نشد: {0}"),
    (r"This version was blocked earlier: (.+)", "این نسخه قبلاً مسدود شده است: {0}"),
    (r"Could not check: (.+)", "بررسی انجام نشد: {0}"),
    (r"Applied: online version (.+)", "اعمال شد: نسخه آنلاین {0}"),
    (r"Went back: online version (.+)", "بازگشت انجام شد: نسخه آنلاین {0}"),
]
