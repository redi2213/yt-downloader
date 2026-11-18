"""More Persian texts (messages of the screens and services, the buttons of config.json).
MORE_EXACT / MORE_PATTERNS are added to core/fa_strings.py; PHRASES are the last resort for
texts that are put together from pieces (``f"Last check: {when}"``): every known piece found
in the text is replaced and the rest (names, numbers) stays as it is."""

MORE_EXACT = {
    # --- update 7: direct link + Lab tools in the share list
    "Direct link (one per line)": "لینک مستقیم (هر خط یک لینک)",
    "Download link": "دانلود لینک",
    "Paste a link that starts with http:// or https://": "لینکی بگذار که با http:// یا https:// شروع شود",
    "Download started": "دانلود شروع شد",
    "Lab tools": "ابزارهای آزمایشگاه",
    "Loading Lab tools...": "در حال بارگیری ابزارهای آزمایشگاه...",
    # --- Lab screen
    "Lab - test tools": "آزمایشگاه - ابزارهای در حال آزمایش",
    "Loading the tool list...": "در حال بارگیری فهرست ابزارها...",
    "Add workflow": "افزودن ورک‌فلو",
    "Forget saved copies": "پاک کردن نسخه‌های ذخیره‌شده",
    "Saved copies removed": "نسخه‌های ذخیره‌شده پاک شد",
    "Offline: showing the saved tool list.": "آفلاین: فهرست ذخیره‌شده‌ی ابزارها نشان داده می‌شود.",
    "No tools yet. Add one to lab/index.json (see LAB.md on the lab branch).": "هنوز ابزاری نیست. یکی به lab/index.json اضافه کنید (LAB.md را روی برنچ lab ببینید).",
    # --- config.json (Download Anything buttons and their fields)
    "Download from TikTok": "دانلود از تیک‌تاک",
    "Video links (one per line)": "لینک ویدیوها (هر خط یکی)",
    "Paste one or more page links": "یک یا چند لینک صفحه را بچسبان",
    "Quality": "کیفیت",
    "Check formats": "بررسی فرمت‌ها",
    "Highest": "بالاترین",
    "Series links (from one episode link)": "لینک‌های سریال (از روی لینک یک قسمت)",
    "One episode link": "لینک یک قسمت",
    "Put a * where the episode number is (optional)": "جای شماره‌ی قسمت یک * بگذار (اختیاری)",
    "First episode": "اولین قسمت",
    "1   (type 01 to keep the zero when you use *)": "1   (اگر از * استفاده می‌کنی، برای حفظ صفر 01 بنویس)",
    "Last episode": "آخرین قسمت",
    "5   (up to 100 episodes per run)": "5   (تا ۱۰۰ قسمت در هر اجرا)",
    "Season (replaces S01 in the link)": "فصل (جای S01 در لینک می‌نشیند)",
    "Keep as in link": "مثل لینک بماند",
    "Links only": "فقط لینک‌ها",
    "Links + upload files": "لینک‌ها + آپلود فایل‌ها",
    "Check that every link works": "بررسی کار کردن همه‌ی لینک‌ها",
    "Upload mode: zip each file": "حالت آپلود: زیپ هر فایل",
    "Download from Aparat": "دانلود از آپارات",
    "Best": "بهترین",
    "Output": "خروجی",
    "Upload files": "آپلود فایل‌ها",
    "Upload as one zip": "آپلود به‌صورت یک زیپ",
    "Links on phone": "لینک‌ها روی گوشی",
    "Channel: how many (tap one, or type your own)": "کانال: چند تا (یکی را لمس کن یا عدد دلخواه بنویس)",
    "Videos": "ویدیو",
    "Days": "روز",
    "Download from Telegram": "دانلود از تلگرام",
    "Download APK from Google Play": "دانلود APK از گوگل پلی",
    "Google Play link": "لینک گوگل پلی",
    "Mode": "حالت",
    "Universal (everything)": "یونیورسال (همه چیز)",
    "Optimized (one device type)": "بهینه (یک نوع دستگاه)",
    "Device type": "نوع دستگاه",
    "arm64 (most phones)": "arm64 (بیشتر گوشی‌ها)",
    "armv7 (old 32-bit)": "armv7 (قدیمی ۳۲ بیتی)",
    "All (Universal only)": "همه (فقط یونیورسال)",
    "Your Android version (only used to warn)": "نسخه‌ی اندروید تو (فقط برای هشدار)",
    "Don't check": "بررسی نکن",
    "Extra languages (English is always included)": "زبان‌های اضافه (انگلیسی همیشه هست)",
    "English only": "فقط انگلیسی",
    "Persian": "فارسی",
    "Arabic": "عربی",
    "Persian + Arabic": "فارسی + عربی",
    "Standard (apk / apks / xapk)": "استاندارد (apk / apks / xapk)",
    "Filimo": "فیلیمو",
    "Filimo link": "لینک فیلیمو",
    "Movie or episode link (or item ID)": "لینک فیلم یا قسمت (یا شناسه)",
    "Get link (phone network)": "دریافت لینک (شبکه‌ی گوشی)",
    "Subtitle (download mode only)": "زیرنویس (فقط حالت دانلود)",
    "None": "هیچ",
    # --- files / folders / install (core)
    "Choosing a folder works only on the phone.": "انتخاب پوشه فقط روی گوشی ممکن است.",
    "Picking a file works only on the phone.": "انتخاب فایل فقط روی گوشی ممکن است.",
    "The file location is unknown - open the APK from the Files app.": "محل فایل معلوم نیست - APK را از برنامه‌ی فایل‌ها باز کن.",
    "Installing works only on the phone.": "نصب فقط روی گوشی ممکن است.",
    "Allow \"Install unknown apps\" for YT Bridge, come back and press Install again.":
        "برای YT Bridge گزینه‌ی «نصب برنامه‌های ناشناس» را مجاز کن، برگرد و دوباره «نصب» را بزن.",
    "The file location is unknown - open it from the Files app.": "محل فایل معلوم نیست - آن را از برنامه‌ی فایل‌ها باز کن.",
    "The file location is unknown - share it from the Files app.": "محل فایل معلوم نیست - آن را از برنامه‌ی فایل‌ها به اشتراک بگذار.",
    "Opening a file works only on the phone.": "باز کردن فایل فقط روی گوشی ممکن است.",
    "Sharing a file works only on the phone.": "اشتراک فایل فقط روی گوشی ممکن است.",
    "Android would not create the file in Downloads": "اندروید اجازه نداد فایل را در Downloads بسازد",
    "Android would not create the sub folder": "اندروید زیرپوشه را نساخت",
    "Android would not create the file in the chosen folder": "اندروید اجازه نداد فایل را در پوشه‌ی انتخابی بسازد",
    "The zip is empty.": "زیپ خالی است.",
    "No files found. Use folders named like branches, e.g. main/ and config/.": "فایلی پیدا نشد. از پوشه‌هایی هم‌نام برنچ‌ها استفاده کن، مثل main/ و config/.",
    "This is not a valid zip file.": "این فایل زیپ معتبری نیست.",
    "expires at the next cleanup": "در پاکسازی بعدی منقضی می‌شود",
    # --- about
    "Download from YouTube to GitHub": "دانلود از یوتیوب به GitHub",
    "Note: video files are auto-deleted after 7 days": "توجه: فایل‌های ویدیویی بعد از ۷ روز خودکار حذف می‌شوند",
    # --- Auto follow
    "Series: next episode each time": "سریال: هر بار قسمت بعدی",
    "Latest videos": "آخرین ویدیوها",
    "Only new from now on": "فقط جدیدها از این به بعد",
    "From episode number": "از شماره‌ی قسمت",
    "From date": "از تاریخ",
    "Also the last N videos": "N ویدیوی آخر را هم بگیر",
    "Paste the channel link.": "لینک کانال را بچسبان.",
    "Only YouTube and Aparat channels can be followed.": "فقط کانال‌های یوتیوب و آپارات را می‌شود دنبال کرد.",
    "This is a link to one video. Open the CHANNEL page and copy its link (youtube.com/@name or aparat.com/name).":
        "این لینک «یک ویدیو» است. صفحه‌ی کانال را باز کن و لینک آن را بردار (youtube.com/@name یا aparat.com/name).",
    "Series mode needs episode numbers in the titles: use it for YouTube. Aparat: Latest videos.":
        "حالت سریال به شماره‌ی قسمت در عنوان نیاز دارد: برای یوتیوب استفاده کن. آپارات: آخرین ویدیوها.",
    "Give the channel a name.": "برای کانال یک نام بگذار.",
    "Type the episode number to start from.": "شماره‌ی قسمتی که از آن شروع می‌شود را بنویس.",
    "Type how many of the last videos to take now.": "بنویس الان چند ویدیوی آخر گرفته شود.",
    "The shortest length is bigger than the longest.": "کمترین طول از بیشترین طول بیشتر است.",
    "every day": "هر روز",
    "Type the start date like 2026-10-19.": "تاریخ شروع را مثل 2026-10-19 بنویس.",
    "Type the end date like 2026-12-31.": "تاریخ پایان را مثل 2026-12-31 بنویس.",
    "PAUSED": "متوقف",
    "not yet": "هنوز نه",
    "Channel": "کانال",
    "The app checks the channels you follow on a schedule (even when it is closed) and adds new videos to one release per channel. The files of each channel are under Release History (one button per channel).":
        "برنامه کانال‌هایی را که دنبال می‌کنی طبق زمان‌بندی (حتی وقتی بسته است) بررسی می‌کند و ویدیوهای جدید را در یک ریلیز برای هر کانال می‌گذارد. فایل‌های هر کانال در «تاریخچه ریلیزها» است (برای هر کانال یک دکمه).",
    "Series\n(next episode)": "سریال\n(قسمت بعدی)",
    "Latest\nvideos": "آخرین\nویدیوها",
    "Start from episode number (empty = only new episodes from now on)": "شروع از شماره‌ی قسمت (خالی = فقط قسمت‌های جدید از این به بعد)",
    "Ignore videos shorter than (minutes)": "ویدیوهای کوتاه‌تر از این (دقیقه) نادیده گرفته شود",
    "Ignore videos longer than (minutes)": "ویدیوهای بلندتر از این (دقیقه) نادیده گرفته شود",
    "Look for new videos every ... days": "هر ... روز دنبال ویدیوی جدید بگرد",
    "The first time": "بار اول",
    "From": "از",
    "Until": "تا",
    "Most videos started per check": "بیشترین ویدیوی شروع‌شده در هر بررسی",
    "title words": "کلمات عنوان",
    "stop rule": "قانون توقف",
    "filters, stop rules": "فیلترها، قوانین توقف",
    "Title must contain one of these words (comma separated)": "عنوان باید یکی از این کلمه‌ها را داشته باشد (با ویرگول جدا کن)",
    "Title must NOT contain (comma separated)": "عنوان نباید شامل این‌ها باشد (با ویرگول جدا کن)",
    "After this date (2026-12-31)": "بعد از این تاریخ (2026-12-31)",
    "After this many videos": "بعد از این تعداد ویدیو",
    "After this episode number": "بعد از این شماره‌ی قسمت",
    "This looks like the link of ONE video. Open the channel page and copy that link (youtube.com/@name).":
        "این شبیه لینک «یک ویدیو» است. صفحه‌ی کانال را باز کن و آن لینک را بردار (youtube.com/@name).",
    "Gets one new episode at a time, by the number in the title (like 'episode 81'). Videos shorter than the limit below (clips, trailers) are skipped.":
        "هر بار یک قسمت جدید را با شماره‌ی عنوان (مثل «episode 81») می‌گیرد. ویدیوهای کوتاه‌تر از حد پایین (کلیپ، تیزر) رد می‌شوند.",
    "How many of the latest videos?": "چند ویدیوی آخر؟",
    "Days: none picked = every day.": "روزها: هیچ‌کدام انتخاب نشود = هر روز.",
    "Put every check's videos in one zip file": "ویدیوهای هر بررسی در یک فایل زیپ",
    "Only videos uploaded since this date (2026-10-19)": "فقط ویدیوهای بارگذاری‌شده از این تاریخ (2026-10-19)",
    "Stop automatically (all optional):": "توقف خودکار (همه اختیاری):",
    "Aparat channels can be followed with 'Latest videos'.": "کانال‌های آپارات را با «آخرین ویدیوها» می‌شود دنبال کرد.",
    "No files yet. They appear here after the first download finishes.": "هنوز فایلی نیست. بعد از پایان اولین دانلود اینجا می‌آیند.",
    "GitHub token invalid, expired or not allowed to do this.": "توکن GitHub نامعتبر یا منقضی است یا اجازه‌ی این کار را ندارد.",
    "The schedule line was not found in Auto-Follow.yml.": "خط زمان‌بندی در Auto-Follow.yml پیدا نشد.",
    "Schedule not updated: the token cannot change workflow files (it needs the 'workflow' permission). It still wakes up every hour.":
        "زمان‌بندی به‌روز نشد: توکن اجازه‌ی تغییر فایل‌های workflow را ندارد (به دسترسی «workflow» نیاز دارد). هنوز هر ساعت بیدار می‌شود.",
    # --- reports, run labels
    "the app was closed before this video finished": "برنامه پیش از پایان این ویدیو بسته شد",
    "Saved report": "گزارش ذخیره‌شده",
    "YouTube download": "دانلود یوتیوب",
    "YouTube qualities": "کیفیت‌های یوتیوب",
    "YouTube playlist": "پلی‌لیست یوتیوب",
    "Any site": "هر سایت",
    "Series links": "لینک‌های سریال",
    "Google Drive": "گوگل درایو",
    "Google Play": "گوگل پلی",
    "Cleanup": "پاکسازی",
    "Arvan": "آروان",
    "RUNNING": "در حال اجرا",
    "FAILED": "ناموفق",
    "OK": "موفق",
    # --- small screens
    "the amount": "مقدار",
    "the job": "کار",
    "The log is not available yet.\nGitHub can take a little while to provide it. Press Refresh, or use Open on GitHub for the live log.":
        "لاگ هنوز در دسترس نیست.\nGitHub کمی طول می‌کشد تا آن را بدهد. «تازه‌سازی» را بزن یا برای لاگ زنده «باز کردن در GitHub» را بزن.",
    "size ?": "حجم ؟",
    "Only changed files are uploaded, one commit per branch. A backup of the branch is saved first (not for config; last 5 kept). Folders missing from the zip are left untouched.":
        "فقط فایل‌های تغییرکرده آپلود می‌شوند، برای هر برنچ یک کامیت. اول از برنچ بکاپ گرفته می‌شود (برای config نه؛ ۵ بکاپ آخر می‌ماند). پوشه‌هایی که در زیپ نیستند دست نمی‌خورند.",
    "Untick a file to leave it out. Only changed files are uploaded, one commit per branch; the branch is backed up first (not config).":
        "تیک یک فایل را بردار تا کنار گذاشته شود. فقط فایل‌های تغییرکرده آپلود می‌شوند، برای هر برنچ یک کامیت؛ اول از برنچ بکاپ گرفته می‌شود (config نه).",
    "project root": "ریشه‌ی پروژه",
    "(binary or large)": "(باینری یا بزرگ)",
    "(only spaces / line endings differ)": "(فقط فاصله‌ها / پایان خط‌ها فرق دارد)",
    "(new file)": "(فایل جدید)",
    "Type a folder name (no ..).": "نام یک پوشه بنویس (بدون ..).",
    "Use this new folder": "از این پوشه‌ی جدید استفاده کن",
    "It is a new file...": "این یک فایل جدید است...",
    "Other folder...": "پوشه‌ی دیگر...",
    "Ignored (not sent to the repo):": "نادیده گرفته شد (به مخزن فرستاده نمی‌شود):",
    "Read on this phone. Every quality uses the closest available height; for exact codecs use the GitHub list.":
        "روی همین گوشی خوانده شد. هر کیفیت از نزدیک‌ترین ارتفاع موجود استفاده می‌کند؛ برای کدک دقیق فهرست GitHub را بگیر.",
    "Ready to pick quality": "آماده‌ی انتخاب کیفیت",
    "Ready": "آماده",
    "Waiting": "در انتظار",
    "Downloading...": "در حال دانلود...",
    "unknown error": "خطای ناشناخته",
    "Download the APK to your save folder (APK), then install it from here?": "APK را در پوشه‌ی ذخیره‌ات (APK) دانلود کنم و بعد از همین‌جا نصبش کنم؟",
    "Copy Arvan link": "کپی لینک آروان",
    "Copy all Arvan links": "کپی همه‌ی لینک‌های آروان",
    "Arvan link (deleted after 7 days)": "لینک آروان (بعد از ۷ روز حذف می‌شود)",
    "Type the inputs of the workflow, one per line, like:\nurl=https://...\nquality=720\nLeave the box empty for a workflow without inputs. It runs on the app's branch.":
        "ورودی‌های این کار را بنویس، هر خط یکی، مثل:\nurl=https://...\nquality=720\nبرای کاری که ورودی ندارد کادر را خالی بگذار. روی برنچ برنامه اجرا می‌شود.",
    "No saved reports yet. A playlist download saves its report here, so you can check later whether every video was downloaded.":
        "هنوز گزارشی ذخیره نشده. دانلود پلی‌لیست گزارشش را اینجا ذخیره می‌کند تا بعداً ببینی همه‌ی ویدیوها دانلود شده یا نه.",
    "Both": "هر دو",
    "Storage of the plan in GB": "حجم ذخیره‌ی پلن (گیگابایت)",
    "Where new files are kept. Arvan files are deleted after 7 days (free plan: 5 GB storage, 20 GB traffic).":
        "فایل‌های جدید کجا نگه داشته شوند. فایل‌های آروان بعد از ۷ روز حذف می‌شوند (پلن رایگان: ۵ گیگابایت فضا، ۲۰ گیگابایت ترافیک).",
    "The bucket must already exist in that Arvan account. The keys are saved as GitHub secrets and cannot be read back.":
        "باکت باید از قبل در آن حساب آروان وجود داشته باشد. کلیدها به‌صورت Secret در GitHub ذخیره می‌شوند و دوباره خوانده نمی‌شوند.",
    "Traffic left: not available from Arvan's storage API - see the Arvan panel": "ترافیک باقی‌مانده: از API ذخیره‌سازی آروان در دسترس نیست - پنل آروان را ببین",
    "Tap a bucket to make it the preferred one. If it is full, the next one is used.": "یک باکت را لمس کن تا اولویت اول شود. اگر پر شد، بعدی استفاده می‌شود.",
    "this phone": "همین گوشی",
    # --- progress / status messages of the navigator
    "Working...": "در حال کار...",
    "Getting link from this phone's network...": "در حال دریافت لینک از شبکه‌ی همین گوشی...",
    "Saving the bucket keys...": "در حال ذخیره‌ی کلیدهای باکت...",
    "Removing the bucket...": "در حال حذف باکت...",
    "Reading the Arvan buckets (about a minute)...": "در حال خواندن باکت‌های آروان (حدود یک دقیقه)...",
    "Deleting expired Arvan files...": "در حال حذف فایل‌های منقضی آروان...",
    "Updating...": "در حال به‌روزرسانی...",
    "Checking the available formats...": "در حال بررسی فرمت‌های موجود...",
    "Getting the error text...": "در حال گرفتن متن خطا...",
    "Getting the log...": "در حال گرفتن لاگ...",
    "Reading what this run left...": "در حال خواندن خروجی این اجرا...",
    "Saving the log...": "در حال ذخیره‌ی لاگ...",
    "Reading the run...": "در حال خواندن اجرا...",
    "Starting the run again...": "در حال شروع دوباره‌ی اجرا...",
    "Saving the topic...": "در حال ذخیره‌ی موضوع...",
    "Sending...": "در حال ارسال...",
    "Could not open the browser - link copied": "مرورگر باز نشد - لینک کپی شد",
    "The run has not started yet - try again in a few seconds": "اجرا هنوز شروع نشده - چند ثانیه بعد دوباره تلاش کن",
    "Choosing videos works for playlist or channel links": "انتخاب ویدیو فقط برای لینک پلی‌لیست یا کانال کار می‌کند",
    "Failed": "ناموفق",
    "Open in downloader": "باز کردن در دانلودر",
    "Copy names list": "کپی فهرست نام‌ها",
    "Refresh links": "تازه‌سازی لینک‌ها",
    "Refresh link": "تازه‌سازی لینک",
    "Refreshing links...": "در حال تازه‌سازی لینک‌ها...",
    "Refreshing link...": "در حال تازه‌سازی لینک...",
    "this field": "این فیلد",
    "A zip with main/ and config/ folders must be chosen on its own.": "زیپ دارای پوشه‌های main/ و config/ را باید تنها انتخاب کنی.",
    "Started, but the run did not show up yet. Open the runs list in a few seconds.": "شروع شد ولی اجرا هنوز دیده نمی‌شود. چند ثانیه بعد فهرست اجراها را باز کن.",
    "Started, but the new run did not show up yet. Open the runs list in a few seconds.": "شروع شد ولی اجرای تازه هنوز دیده نمی‌شود. چند ثانیه بعد فهرست اجراها را باز کن.",
    "Started. Open the runs list in a few seconds.": "شروع شد. چند ثانیه بعد فهرست اجراها را باز کن.",
    "Copied - paste it in the chat.": "کپی شد - در چت بچسبان.",
    "This run's inputs could not be read. Check them and press Run.": "ورودی‌های این اجرا خوانده نشد. بررسی کن و «Run» را بزن.",
    "Could not detect the zip workflow run. It may still be running.": "اجرای کار زیپ پیدا نشد. شاید هنوز در حال اجراست.",
    "GitHub token invalid or expired. Update it and retry.": "توکن GitHub نامعتبر یا منقضی است. آن را به‌روز کن و دوباره تلاش کن.",
    "Could not detect the workflow run. It may still be running on GitHub Actions.": "اجرای کار پیدا نشد. شاید هنوز روی GitHub Actions در حال اجراست.",
    "The check finished but no format list was found in the log. Is Any-Site-Upload.yml the new version (with the 'check' option)?":
        "بررسی تمام شد ولی فهرست فرمت‌ها در لاگ پیدا نشد. آیا Any-Site-Upload.yml نسخه‌ی جدید (با گزینه‌ی «check») است؟",
    "The topic needs 6-64 letters, digits, - or _ (no spaces).": "موضوع باید ۶ تا ۶۴ حرف، رقم، - یا _ باشد (بدون فاصله).",
    "Type or generate a topic first.": "اول یک موضوع بنویس یا بساز.",
    "GitHub token invalid, expired or not allowed to write to the config branch.": "توکن GitHub نامعتبر یا منقضی است یا اجازه‌ی نوشتن در برنچ config را ندارد.",
    # --- Health page
    "YouTube downloads (cookies, avoids the bot check)": "دانلود یوتیوب (کوکی، جلوگیری از بررسی ربات)",
    "Google Play APK download": "دانلود APK از گوگل پلی",
    "Telegram download": "دانلود از تلگرام",
    "Any site (cookies, optional)": "هر سایت (کوکی، اختیاری)",
    "Any site (proxy, optional)": "هر سایت (پروکسی، اختیاری)",
    "Build APK (signing)": "ساخت APK (امضا)",
    "Arvan storage": "ذخیره‌سازی آروان",
    "Workflows": "کارها (Workflows)",
    "Secrets": "Secretها",
    "No token is saved on this phone.": "هیچ توکنی روی این گوشی ذخیره نشده.",
    "Settings: paste a token, or use Sign in with GitHub.": "ستینگ: یک توکن بچسبان یا «ورود با GitHub» را بزن.",
    "The token can read the repo but not write to it: running workflows and updates need write access.": "توکن می‌تواند مخزن را بخواند ولی در آن بنویسد نه: اجرای کارها و به‌روزرسانی به دسترسی نوشتن نیاز دارد.",
    "Settings > Update project: send the update zip again, or add the missing file(s) to .github/workflows.": "ستینگ > به‌روزرسانی پروژه: زیپ به‌روزرسانی را دوباره بفرست یا فایل‌های جاافتاده را در .github/workflows بگذار.",
    "Add the missing Secrets only for the tools you use: repo Settings > Secrets and variables > Actions.": "Secretهای جاافتاده را فقط برای ابزارهایی که استفاده می‌کنی اضافه کن: تنظیمات مخزن > Secrets and variables > Actions.",
    "The repo is public: Actions minutes are free and not counted.": "مخزن عمومی است: دقیقه‌های Actions رایگان است و حساب نمی‌شود.",
    "Not available with this token.": "با این توکن در دسترس نیست.",
    "It needs a classic token with the 'user' scope. You can also see it at github.com/settings/billing.": "به توکن classic با دسترسی «user» نیاز دارد. می‌توانی آن را در github.com/settings/billing هم ببینی.",
    "Almost out: runs will stop or cost money. Wait for the new month, or make the repo public.": "تقریباً تمام شده: اجراها متوقف می‌شوند یا هزینه دارند. منتظر ماه جدید بمان یا مخزن را عمومی کن.",
    "Getting close to the monthly limit: avoid big downloads for now.": "نزدیک سقف ماهانه است: فعلاً دانلود بزرگ نکن.",
    "The token is invalid, expired, or has no access to this repo.": "توکن نامعتبر یا منقضی است یا به این مخزن دسترسی ندارد.",
    "Settings: save a new token (or sign in with GitHub again).": "ستینگ: توکن جدید ذخیره کن (یا دوباره با GitHub وارد شو).",
    "Could not reach GitHub (no connection?).": "به GitHub وصل نشد (اینترنت قطع است؟).",
    "Check the internet connection and press Refresh.": "اینترنت را بررسی کن و «تازه‌سازی» را بزن.",
    "Press Refresh in a minute.": "یک دقیقه‌ی دیگر «تازه‌سازی» را بزن.",
    "The branch 'config' does not exist.": "برنچ «config» وجود ندارد.",
    "It holds config.json (buttons, error help) and ntfy.json. Create it from the Settings update.": "config.json (دکمه‌ها، راهنمای خطا) و ntfy.json در آن است. آن را با به‌روزرسانی ستینگ بساز.",
    "Could not read the workflow list (token).": "فهرست کارها (Workflows) خوانده نشد (توکن).",
    "See the token check above.": "بررسی توکن بالا را ببین.",
    "Press Refresh.": "«تازه‌سازی» را بزن.",
    "This token cannot read the repo's Secrets.": "این توکن نمی‌تواند Secretهای مخزن را بخواند.",
    "Use a classic token with the 'repo' scope (or a GitHub App with 'Secrets: Read').": "از توکن classic با دسترسی «repo» استفاده کن (یا GitHub App با «Secrets: Read»).",
    "Other Secrets:": "Secretهای دیگر:",
    "The token must belong to (or be allowed on) this repo.": "توکن باید مال این مخزن باشد (یا روی آن اجازه داشته باشد).",
    "The token has expired.": "توکن منقضی شده است.",
    "Settings: save a new token.": "ستینگ: توکن جدید ذخیره کن.",
    "It expires soon: create a new token and save it in Settings.": "به‌زودی منقضی می‌شود: توکن جدید بساز و در ستینگ ذخیره کن.",
    "This branch does not exist in the repo.": "این برنچ در مخزن وجود ندارد.",
    "Another quality": "کیفیت دیگر",
    "CHECK": "بررسی",
    "PROBLEM": "مشکل",
    "INFO": "اطلاعات",
}

