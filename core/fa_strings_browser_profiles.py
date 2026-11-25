"""Persian texts of the browser profiles screens (screens/browser_profiles.py; Browser settings > Profiles)."""

BPF_EXACT = {
    "Browser profiles": "پروفایل‌های مرورگر",
    "Each profile is a separate box: its own cookies and logins, settings, speed dial, history, bookmarks and tabs. "
    "Export cookies uses the active profile. Profiles are switched only here, in the browser settings.":
        "هر پروفایل یک جعبه‌ی جداست: کوکی و لاگین، تنظیمات، Speed-dial، تاریخچه، بوکمارک و تب‌های خودش را دارد. "
        "Export cookies از پروفایل فعال می‌گیرد. تعویض پروفایل فقط از همین‌جا، در تنظیمات مرورگر، انجام می‌شود.",
    "This phone's browser engine (Android System WebView) is too old for profiles. Update it from Google Play.":
        "موتور مرورگر این گوشی (Android System WebView) برای پروفایل‌ها قدیمی است. آن را از گوگل‌پلی به‌روز کنید.",
    "New profile": "پروفایل جدید",
    "Profile name": "نام پروفایل",
    "Secure profile: OFF": "پروفایل امن: خاموش",
    "Secure profile: ON": "پروفایل امن: روشن",
    "Secure profile: cookies, logins and tabs stay saved; third-party trackers and cookies are blocked; "
    "WebRTC cannot leak your IP; location, camera and microphone are closed and ask every time. No proxy. "
    "It cannot be changed after the profile is made.":
        "پروفایل امن: کوکی، لاگین و تب‌ها ذخیره می‌مانند؛ ردیاب‌ها و کوکی‌های شخص ثالث بلاک می‌شوند؛ WebRTC "
        "نمی‌تواند IP را لو بدهد؛ لوکیشن، دوربین و میکروفن بسته‌اند و هر بار می‌پرسند. بدون پروکسی. "
        "بعد از ساخت پروفایل قابل تغییر نیست.",
    "Create profile": "ساخت پروفایل",
    "Profile created": "پروفایل ساخته شد",
    "Profile deleted": "پروفایل حذف شد",
    "Saved": "ذخیره شد",
    "Edit": "ویرایش",
    "Edit profile": "ویرایش پروفایل",
    "Save": "ذخیره",
    "Normal profile": "پروفایل معمولی",
    "Secure profile": "پروفایل امن",
    "Switch to this profile": "رفتن به این پروفایل",
    "Delete profile": "حذف پروفایل",
    "Tap again to delete this profile and all its data": "برای حذف این پروفایل و همه‌ی داده‌هایش دوباره بزنید",
    "Open the browser": "باز کردن مرورگر",
    "Back to the browser settings": "بازگشت به تنظیمات مرورگر",
    "Back to the profiles": "بازگشت به پروفایل‌ها",
    "Already the active profile": "همین پروفایل فعال است",
    "Name can't be empty": "نام نمی‌تواند خالی باشد",
    "A profile with this name already exists": "پروفایلی با این نام از قبل هست",
    "The main profile can't be deleted": "پروفایل اصلی حذف نمی‌شود",
    "Switch to another profile first": "اول به پروفایل دیگری بروید",
    "Profile not found": "پروفایل پیدا نشد",
    "This phone's browser engine does not support profiles (update Android System WebView)":
        "موتور مرورگر این گوشی از پروفایل پشتیبانی نمی‌کند (Android System WebView را به‌روز کنید)",
    "Color: Blue": "رنگ: آبی",
    "Color: Green": "رنگ: سبز",
    "Color: Red": "رنگ: قرمز",
    "Color: Orange": "رنگ: نارنجی",
    "Color: Purple": "رنگ: بنفش",
    "Color: Teal": "رنگ: سبزآبی",
    "Color: Pink": "رنگ: صورتی",
    "Color: Gray": "رنگ: خاکستری",
}

BPF_PATTERNS = [
    (r"Profile: (.+)", "پروفایل: {0}"),
    (r"(.+) \(active, secure\)", "{0} (فعال، امن)"),
    (r"(.+) \(active\)", "{0} (فعال)"),
    (r"(.+) \(secure\)", "{0} (امن)"),
]
