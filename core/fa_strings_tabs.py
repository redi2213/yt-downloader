"""Persian texts of the app tabs (screens/tabs.py, main.py: the Tabs button)."""

TB_EXACT = {
    "Tabs": "تب\u200cها",
    "New tab": "تب جدید",
    "Close tab": "بستن تب",
    "Close the tab": "بستن تب",
    "Tab": "تب",
    "Running job": "کار در حال اجرا",
    "Quality list": "فهرست کیفیت\u200cها",
    "Video download": "دانلود ویدیو",
    "Playlist links": "لینک\u200cهای پلی\u200cلیست",
    "Playlist download": "دانلود پلی\u200cلیست",
    "File upload": "آپلود فایل",
    "Status: idle": "وضعیت: بیکار",
    "Status: running": "وضعیت: در حال اجرا",
    "Status: finished": "وضعیت: تمام شد",
    "Status: error": "وضعیت: خطا",
    "This tab is running a job. Close it anyway? The job keeps running on GitHub, but you will not see it here.":
        "در این تب یک کار در حال اجراست. بسته شود؟ کار روی GitHub ادامه می\u200cدهد، ولی پیشرفتش را اینجا نمی\u200cبینید.",
    "All tabs are busy. Which one should be closed to make room for the new link?":
        "همه\u200cی تب\u200cها مشغول\u200cاند. برای لینک جدید کدام تب بسته شود؟",
}

TB_PATTERNS = [
    (r"Tabs \((\d+)\)(.*)", "تب\u200cها ({0}){1}"),
    (r"Status: running (\d+)%", "وضعیت: در حال اجرا {0}٪"),
    (r"Close tab (\d+): (.+)", "بستن تب {0}: {1}"),
    (r"Up to (\d+) tabs are open", "حداکثر {0} تب باز است"),
]