MORE_PATTERNS = [
    (r"Telegram bot files - page (\d+) \((\d+) files\)", "فایل‌های ربات تلگرام - صفحه {0} ({1} فایل)"),
    (r"Could not load the bot files: (.+)", "فایل‌های ربات خوانده نشد: {0}"),
    (r"Quality: (.+)", "کیفیت: {0}"),
    (r"Android (\d+)", "اندروید {0}"),
    (r"Last (\d+) videos", "{0} ویدیوی آخر"),
    (r"Last (\d+) days?", "{0} روز اخیر"),
]

# (English piece, Persian) - the longest piece is tried first; only whole words are replaced.
PHRASES = [
    ("Could not open the folder picker:", "باز کردن انتخاب‌گر پوشه ممکن نشد:"),
    ("Could not open the file picker:", "باز کردن انتخاب‌گر فایل ممکن نشد:"),
    ("Could not read the file:", "خواندن فایل ممکن نشد:"),
    ("Could not keep access to the folder:", "دسترسی به پوشه نگه داشته نشد:"),
    ("Open the APK from the Files app:", "APK را از برنامه‌ی فایل‌ها باز کن:"),
    ("Open the APK from the Files app.", "APK را از برنامه‌ی فایل‌ها باز کن."),
    ("Could not open the installer:", "نصب‌کننده باز نشد:"),
    ("Open the file from the Files app:", "فایل را از برنامه‌ی فایل‌ها باز کن:"),
    ("Share the file from the Files app:", "فایل را از برنامه‌ی فایل‌ها به اشتراک بگذار:"),
    ("Could not open the file:", "باز کردن فایل ممکن نشد:"),
    ("Open it from the Files app.", "آن را از برنامه‌ی فایل‌ها باز کن."),
    ("Could not share the file:", "اشتراک فایل ممکن نشد:"),
    ("Last check:", "آخرین بررسی:"),
    ("FINISHED:", "پایان‌یافته:"),
    ("Last episode fetched:", "آخرین قسمت دریافت‌شده:"),
    ("Videos started so far:", "ویدیوهای شروع‌شده تا الان:"),
    ("Last video:", "آخرین ویدیو:"),
    ("Last problem:", "آخرین مشکل:"),
    ("Files go to the release:", "فایل‌ها به این ریلیز می‌روند:"),
    ("latest, every", "آخرین‌ها، هر"),
    ("(Iran time)", "(به وقت ایران)"),
    ("per check", "در هر بررسی"),
    ("h left", "ساعت مانده"),
    ("days left", "روز مانده"),
    ("is too large (", "بیش از حد بزرگ است ("),
    (": enter a whole number", ": یک عدد صحیح وارد کن"),
    ("must be from 1 to", "باید از 1 تا"),
    ("is not in the repo, but it looks like:", "در مخزن نیست، ولی شبیه این است:"),
    ("exists in several places. Which one?", "در چند جا هست. کدام؟"),
    ("is a new file. Where should it go?", "فایل جدید است. کجا برود؟"),
    ("file(s) below still need a choice.", "فایل پایین هنوز به انتخاب نیاز دارد."),
    ("Same as the repo, nothing to do (", "مثل مخزن است، کاری لازم نیست ("),
    ("Will replace (", "جایگزین می‌شود ("),
    ("Replace", "جایگزین"),
    ("Put in", "قرار بده در"),
    ("No problems,", "مشکلی نیست،"),
    ("to look at", "مورد برای بررسی"),
    ("to fix", "مورد برای رفع"),
    ("What to do:", "چه کار کنم:"),
    ("- page", "- صفحه"),
    ("selected release(s)?", "ریلیز انتخاب‌شده؟"),
    ("releases shown?", "ریلیز نمایش‌داده‌شده؟"),
    ("Yes, delete all", "بله، همه حذف شود"),
    ("Delete the", "حذف"),
    ("Delete all", "حذف همه‌ی"),
    ("Copied", "کپی شد"),
    ("Sharing", "در حال اشتراک"),
    ("Share not available - copied", "اشتراک ممکن نیست - کپی شد"),
    ("Zipping:", "در حال زیپ:"),
    ("link(s) ready", "لینک آماده است"),
    ("- nearest quality used for", "- نزدیک‌ترین کیفیت استفاده شد برای"),
    ("file(s) in", "فایل در"),
    ("Log copied (", "لاگ کپی شد ("),
    ("Log saved:", "لاگ ذخیره شد:"),
    ("ready -", "آماده -"),
    ("Finished:", "پایان:"),
    ("Failed (", "ناموفق ("),
    ("videos found. Choose quality for ALL:", "ویدیو پیدا شد. کیفیت همه را انتخاب کن:"),
    ("selected video(s). Choose quality:", "ویدیوی انتخاب‌شده. کیفیت را انتخاب کن:"),
    ("Storage note:", "یادداشت ذخیره‌سازی:"),
    ("files, deleted after 7 days)", "فایل، بعد از ۷ روز حذف می‌شوند)"),
    ("Arvan links (", "لینک‌های آروان ("),
    ("- started", "- شروع شد"),
    ("Remove the bucket \"", "باکت «"),
    ("\" from the app?\nIts keys are deleted from the GitHub secrets. Files already on Arvan stay there until the daily cleanup.",
     "» از برنامه حذف شود؟\nکلیدهای آن از Secretهای GitHub پاک می‌شود. فایل‌های موجود در آروان تا پاکسازی روزانه می‌مانند."),
    ("Files in the bucket:", "فایل‌های باکت:"),
    ("(from this app:", "(از همین برنامه:"),
    ("Could not read it:", "خوانده نشد:"),
    ("Used:", "مصرف‌شده:"),
    ("Free:", "آزاد:"),
    ("Could not fetch status:", "وضعیت دریافت نشد:"),
    ("The check failed (", "بررسی ناموفق بود ("),
    ("Checking formats (", "در حال بررسی فرمت‌ها ("),
    ("Error:", "خطا:"),
    ("Could not start sign-in:", "شروع ورود ممکن نشد:"),
    ("Network error while fetching the link:", "خطای شبکه هنگام گرفتن لینک:"),
    ("Network error:", "خطای شبکه:"),
    ("Could not fetch qualities (", "کیفیت‌ها دریافت نشد ("),
    ("The phone could not read the qualities (", "گوشی نتوانست کیفیت‌ها را بخواند ("),
    ("). Use the GitHub button.", "). دکمه‌ی GitHub را بزن."),
    ("Download failed (", "دانلود ناموفق بود ("),
    ("Download failed:", "دانلود ناموفق بود:"),
    ("The link above still works.", "لینک بالا هنوز کار می‌کند."),
    ("Downloading to", "در حال دانلود در"),
    ("Saved:", "ذخیره شد:"),
    ("Size:", "حجم:"),
    ("failed (", "ناموفق ("),
    (", total", "، مجموع"),
    ("Schedule updated (", "زمان‌بندی به‌روز شد ("),
    ("wake-ups a day).", "بیدارشدن در روز)."),
    ("Schedule already up to date (", "زمان‌بندی از قبل به‌روز است ("),
    ("Schedule not updated:", "زمان‌بندی به‌روز نشد:"),
    ("Action failed (", "عمل ناموفق بود ("),
    ("Delete failed:", "حذف ناموفق بود:"),
    ("Rename failed:", "تغییر نام ناموفق بود:"),
    ("Zip failed (", "زیپ ناموفق بود ("),
    ("Zip failed:", "زیپ ناموفق بود:"),
    ("Deleted", "حذف شد"),
    ("Deleting", "در حال حذف"),
    ("Valid. Repo:", "معتبر. مخزن:"),
    ("minutes used this month", "دقیقه در این ماه مصرف شده"),
    ("of about", "از حدود"),
    ("included (", "رایگان ("),
    ("workflows the app uses are in the repo.", "کاری که برنامه استفاده می‌کند در مخزن است."),
    ("known Secrets are set.", "Secret شناخته‌شده تنظیم شده است."),
    ("Expires in", "منقضی می‌شود در"),
    ("GitHub answered HTTP", "GitHub پاسخ داد HTTP"),
    ("The repo", "مخزن"),
    ("was not found with this token.", "با این توکن پیدا نشد."),
    ("is needed because Storage is set to use Arvan", "لازم است چون ذخیره‌سازی روی آروان تنظیم شده"),
    ("Could not check:", "بررسی نشد:"),
    ("Health check failed:", "بررسی سلامت ناموفق بود:"),
    ("Could not read the workflow list:", "فهرست کارها خوانده نشد:"),
    ("Could not read the Secrets:", "Secretها خوانده نشدند:"),
    ("Branch:", "برنچ:"),
    ("Version", "نسخه"),
]

