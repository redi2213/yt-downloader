"""Persian texts of the browser link menu (screens/browser_pages.py: open_link_menu) and its setting."""

BL_EXACT = {
    "Link": "لینک",
    "Open in a background tab": "باز کردن در تب پس\u200cزمینه",
    "Open in the download editor": "باز کردن در ویرایشگر دانلود",
    "Copy link text": "کپی متن لینک",
    "Copy link": "کپی لینک",
    "Share link": "اشتراک\u200cگذاری لینک",
    "Open in the Browser": "باز کردن در مرورگر",
    "Save page as...": "ذخیره\u200cی صفحه",
    "Save as PDF": "ذخیره به صورت PDF",
    "Save as HTML": "ذخیره به صورت HTML",
    "Save as screenshot (visible part)": "ذخیره به صورت اسکرین\u200cشات (بخش دیده\u200cشده)",
    "Saving...": "در حال ذخیره...",
    "Open a page first": "اول یک صفحه را باز کنید",
    "The page took too long to answer": "صفحه دیر پاسخ داد",
    "Files go to Download/Yt-bridge/Pages (or the folder chosen in Settings). The PDF holds the whole page; "
    "the screenshot only what is on the screen.":
        "فایل\u200cها در Download/Yt-bridge/Pages (یا پوشه\u200cی انتخاب\u200cشده در تنظیمات) ذخیره می\u200cشوند. "
        "PDF کل صفحه را دارد؛ اسکرین\u200cشات فقط آنچه روی صفحه دیده می\u200cشود.",
    "Back to the page": "بازگشت به صفحه",
    "Opened in a background tab": "در تب پس\u200cزمینه باز شد",
    "Link text copied": "متن لینک کپی شد",
    "Link copied": "لینک کپی شد",
    "This link has no text - the link was copied": "این لینک متن ندارد - خود لینک کپی شد",
    "Share is not available - copied to the clipboard": "اشتراک\u200cگذاری در دسترس نیست - در کلیپ\u200cبورد کپی شد",
    "Direct file link click: open the download editor": "کلیک روی لینک مستقیم فایل: ویرایشگر دانلود باز شود",
    "Direct file link click: add to the list (default)": "کلیک روی لینک مستقیم فایل: فقط به لیست اضافه شود (پیش\u200cفرض)",
    "Pressing and holding a link in a page opens its menu: background tab, download editor, copy, share.":
        "نگه داشتن انگشت روی لینک در صفحه، منوی آن را باز می\u200cکند: تب پس\u200cزمینه، ویرایشگر دانلود، کپی، اشتراک\u200cگذاری.",
}

BL_PATTERNS = [
    (r"Saved: (.+)", "ذخیره شد: {0}"),
    (r"Could not save: (.+)", "ذخیره نشد: {0}"),
    (r"Tab limit reached \((\d+)\)", "به سقف تب\u200cها رسیدید ({0})"),
]