from core.fa_strings_msgs import MSG_EXACT, MSG_PHRASES   # noqa: E402
MORE_EXACT.update(MSG_EXACT)
MORE_EXACT.update({
    "Telegram bot files": "فایل‌های ربات تلگرام",
    "outputs of the Telegram bot": "خروجی‌های ربات تلگرام",
    ("No access to the Telegram bot repo (aparat-bot). "
     "Install the YT Bridge Auth app on it (Contents + Actions)."):
        "دسترسی به ریپوی ربات تلگرام (aparat-bot) نیست. برنامه YT Bridge Auth را روی آن نصب کن (Contents و Actions).",
})
PHRASES.extend(MSG_PHRASES)


MORE_EXACT.update({
    "Site log": "گزارش سایت‌ها",
    "Site log (which sites work)": "گزارش سایت‌ها (کدام سایت کار می‌کند)",
    "Loading the site log...": "در حال خواندن گزارش سایت‌ها...",
    "Checking the site history...": "در حال بررسی سابقه سایت...",
    "This site failed before": "این سایت قبلاً خطا داده است",
    "Run it anyway?": "با این حال اجرا شود؟",
    "Yes, run anyway": "بله، اجرا کن",
    "No, go back": "نه، برگرد",
    "Works": "کار می‌کند",
    "Sometimes works": "گاهی کار می‌کند",
    "Never worked": "تا حالا کار نکرده",
    "Not sure yet": "هنوز مشخص نیست",
    "No sites recorded yet. Every Any site run adds its link here.":
        "هنوز سایتی ثبت نشده. هر بار که «Any site» اجرا شود، اینجا ثبت می‌شود.",
    "Sites that ran through Any site (success = file over 10 MB).":
        "سایت‌هایی که با «Any site» اجرا شده‌اند (موفق = فایل بیشتر از ۱۰ مگابایت).",
    "Could not read the site log.": "گزارش سایت‌ها خوانده نشد.",
})
MORE_PATTERNS.extend([
    (r"Failed (\d+) time\(s\), worked 0 times\.", "{0} بار ناموفق بوده، هیچ‌بار موفق نبوده."),
    (r"Last problem: (.+)", "آخرین مشکل: {0}"),
    (r"worked (\d+)  ·  under 10 MB (\d+)  ·  failed (\d+)", "موفق {0}  ·  زیر ۱۰ مگ {1}  ·  ناموفق {2}"),
    (r"Unclear: (\d+)", "نامشخص: {0}"),
    (r"Last: (\d{4}-\d{2}-\d{2})", "آخرین: {0}"),
    (r"Could not read the site log: (.+)", "گزارش سایت‌ها خوانده نشد: {0}"),
])


MORE_EXACT.update({
    "Build automatically after the update": "بیلد خودکار بعد از آپدیت",
    "Download automatically after the build": "دانلود خودکار بعد از بیلد",
    "Install automatically after the download": "نصب خودکار بعد از دانلود",
    "Show the build": "نمایش بیلد",
    "The build started by itself (about 15-30 minutes). It keeps going if you leave this screen.":
        "بیلد خودکار شروع شد (حدود ۱۵ تا ۳۰ دقیقه). اگر از این صفحه بیرون بروی ادامه پیدا می‌کند.",
    "The APK is downloaded. Open the app to install it.": "APK دانلود شد. برای نصب، اپ را باز کن.",
})


MORE_EXACT.update({
    "Channel or page videos (latest / most viewed)": "ویدیوهای کانال یا صفحه (آخرین / پربازدیدترین)",
    "YouTube channel or page link (youtube.com/@name)": "لینک کانال یا صفحه یوتیوب (youtube.com/@name)",
    "How many videos (1-500)": "تعداد ویدیو (۱ تا ۵۰۰)",
    "Choose from latest videos": "انتخاب از آخرین ویدیوها",
    "Choose from most viewed videos": "انتخاب از پربازدیدترین ویدیوها",
    "Enter a channel or page link": "لینک کانال یا صفحه را وارد کن",
    "Only YouTube channel or page links work here": "اینجا فقط لینک کانال یا صفحه یوتیوب کار می‌کند",
    "That is ONE video. Paste the channel or page link (youtube.com/@name)": "این لینک یک ویدیو است. لینک کانال یا صفحه را بچسبان (youtube.com/@name)",
    "Type how many videos: a number from 1 to 500": "تعداد ویدیو را بنویس: عددی از ۱ تا ۵۰۰",
})


MORE_EXACT.update({
    "Job failed": "کار ناموفق بود",
    "APK build finished": "بیلد APK تمام شد",
    "Project backup finished": "بکاپ پروژه تمام شد",
    "Qualities are ready": "کیفیت‌ها آماده است",
    "Playlist finished": "پلی‌لیست تمام شد",
    "Finished - tap to see the result": "تمام شد - برای دیدن نتیجه بزن",
})


MORE_EXACT.update({
    "APK builds": "ساخت‌های APK",
    "Cancel run": "لغو اجرا",
    "Cancelling the run...": "در حال لغو اجرا...",
})

MORE_EXACT.update({
    "YouTube link (video, playlist or channel)": "لینک یوتیوب (ویدیو، پلی‌لیست یا کانال)",
    "Paste a YouTube link: a video, a playlist or a channel": "یک لینک یوتیوب بچسبان: ویدیو، پلی‌لیست یا کانال",
    "This is not a YouTube link": "این لینک یوتیوب نیست",
    "Video link detected": "لینک ویدیو شناسایی شد",
    "Playlist link detected": "لینک پلی‌لیست شناسایی شد",
    "Channel or page link detected": "لینک کانال یا صفحه شناسایی شد",
    "More from this video's channel (latest / most viewed)": "ویدیوهای بیشتر از کانال این ویدیو (آخرین / پربازدیدترین)",
    "Finding the channel of this video...": "در حال پیدا کردن کانال این ویدیو...",
    "Could not find the channel of this video": "کانال این ویدیو پیدا نشد",
})


MORE_EXACT.update({
    "APK builds and backups": "ساخت‌های APK و بکاپ‌ها",
})


MORE_EXACT.update({
    # --- Proxy / v2ray config (Settings) and Any site (phone)
    "Proxy / v2ray config (for Any site)": "پروکسی / کانفیگ v2ray (برای Any site)",
    "Proxy / v2ray config": "پروکسی / کانفیگ v2ray",
    "Many sites block GitHub's IP. With a config saved here, Any site reads the page through it (only the page; the video itself is downloaded directly). Supported: vless / vmess / trojan / ss links (one per line), a subscription link, or a full Xray JSON. When a config is set, the free proxy list is not used. The config is saved as a GitHub secret and cannot be read back.":
        "خیلی از سایت‌ها آی‌پی گیت‌هاب را مسدود می‌کنند. با کانفیگی که اینجا ذخیره کنی، Any site صفحه را از طریق آن می‌خواند (فقط خود صفحه؛ خود ویدیو مستقیم دانلود می‌شود). پشتیبانی: لینک‌های vless / vmess / trojan / ss (هر خط یکی)، لینک اشتراک، یا JSON کامل Xray. وقتی کانفیگ پر باشد، لیست پروکسی رایگان استفاده نمی‌شود. کانفیگ به صورت Secret گیت‌هاب ذخیره می‌شود و دوباره قابل خواندن نیست.",
    "Checking what is saved...": "در حال بررسی چیزی که ذخیره شده...",
    "Could not read what is saved.": "خواندن چیزی که ذخیره شده ممکن نشد.",
    "A v2ray config is saved.": "یک کانفیگ v2ray ذخیره شده است.",
    "No v2ray config is saved.": "هیچ کانفیگ v2ray ذخیره نشده است.",
    "Paste vless:// vmess:// trojan:// ss:// links, a subscription link or Xray JSON": "لینک‌های vless:// vmess:// trojan:// ss://، لینک اشتراک یا JSON ی Xray را بچسبان",
    "Save config": "ذخیره کانفیگ",
    "Replace the saved config": "جایگزین کردن کانفیگ ذخیره‌شده",
    "Delete the saved config": "حذف کانفیگ ذخیره‌شده",
    "Saving the config...": "در حال ذخیره‌ی کانفیگ...",
    "Deleting the config...": "در حال حذف کانفیگ...",
    "Config saved": "کانفیگ ذخیره شد",
    "Config deleted": "کانفیگ حذف شد",
    "Paste a config first.": "اول یک کانفیگ بچسبان.",
    "This JSON is not valid.": "این JSON معتبر نیست.",
    "No vless:// vmess:// trojan:// ss:// link or subscription link was found.": "هیچ لینک vless:// vmess:// trojan:// ss:// یا لینک اشتراکی پیدا نشد.",
    "This config is too long for a GitHub secret.": "این کانفیگ برای Secret گیت‌هاب خیلی طولانی است.",
    "Reading the links on this phone...": "در حال خواندن لینک‌ها با گوشی...",
    "No link was found on this phone.": "هیچ لینکی روی این گوشی پیدا نشد.",
    "\n\nIf the site gives video and audio separately, or blocks this phone, use the Any site button (GitHub) instead.":
        "\n\nاگر سایت تصویر و صدا را جدا می‌دهد یا این گوشی را مسدود کرده، از دکمه‌ی Any site (گیت‌هاب) استفاده کن.",
    "Any site (phone)": "Any site (با گوشی)",
    "Proxy (optional)": "پروکسی (اختیاری)",
    "socks5://ip:port - only for reading the page": "socks5://ip:port - فقط برای خواندن صفحه",
    "v2ray config (optional)": "کانفیگ v2ray (اختیاری)",
    "Empty = the config saved in Settings": "خالی = کانفیگ ذخیره‌شده در تنظیمات",
    "Find free proxies": "پیدا کردن پروکسی رایگان",
    "How many working proxies to find": "چند پروکسی سالم پیدا شود",
})


MORE_EXACT.update({
    "How to read the page": "صفحه چطور خوانده شود",
    "Auto": "خودکار",
    "GitHub IP": "آی‌پی گیت‌هاب",
    "Proxy": "پروکسی",
    "v2ray": "v2ray",
})

MORE_EXACT.update({
    "Paste any link here": "هر لینکی را اینجا بچسبان",
    "Go": "برو",
    "Paste a link first": "اول یک لینک بچسبان",
})

MORE_EXACT.update({
    "Check for update": "بررسی نسخه‌ی جدید",
    "Checking...": "در حال بررسی...",
    "Could not check for updates.": "بررسی نسخه ممکن نشد.",
})
MORE_PATTERNS.extend([
    (r"Version (.+) is on GitHub \(you have (.+)\)\. Build the new APK from Settings > App tools\.",
     "نسخه {0} در GitHub هست (نسخه‌ی شما {1}). APK جدید را از تنظیمات > ابزارهای برنامه بساز."),
    (r"You have the latest version \((.+)\)\.", "شما آخرین نسخه ({0}) را دارید."),
    (r"This build \((.+)\) is newer than main \((.+)\)\.", "این بیلد ({0}) از main ({1}) جلوتر است."),
    (r"Could not compare versions \((.+) / (.+)\)\.", "مقایسه‌ی نسخه‌ها ممکن نشد ({0} / {1})."),
])


# --- file deadlines (Release History > File deadlines), date format
MORE_EXACT.update({
    "File deadlines": "مهلت فایل‌ها",
    "when each file is deleted": "زمان حذف هر فایل",
    "Files are deleted by a daily cleanup. Extend adds days to a file's deletion date (or keeps it forever).":
        "فایل‌ها با یک پاک‌سازی روزانه حذف می‌شوند. تمدید چند روز به تاریخ حذف فایل اضافه می‌کند (یا آن را برای همیشه نگه می‌دارد).",
    "Could not load the deadlines": "بارگذاری مهلت‌ها ممکن نشد",
    "Extend": "تمدید",
    "Extending...": "در حال تمدید...",
    "Add days to the deletion date": "چند روز به تاریخ حذف اضافه کن",
    "Number of days": "تعداد روز",
    "Add days": "اضافه کن",
    "Keep forever": "برای همیشه نگه دار",
    "Date format": "قالب تاریخ",
    "Choose how dates are shown": "نحوه نمایش تاریخ را انتخاب کن",
    "Gregorian": "میلادی",
    "Jalali (Shamsi)": "شمسی (جلالی)",
    "Every date in the app (releases, runs, deadlines) follows this choice. Times are Tehran time.":
        "همه‌ی تاریخ‌های برنامه (ریلیزها، اجراها، مهلت‌ها) از این انتخاب پیروی می‌کنند. ساعت‌ها به وقت تهران است.",
    "No access to the Telegram bot repo (aparat-bot).": "دسترسی به مخزن ربات تلگرام (aparat-bot) نیست.",
})
MORE_PATTERNS.extend([
    (r"File deadlines \((\d+) files\)", "مهلت فایل‌ها ({0} فایل)"),
    (r"Extend all (\d+) files?", "تمدید همه ({0} فایل)"),
    (r"Extend (\d+) files?", "تمدید {0} فایل"),
    (r"\+(\d+) days", "+{0} روز"),
    (r"Auto follow: (.+)", "دنبال‌کردن خودکار: {0}"),
])
PHRASES.extend([
    ("Less than 1 day left", "کمتر از ۱ روز مانده"),
    ("days left", "روز مانده"),
    ("day left", "روز مانده"),
    ("Due for deletion", "به‌زودی حذف می‌شود"),
    ("Kept forever", "برای همیشه نگه داشته می‌شود"),
    ("No time limit", "بدون محدودیت زمانی"),
    ("Extend failed:", "تمدید ناموفق بود:"),
    ("Could not load the deadlines:", "بارگذاری مهلت‌ها ممکن نشد:"),
    ("Extend", "تمدید"),
    ("Gregorian", "میلادی"),
    ("Jalali (Shamsi)", "شمسی (جلالی)"),
])

# --- Lab list: titles and descriptions of the Lab tools (the Lab tools' own screens are translated by lab/lib/lab_fa.py)
MORE_EXACT.update({
    "Hello Lab (example)": "سلام آزمایشگاه (نمونه)",
    "Example: menus, sub-menus, input, choices, background work, saved values.": "نمونه: منو، زیرمنو، ورودی، انتخاب، کار پس‌زمینه، مقدارهای ذخیره‌شده.",
    "Mornye (lab copy)": "مورنیه (کپی آزمایشگاه)",
    "Copy of Mornye from link. The app's own Mornye is untouched; sessions are shared, settings are separate.": "کپی مورنیه از لینک. مورنیه‌ی خود اپ دست‌نخورده می‌ماند؛ نشست‌ها مشترک و تنظیم‌ها جدا هستند.",
    "Link Lab (any site, copy of link_downloader)": "آزمایشگاه لینک (هر سایت، کپی link_downloader)",
    "Get links / download any site through yt-dlp, with free proxies or v2ray. Uses the lab-links, lab-download and lab-find-proxies workflows; the app's own tools are untouched.": "گرفتن لینک / دانلود از هر سایت با yt-dlp، با پروکسی رایگان یا v2ray. ورک‌فلوهای lab-links و lab-download و lab-find-proxies را استفاده می‌کند؛ ابزارهای خود اپ دست‌نخورده‌اند.",
    "Copy tools (safe copy to edit)": "ابزار کپی (نسخه‌ی امن برای ویرایش)",
    "Copy a main workflow or a config plugin to the lab branch, edit the copy, run it from lab, or discard it. The originals are never touched.": "یک ورک‌فلوی main یا یک پلاگین config را به برنچ lab کپی کن، کپی را ویرایش کن، از lab اجرا کن یا دورش بینداز. نسخه‌های اصلی هرگز دست نمی‌خورند.",
    "Page Sniffer (get m3u8 with my login)": "شنودگر صفحه (گرفتن m3u8 با ورود خودم)",
    "Open a series/movie page in an in-app browser, log in with your account, press play: the tool catches the .m3u8 link. Then copy it or send it to lab-download (same as Link Lab).": "صفحه‌ی یک سریال/فیلم را در مرورگر داخل اپ باز کن، با حساب خودت وارد شو، پخش را بزن: ابزار لینک .m3u8 را می‌گیرد. بعد کپی‌اش کن یا به lab-download بفرست (مثل آزمایشگاه لینک).",
    "Promote tool to Download Anything": "انتقال ابزار به دانلود از هر جا",
    "Move a tested Lab tool to Download Anything (config branch + main workflows) with no build: dry-run preview, one commit per branch, Rollback.": "ابزار آزمایش‌شده‌ی آزمایشگاه را بدون بیلد به دانلود از هر جا منتقل کن (برنچ config + ورک‌فلوهای main): پیش‌نمایش آزمایشی، یک کامیت برای هر برنچ، بازگردانی.",
    "Add workflow (link or paste)": "افزودن ورک‌فلو (لینک یا چسباندن)",
})
PHRASES.extend([
    ("[imported]", "[وارد‌شده]"),
    ("Imported workflow", "ورک‌فلوی واردشده"),
    ("Run, Check and a copyable error report inside; edit the workflow on the lab branch.", "اجرا، بررسی و گزارش خطای قابل‌کپی داخلش هست؛ ورک‌فلو را روی برنچ lab ویرایش کن."),
])

MORE_EXACT.update({
    # --- update 8: About screen, update download
    "Looking for the APK...": "در حال جستجوی APK...",
    "The update is downloaded. Press Install.": "به‌روزرسانی دانلود شد. نصب را بزن.",
    "Download update": "دانلود به‌روزرسانی",
    "The APK of this version is not ready yet.": "APK این نسخه هنوز آماده نیست.",
})
MORE_PATTERNS.extend([
    (r"Version (.+) is on GitHub \(you have (.+)\)\.", "نسخه‌ی {0} روی گیت‌هاب است (شما {1} دارید)."),
    (r"Download update \((.+)\)", "دانلود به‌روزرسانی ({0})"),
    (r"Downloading the update\.\.\. (\d+)%", "در حال دانلود به‌روزرسانی... {0}٪"),
    (r"Download failed: (.+)", "دانلود ناموفق بود: {0}"),
])


MORE_EXACT.update({
    "Browser": "مرورگر",
    "Search or type a link": "جستجو یا نوشتن لینک",
    "Go": "برو",
    "Reload": "بارگذاری دوباره",
    "Close": "بستن",
    "Videos on this page": "ویدیوهای این صفحه",
    "Back to browser": "بازگشت به مرورگر",
    "Select all": "انتخاب همه",
    "Try this page on GitHub (Any site)": "امتحان این صفحه روی GitHub (هر سایت)",
    "Reading the qualities on this phone...": "در حال خواندن کیفیت‌ها روی همین گوشی...",
    "Tap the files you want first": "اول فایل‌های دلخواه را لمس کن",
    "No video found yet. Start playing the video on the page, then tap the badge again.":
        "هنوز ویدیویی پیدا نشد. ویدیو را در صفحه پخش کن و دوباره روی نشانگر بزن.",
    "The browser works only on the phone (Android).": "مرورگر فقط روی گوشی (اندروید) کار می‌کند.",
    "Open a page first": "اول یک صفحه را باز کن",
})


# --- update 8: compact Downloads page (tabs, menu, group delete)
MORE_EXACT.update({
    "+ Add link": "+ افزودن لینک",
    "Finished": "تمام‌شده",
    "Downloading": "در حال دانلود",
    "Failed": "ناموفق",
    "\u25cf All": "\u25cf همه",
    "\u25cf Downloading": "\u25cf در حال دانلود",
    "\u25cf Finished": "\u25cf تمام‌شده",
    "\u25cf Failed": "\u25cf ناموفق",
    "Delete file": "حذف فایل",
    "Delete files": "حذف فایل‌ها",
    "Remove from list": "حذف از فهرست",
    "Remove from list only": "فقط از فهرست حذف شود",
    "Tap a file to select it first": "اول یک فایل را لمس کن تا انتخاب شود",
})
MORE_PATTERNS.extend([
    (r"All \((\d+)\)", "همه ({0})"),
    (r"Downloading \((\d+)\)", "در حال دانلود ({0})"),
    (r"Finished \((\d+)\)", "تمام‌شده ({0})"),
    (r"Failed \((\d+)\)", "ناموفق ({0})"),
    (r"\u25cf All \((\d+)\)", "\u25cf همه ({0})"),
    (r"\u25cf Downloading \((\d+)\)", "\u25cf در حال دانلود ({0})"),
    (r"\u25cf Finished \((\d+)\)", "\u25cf تمام‌شده ({0})"),
    (r"\u25cf Failed \((\d+)\)", "\u25cf ناموفق ({0})"),
    (r"Deleting (\d+) file\(s\)\.\.\.", "در حال حذف {0} فایل..."),
    (r"Deleted (\d+) file\(s\), (\d+) already gone", "{0} فایل حذف شد، {1} قبلاً حذف شده بود"),
    (r"Deleted (\d+) file\(s\)", "{0} فایل حذف شد"),
    (r"Removed (\d+) from the list \(files stay\)", "{0} مورد از فهرست حذف شد (فایل‌ها می‌مانند)"),
    (r"Delete the (\d+) selected files from the phone\?\nThis cannot be undone\.",
     "{0} فایل انتخاب‌شده از گوشی حذف شود؟\nاین کار برگشت‌پذیر نیست."),
    (r"Delete this file from the phone\?\n(.+)\nThis cannot be undone\.",
     "این فایل از گوشی حذف شود؟\n{0}\nاین کار برگشت‌پذیر نیست."),
])


# --- update 9: Phone / Release switch, on-phone badge, duplicate warning, release delete, folders
MORE_EXACT.update({
    "Phone": "گوشی",
    "\u25cf Phone": "\u25cf گوشی",
    "\u25cf Release": "\u25cf ریلیز",
    "Release": "ریلیز",
    "Tools": "ابزارها",
    "On phone": "روی گوشی",
    "Download again": "دانلود دوباره",
    "Download all again": "همه را دوباره دانلود کن",
    "Nothing to download": "چیزی برای دانلود نیست",
    "Delete from release": "حذف از ریلیز",
    "Keep in release": "نگه داشتن در ریلیز",
    "Delete this file from the release?": "این فایل از ریلیز حذف شود؟",
    "Yes, delete from release": "بله، از ریلیز حذف شود",
    "Watched folders": "پوشه‌های نظارت‌شده",
    "Add folder": "افزودن پوشه",
    "Scan again": "اسکن دوباره",
    "Scanning folders...": "در حال اسکن پوشه‌ها...",
    "Watched folders (files saved by other apps)": "پوشه‌های نظارت‌شده (فایل‌های برنامه‌های دیگر)",
    "Add the folders where other download apps save files. Release History and Downloads then show a file that is already on the phone, and warn before it is downloaded again.":
        "پوشه‌هایی را اضافه کن که برنامه‌های دانلود دیگر فایل‌ها را در آن ذخیره می‌کنند. تاریخچه ریلیز و دانلودها فایلی را که از قبل روی گوشی هست نشان می‌دهند و قبل از دانلود دوباره هشدار می‌دهند.",
    "Folders: By source (APK, YouTube...)  (tap to change)": "پوشه‌ها: بر اساس منبع (APK، YouTube...)  (برای تغییر لمس کن)",
    "Folders: By file type (Videos, Audio...)  (tap to change)": "پوشه‌ها: بر اساس نوع فایل (ویدیو، صدا...)  (برای تغییر لمس کن)",
    "Folders: One folder for everything  (tap to change)": "پوشه‌ها: یک پوشه برای همه  (برای تغییر لمس کن)",
    "After a release download: Ask me to delete it from the release": "بعد از دانلود از ریلیز: بپرس از ریلیز هم حذف شود",
    "After a release download: Always delete it from the release": "بعد از دانلود از ریلیز: همیشه از ریلیز هم حذف شود",
    "After a release download: Keep it in the release": "بعد از دانلود از ریلیز: در ریلیز بماند",
})
MORE_PATTERNS.extend([
    (r"(\d+) of (\d+) file\(s\) already on the phone", "{0} از {1} فایل از قبل روی گوشی هست"),
    (r"Skip them, download (\d+) new", "ردشان کن، {0} فایل جدید دانلود شود"),
    (r"Already on the phone: (.+)", "از قبل روی گوشی هست: {0}"),
    (r"Deleting (\d+) from the release\.\.\.", "در حال حذف {0} فایل از ریلیز..."),
    (r"Deleted (\d+) of (\d+) from the release", "{0} از {1} فایل از ریلیز حذف شد"),
    (r"(\d+) file\(s\) you downloaded from the release are on the phone now\.\nDelete them from the release too\?",
     "{0} فایلی که از ریلیز دانلود کردی الان روی گوشی است.\nاز ریلیز هم حذف شوند؟"),
    (r"Files seen in these folders: (\d+)", "فایل‌های دیده‌شده در این پوشه‌ها: {0}"),
])

# --- update 12: browser list - sort, select, clear, refresh
MORE_EXACT.update({
    "Found files": "فایل\u200cهای پیدا\u200cشده",
    "Deselect all": "لغو انتخاب همه",
    "Sort: Newest": "مرتب\u200cسازی: جدیدترین",
    "Sort: Oldest": "مرتب\u200cسازی: قدیمی\u200cترین",
    "Sort: Size": "مرتب\u200cسازی: حجم",
    "Sort: Quality": "مرتب\u200cسازی: کیفیت",
    "Sort: Name": "مرتب\u200cسازی: نام",
    "Sort: Type": "مرتب\u200cسازی: نوع",
    "Scanning the page again...": "در حال اسکن دوباره\u200cی صفحه...",
    "Tap the files you want first": "اول فایل\u200cهای مورد نظر را لمس کن",
})
MORE_PATTERNS.extend([
    (r"Selected: (\d+) of (\d+)  \|  Total (.+)", "انتخاب\u200cشده: {0} از {1}  |  حجم کل {2}"),
])

# --- update 13: browser actions menu, quality groups
MORE_EXACT.update({
    "Actions for selected": "عملیات روی انتخاب‌شده‌ها",
    "What to do with it": "با این فایل چه کنم؟",
    "Download in the app": "دانلود با دانلودر برنامه",
    "Copy direct link": "کپی لینک مستقیم",
    "Copy direct links": "کپی لینک‌های مستقیم",
    "Copy page link": "کپی لینک صفحه",
    "Copy page links": "کپی لینک صفحه‌ها",
    "Upload to GitHub with this link": "آپلود در GitHub با همین لینک",
    "Upload to GitHub with these links": "آپلود در GitHub با همین لینک‌ها",
    "Send to workflows": "ارسال به Workflowها",
    "Share with other apps": "اشتراک‌گذاری با برنامه‌های دیگر",
    "File details": "جزئیات فایل",
    "Back to the list": "بازگشت به فهرست",
    "Back to the actions": "بازگشت به عملیات",
    "Link copied": "لینک کپی شد",
    "Share is not available - copied to the clipboard": "اشتراک‌گذاری در دسترس نیست - در کلیپ‌بورد کپی شد",
    "Video page (via GitHub)": "ویدیوی صفحه (از طریق GitHub)",
    "Not known": "نامشخص",
    "File name": "نام فایل",
    "File type": "نوع فایل",
    "Video quality": "کیفیت ویدیو",
    "File size": "حجم فایل",
    "Codec": "کدک",
    "Page link": "لینک صفحه",
    "Direct link": "لینک مستقیم",
    "Found on page": "پیدا شده در صفحه",
    "Sent with the request": "همراه درخواست ارسال می‌شود",
})
MORE_PATTERNS.extend([
    (r"(\d+) qualities  \|  (.+)", "{0} کیفیت  |  {1}"),
    (r"(\d+) qualities", "{0} کیفیت"),
    (r"(\d+) links copied", "{0} لینک کپی شد"),
    (r"Selected: (\d+) of (\d+)", "انتخاب\u200cشده: {0} از {1}"),
])

# --- update 14: browser file types (Browser settings, type filter, caught downloads)
MORE_EXACT.update({
    "Browser settings": "تنظیمات مرورگر",
    "File types the browser looks for. Turn a type off to hide it from the results.":
        "نوع فایل‌هایی که مرورگر دنبالشان می‌گردد. با خاموش‌کردن هر نوع، از نتایج پنهان می‌شود.",
    "Custom extensions": "پسوندهای سفارشی",
    "Extension, e.g. torrent": "پسوند، مثلاً torrent",
    "Add": "افزودن",
    "No custom extensions yet.": "هنوز پسوند سفارشی‌ای نیست.",
    "Not a valid extension (letters and digits only, up to 8)": "پسوند معتبر نیست (فقط حرف و عدد انگلیسی، حداکثر ۸ کاراکتر)",
    "This type is already built in": "این نوع از قبل در برنامه هست",
    "Already in the list": "از قبل در فهرست هست",
    "A type you turn on is looked for when you go back (the page loads again). These choices stay after the app is closed.":
        "نوعی که روشن کنی بعد از بازگشت جستجو می‌شود (صفحه دوباره بارگذاری می‌شود). این انتخاب‌ها بعد از بستن برنامه هم می‌مانند.",
    "No files found yet. Play a video or open a file link on the page, then tap the badge again.":
        "هنوز فایلی پیدا نشده. ویدیو را پخش کن یا روی لینک فایل بزن، بعد دوباره روی نشان بزن.",
    "Type: All": "نوع: همه",
})
_BROWSER_CATS = {"Videos": "ویدیوها", "Audio": "صدا", "Archives": "فایل‌های فشرده", "APK files": "فایل‌های APK",
                 "Packages": "بسته‌ها", "Documents": "اسناد", "Custom": "سفارشی", "Other": "سایر"}
for _en, _fa in _BROWSER_CATS.items():
    MORE_EXACT[f"{_en}: ON"] = f"{_fa}: روشن"
    MORE_EXACT[f"{_en}: OFF"] = f"{_fa}: خاموش"
    MORE_EXACT[f"Type: {_en}"] = f"نوع: {_fa}"
MORE_PATTERNS.extend([
    (r"Added: (.+)", "اضافه شد: {0}"),
    (r"Removed: (.+)", "حذف شد: {0}"),
    (r"Remove: (.+)", "حذف: {0}"),
    (r"(\d+) download\(s\) caught from the page - find them below", "{0} دانلود از صفحه گرفته شد - پایین فهرست را ببین"),
])
PHRASES.extend([
    ("Video file", "فایل ویدیو"), ("Audio file", "فایل صدا"), ("HLS stream", "استریم HLS"),
    ("DASH stream", "استریم DASH"), ("Archive file", "فایل فشرده"), ("APK file", "فایل APK"),
    ("Package file", "فایل بسته"), ("Document", "سند"), ("Custom file", "فایل سفارشی"),
    ("Unknown file", "فایل ناشناخته"), ("via GitHub", "از طریق GitHub"),
])


# --- update 15: browser tabs, history and bookmarks (screens/browser_pages.py)
_TABS_FA = {
    "Menu": "منو", "Browser menu": "منوی مرورگر", "Tabs": "تب‌ها", "New tab": "تب جدید",
    "Close all": "بستن همه", "Tap again to close all": "برای بستن همه دوباره بزن",
    "Add bookmark": "افزودن نشانک", "Remove bookmark": "حذف نشانک", "Bookmark added": "نشانک اضافه شد",
    "Bookmark removed": "نشانک حذف شد", "Open a page first": "اول یک صفحه باز کن", "Bookmarks": "نشانک‌ها",
    "Bookmark": "نشانک", "History": "تاریخچه", "Search history": "جست‌وجو در تاریخچه",
    "Search bookmarks": "جست‌وجو در نشانک‌ها", "Clear all": "پاک کردن همه",
    "Tap again to clear all": "برای پاک‌کردن همه دوباره بزن", "No history yet.": "هنوز تاریخچه‌ای نیست.",
    "No bookmarks yet.": "هنوز نشانکی نیست.", "Nothing matches your search.": "چیزی پیدا نشد.",
    "Edit": "ویرایش", "Open in new tab": "باز کردن در تب جدید", "Title": "عنوان",
    "Title can't be empty": "عنوان نمی‌تواند خالی باشد", "Renamed": "نام تغییر کرد",
    "Back to the menu": "بازگشت به منو", "Back to bookmarks": "بازگشت به نشانک‌ها",
}
for _en, _fa in _TABS_FA.items():
    MORE_EXACT.setdefault(_en, _fa)
MORE_PATTERNS.extend([
    (r"Tabs \((\d+)\)", "تب‌ها ({0})"),
    (r"Open tabs: (\d+) of (\d+)", "تب‌های باز: {0} از {1}"),
    (r"Tab limit reached \((\d+)\)", "به حداکثر تعداد تب رسیدی ({0})"),
    (r"(\d+) pages?", "{0} صفحه"),
    (r"(\d+) bookmarks?", "{0} نشانک"),
    (r"(\d+) of (\d+) pages?", "{0} از {1} صفحه"),
    (r"(\d+) of (\d+) bookmarks?", "{0} از {1} نشانک"),
])


# --- update 16: browser page tools (screens/browser_tools.py)
_TOOLS_FA = {
    "Page tools": "ابزارهای صفحه", "Data saving": "صرفه\u200cجویی در اینترنت", "Clean up": "پاک\u200cسازی",
    "Some page tools need the latest app update (a new build).":
        "بعضی ابزارها به آخرین نسخه\u200cی برنامه (بیلد جدید) نیاز دارند.",
    "Needs the latest app update": "به آخرین نسخه\u200cی برنامه (بیلد جدید) نیاز دارد",
    "Translate page (Persian)": "ترجمه\u200cی صفحه (فارسی)", "Show original page": "نمایش صفحه\u200cی اصلی",
    "Translate opens the page through Google Translate: it needs Google to be reachable, and pages that need a sign-in may not work.":
        "ترجمه، صفحه را از طریق Google Translate باز می\u200cکند: به در دسترس بودن گوگل نیاز دارد و صفحه\u200cهایی که ورود لازم دارند ممکن است کار نکنند.",
    "This page cannot be translated": "این صفحه قابل ترجمه نیست",
    "Find in page": "جست\u200cوجو در صفحه", "Done": "تمام",
    "Desktop view on for this tab": "نمای دسکتاپ برای این تب روشن شد",
    "Desktop view off for this tab": "نمای دسکتاپ برای این تب خاموش شد",
    "Dark mode on": "حالت تاریک روشن شد", "Dark mode off": "حالت تاریک خاموش شد",
    "Images are blocked now; the page reloads": "تصاویر مسدود شد؛ صفحه دوباره بارگذاری می\u200cشود",
    "Images are loaded again; the page reloads": "تصاویر دوباره بارگذاری می\u200cشوند؛ صفحه دوباره بارگذاری می\u200cشود",
    "Videos are blocked now; the page reloads": "ویدیوها مسدود شد؛ صفحه دوباره بارگذاری می\u200cشود",
    "Videos are loaded again; the page reloads": "ویدیوها دوباره بارگذاری می\u200cشوند؛ صفحه دوباره بارگذاری می\u200cشود",
    "Clear cache": "پاک\u200cکردن کش", "Cache cleared": "کش پاک شد",
    "Clear this site's data": "پاک\u200cکردن اطلاعات این سایت",
    "Clear data of all sites": "پاک\u200cکردن اطلاعات همه\u200cی سایت\u200cها",
    "Cookies and saved data (sign-in, preferences) of this site are deleted. You will be signed out of it.":
        "کوکی\u200cها و داده\u200cهای ذخیره\u200cشده (ورود، تنظیمات) این سایت پاک می\u200cشود. از این سایت خارج می\u200cشوی.",
    "Cookies and saved data of ALL sites are deleted. You will be signed out of every site.":
        "کوکی\u200cها و داده\u200cهای ذخیره\u200cشده\u200cی همه\u200cی سایت\u200cها پاک می\u200cشود. از همه\u200cی سایت\u200cها خارج می\u200cشوی.",
    "Yes, clear": "بله، پاک شود", "Cancel": "انصراف",
    "Done. The page reloads.": "انجام شد. صفحه دوباره بارگذاری می\u200cشود.",
}
for _en, _fa in _TOOLS_FA.items():
    MORE_EXACT.setdefault(_en, _fa)
for _en, _fa in {"Desktop view": "نمای دسکتاپ", "Dark mode": "حالت تاریک", "Images disabled": "تصاویر غیرفعال",
                 "Videos disabled": "ویدیوها غیرفعال"}.items():
    MORE_EXACT[f"{_en}: ON"] = f"{_fa}: روشن"
    MORE_EXACT[f"{_en}: OFF"] = f"{_fa}: خاموش"
MORE_PATTERNS.extend([
    (r"Site: (.+)", "سایت: {0}"),
])


# --- update 17: export cookies (screens/browser_cookies.py)
_COOKIES_FA = {
    "Cookies and headers": "کوکی\u200cها و هدرها", "Export cookies": "خروجی کوکی\u200cها",
    "Cookies sign in as you: anyone who gets them can use your accounts. Choose only the domains you need. Nothing is sent anywhere without your confirmation.":
        "کوکی\u200cها به\u200cجای تو وارد حساب می\u200cشوند: هر کسی که آن\u200cها را بگیرد می\u200cتواند از حساب\u200cهایت استفاده کند. فقط دامنه\u200cهایی را انتخاب کن که لازم داری. بدون تأیید تو چیزی به جایی فرستاده نمی\u200cشود.",
    "Open a page first": "اول یک صفحه باز کن",
    "Only the cookies sent with the files found on this page are available. All the cookies of the site need the latest app update (a new build).":
        "فقط کوکی\u200cهایی در دسترس است که همراه فایل\u200cهای پیداشده\u200cی این صفحه فرستاده شده\u200cاند. برای همه\u200cی کوکی\u200cهای سایت به آخرین نسخه\u200cی برنامه (بیلد جدید) نیاز است.",
    "No cookies were found for this site. Sign in on the page first, then try again.":
        "برای این سایت کوکی\u200cای پیدا نشد. اول در صفحه وارد حساب شو، بعد دوباره امتحان کن.",
    "Add another domain (for example google.com)": "افزودن دامنه\u200cی دیگر (مثلاً google.com)",
    "Add domain": "افزودن دامنه", "Type a domain like google.com": "یک دامنه مثل google.com بنویس",
    "Domain added": "دامنه اضافه شد", "No cookies were found for this domain": "برای این دامنه کوکی\u200cای پیدا نشد",
    "Choose at least one domain": "حداقل یک دامنه را انتخاب کن", "Continue": "ادامه",
    "Android WebView limits: HttpOnly cookies are included, but the expiry, path and Secure / HttpOnly flags of a cookie cannot be read, so cookies.txt keeps every cookie as a session cookie for the whole site (path /). Cookies set only for another path, or for a domain that is not listed here, are not available: use Add domain for sign-in domains (for example google.com).":
        "محدودیت\u200cهای WebView اندروید: کوکی\u200cهای HttpOnly هم گرفته می\u200cشوند، اما تاریخ انقضا، مسیر و پرچم\u200cهای Secure و HttpOnly هر کوکی خوانده نمی\u200cشود؛ برای همین cookies.txt همه\u200cی کوکی\u200cها را به\u200cصورت کوکی نشست برای کل سایت (مسیر /) نگه می\u200cدارد. کوکی\u200cهایی که فقط برای مسیر دیگری یا برای دامنه\u200cای خارج از این فهرست ساخته شده\u200cاند در دسترس نیستند: برای دامنه\u200cهای ورود (مثلاً google.com) از «افزودن دامنه» استفاده کن.",
    "Back to domains": "بازگشت به دامنه\u200cها", "Back to the cookies": "بازگشت به کوکی\u200cها",
    "Cookies": "کوکی\u200cها", "Headers for yt-dlp and curl": "هدرها برای yt-dlp و curl",
    "Copy cookies (Netscape format)": "کپی کوکی\u200cها (فرمت Netscape)", "Cookies copied": "کوکی\u200cها کپی شد",
    "Save cookies.txt on the phone": "ذخیره\u200cی cookies.txt در گوشی", "Saving...": "در حال ذخیره...",
    "Could not save the file": "ذخیره\u200cی فایل انجام نشد",
    "This file signs in as you: delete it when you are done.": "این فایل به\u200cجای تو وارد حساب می\u200cشود: بعد از کارت پاکش کن.",
    "Send to a GitHub secret": "ارسال به GitHub Secret",
    "Copy yt-dlp options": "کپی گزینه\u200cهای yt-dlp", "Copy curl command (cookies.txt)": "کپی دستور curl (با cookies.txt)",
    "Copy curl command (Cookie header)": "کپی دستور curl (با هدر Cookie)", "Copy Cookie header": "کپی هدر Cookie",
    "Copy User-Agent": "کپی User-Agent", "Copy Referer": "کپی Referer", "Copied": "کپی شد",
    "Nothing to copy": "چیزی برای کپی نیست",
    "The Cookie header and the curl command with it hold the cookie values: share them with care.":
        "هدر Cookie و دستور curl همراه آن مقدار کوکی\u200cها را دارند: با احتیاط به اشتراک بگذار.",
    "The workflows read cookies from a GitHub secret of your repository. The secret is replaced by these cookies; what is saved now cannot be read back. Choose where they go:":
        "workflowها کوکی را از یک Secret گیت\u200cهاب مخزن تو می\u200cخوانند. Secret با این کوکی\u200cها جایگزین می\u200cشود؛ آنچه الان ذخیره است قابل خواندن نیست. انتخاب کن کجا بروند:",
    "Checking what is saved...": "در حال بررسی آنچه ذخیره شده...", "Saved now: none": "الان چیزی ذخیره نیست",
    "Could not read what is saved.": "خواندن آنچه ذخیره شده انجام نشد.",
    "Send cookies to GitHub?": "کوکی\u200cها به GitHub ارسال شود؟",
    "Sent to GitHub encrypted; only your workflows can read them. This replaces the cookies saved in this secret now, and they cannot be read back.":
        "رمزشده به GitHub فرستاده می\u200cشود؛ فقط workflowهای تو می\u200cتوانند آن را بخوانند. این کار کوکی\u200cهای فعلیِ این Secret را جایگزین می\u200cکند و قابل بازگرداندن نیست.",
    "Yes, send to GitHub": "بله، به GitHub ارسال شود", "Cancel": "انصراف",
    "Sending...": "در حال ارسال...", "Sent. The workflows will use these cookies.": "ارسال شد. workflowها از این کوکی\u200cها استفاده می\u200cکنند.",
    "Could not send": "ارسال انجام نشد", "There are no cookies to save.": "کوکی\u200cای برای ذخیره نیست.",
    "These cookies are too long for a GitHub secret. Choose fewer domains.": "این کوکی\u200cها برای یک GitHub Secret زیادی طولانی است. دامنه\u200cهای کمتری انتخاب کن.",
    "Back to the menu": "بازگشت به منو", "Back to browser": "بازگشت به مرورگر",
}
for _en, _fa in _COOKIES_FA.items():
    MORE_EXACT.setdefault(_en, _fa)
MORE_PATTERNS.extend([
    (r"(.+) \((\d+)\): ON", "{0} ({1}): روشن"),
    (r"(.+) \((\d+)\): OFF", "{0} ({1}): خاموش"),
    (r"Cookies: (\d+)", "کوکی\u200cها: {0}"),
    (r"Domains: (.+)", "دامنه\u200cها: {0}"),
    (r"Secret: (.+)", "Secret: {0}"),
    (r"Saved now: (.+)", "الان ذخیره است: {0}"),
    (r"Saved: (.+)", "ذخیره شد: {0}"),
])

# --- update: browser start mode (background queue or now)
_RUNMODE_FA = {
    "Run it in the background or now?": "در پس\u200cزمینه انجام شود یا همین الان؟",
    "Background: the files join the queue and you stay here. Now: the Downloads page opens and you watch the progress.":
        "پس\u200cزمینه: فایل\u200cها به صف می\u200cروند و تو همین\u200cجا می\u200cمانی. همین الان: صفحه\u200cی دانلودها باز می\u200cشود و پیشرفت را می\u200cبینی.",
    "Add to the queue (background)": "افزودن به صف (پس\u200cزمینه)",
    "Now (watch it)": "همین الان (نمایش پیشرفت)",
    "Don't ask again: OFF": "دیگر نپرس: خاموش",
    "Don't ask again: ON": "دیگر نپرس: روشن",
    "You can change this later in Browser settings.": "بعداً از تنظیمات مرورگر می\u200cتوانی این را عوض کنی.",
    "Added to the queue - it runs in the background": "به صف اضافه شد - در پس\u200cزمینه انجام می\u200cشود",
    "Add to the queue (download in background)": "افزودن به صف (دانلود در پس\u200cزمینه)",
    "Start mode (download / upload)": "حالت شروع (دانلود / آپلود)",
    "Run mode: Ask every time": "حالت اجرا: هر بار بپرس",
    "Run mode: Always in the background": "حالت اجرا: همیشه در پس\u200cزمینه",
    "Run mode: Always now": "حالت اجرا: همیشه همین الان",
    "Ask every time shows the choice each time. The other two start at once without asking - this setting wins.":
        "«هر بار بپرس» هر دفعه انتخاب را نشان می\u200cدهد. دو حالت دیگر بدون پرسیدن فوراً شروع می\u200cکنند - این تنظیم اولویت دارد.",
}
for _en, _fa in _RUNMODE_FA.items():
    MORE_EXACT.setdefault(_en, _fa)


# --- update: Downloads tabs (Adding / Error / Scheduler), add-to-list and the download scheduler
_SCHED_FA = {
    "Adding": "افزوده\u200cشده",
    "Error": "خطا",
    "Scheduler": "زمان\u200cبندی",
    "Added - waiting for you to start it": "اضافه شد - منتظر شروع تو است",
    "Paused until the next start time": "متوقف تا ساعت شروع بعدی",
    "Scheduled - the scheduler is OFF": "زمان\u200cبندی\u200cشده - زمان\u200cبند خاموش است",
    "Start now": "شروع همین الان",
    "Stop now": "توقف همین الان",
    "Add to scheduler": "افزودن به زمان\u200cبندی",
    "Back to Adding": "بازگشت به افزوده\u200cشده\u200cها",
    "Scheduler: ON": "زمان\u200cبند: روشن",
    "Scheduler: OFF": "زمان\u200cبند: خاموش",
    "Stop time: not set": "ساعت پایان: تعیین نشده",
    "Scheduler is off": "زمان\u200cبند خاموش است",
    "Inside the time window - scheduled files run": "داخل بازه\u200cی زمانی - فایل\u200cهای زمان\u200cبندی\u200cشده اجرا می\u200cشوند",
    "Outside the time window - waiting for the start time": "خارج از بازه\u200cی زمانی - منتظر ساعت شروع",
    "The time is the phone's clock. Scheduled files run between the start and stop time every day, while the app is open.":
        "ساعت، ساعت گوشی است. فایل\u200cهای زمان\u200cبندی\u200cشده هر روز بین ساعت شروع و پایان اجرا می\u200cشوند، تا وقتی برنامه باز است.",
    "Start time": "ساعت شروع",
    "Stop time": "ساعت پایان",
    "No stop time": "بدون ساعت پایان",
    "Save": "ذخیره",
    "Cancel": "انصراف",
    "Type the hour and the minutes": "ساعت و دقیقه را بنویس",
    "Hour 0-23, minutes 0-59": "ساعت ۰ تا ۲۳، دقیقه ۰ تا ۵۹",
    "Scheduled files started": "فایل\u200cهای زمان\u200cبندی\u200cشده شروع شدند",
    "Scheduled downloads paused": "دانلودهای زمان\u200cبندی\u200cشده متوقف شدند",
    "Add to the list (don't start)": "افزودن به فهرست (شروع نشود)",
    "Add to the scheduler": "افزودن به زمان\u200cبندی",
    "These files need GitHub - use Download in the app": "این فایل\u200cها باید از GitHub بروند - «دانلود در برنامه» را بزن",
    "Update the app to use this": "برای استفاده از این، برنامه را به\u200cروز کن",
}
for _en, _fa in _SCHED_FA.items():
    MORE_EXACT.setdefault(_en, _fa)
    MORE_EXACT.setdefault("\u25cf " + _en, "\u25cf " + _fa)
_TAB_FA = {"All": "همه", "Downloading": "در حال دانلود", "Adding": "افزوده\u200cشده", "Finished": "تمام\u200cشده",
           "Error": "خطا", "Scheduler": "زمان\u200cبندی"}
for _en, _fa in _TAB_FA.items():
    MORE_PATTERNS.append((_en + r" \((\d+)\)", _fa + " ({0})"))
    MORE_PATTERNS.append(("\u25cf " + _en + r" \((\d+)\)", "\u25cf " + _fa + " ({0})"))
MORE_PATTERNS.extend([
    (r"Scheduled - starts at (.+)", "زمان\u200cبندی\u200cشده - شروع در ساعت {0}"),
    (r"Start time: (.+)", "ساعت شروع: {0}"),
    (r"Stop time: (.+)", "ساعت پایان: {0}"),
    (r"Phone time: (.+)", "ساعت گوشی: {0}"),
    (r"Started (\d+) file\(s\)", "{0} فایل شروع شد"),
    (r"Added (\d+) file\(s\) to the scheduler", "{0} فایل به زمان\u200cبندی اضافه شد"),
    (r"Moved (\d+) file\(s\) back to Adding", "{0} فایل به افزوده\u200cشده\u200cها برگشت"),
    (r"Removed (\d+) waiting file\(s\)", "{0} فایل منتظر حذف شد"),
    (r"(\d+) file\(s\) added to the scheduler", "{0} فایل به زمان\u200cبندی اضافه شد"),
    (r"(\d+) file\(s\) added to the list", "{0} فایل به فهرست اضافه شد"),
])
