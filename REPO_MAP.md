# REPO_MAP (نقشه کوتاه ریپو)

هدف: Claude اول این فایل را بخواند، نه کل درخت ریپو را. هر وقت فایل/پوشه‌ی مهمی اضافه، حذف یا جابجا شد، همین فایل را به‌روز کن.
جزئیات بیشتر: ARCHITECTURE.md (لایه‌بندی و جریان اجرا؛ به‌روز؛ فقط برای کار معماری) و PROJECT_NOTES.md (رفتار قابلیت‌ها، ~۱۴KB، خلاصه‌شده ۱۴۰۵/۰۸؛ قابلیت‌های جدیدتر در آن نیست؛ فقط وقتی صریحاً لازم شد).

## شاخه‌ها
- main: کد اپ (Kivy/Android) + همه workflowهای GitHub Actions + version.txt
- config: داده و تنظیم، بدون کد اپ: config.json، follows.json، follow-state.json، ntfy.json، promotions.json، site-log.jsonl، working_proxies.txt، plugins/، lab/ (کپی‌های کاری)، logs/
- lab: محیط آزمایشی Lab: workflowهای lab-*، lab/lib/*، lab_scripts/*، راهنماها (LAB.md, WORKFLOW_GUIDE.md, LINKLAB_SITE_GUIDE.md)
- بکاپ: شاخه‌ی backup و پوشه‌ی config/backups/ حذف شده‌اند (۱۴۰۵/۰۸). بکاپ پروژه فقط با backup-project.yml ساخته می‌شود و zip آن در Release آپلود می‌شود (نه در هیچ شاخه‌ای).

## main: کد اپ
- main.py: ورودی اپ
- screens/: صفحه‌ها (UI)
  - navigator.py (خیلی بزرگ، ~119KB: مسیریابی و منوها؛ فقط بخش لازم را بخوان)
  - history.py (Release History)، downloads.py (Downloads)، youtube_download.py، playlist.py
  - settings.py، appearance.py، app_update.py، follow.py، health.py، lab.py، plugin_host.py، arvan.py، storage.py، browser.py
  - actions_dynamic.py / actions_status.py (دکمه‌های Download Anything و وضعیت اجرا)
- services/: منطق و ارتباط با GitHub (download_service، history_service، runs_service، playlist_service، follow_service، file_download_service، repo_update_service، health_service، arvan_service، cookie_secret_service، ...)
- api/: GitHub API و تنظیمات ذخیره‌شده
  - api/github/: client، releases (بزرگ)، workflows، logs، remote_config، repo_files، auth
  - *_prefs.py: تنظیمات کاربر (appearance، download_folder، storage، watched_folders، ntfy، ...)
  - mornye.py (بزرگ)، filimo.py
- core/: ابزار مشترک
  - fa_strings.py / fa_strings_more.py / fa_strings_msgs.py: متن‌های فارسی UI
  - error_help.py (راهنمای خطا)، download_manager.py، hls_download.py (دانلود m3u8 روی گوشی و ساخت یک فایل ویدیویی)، android_*.py (دانلود/فایل/نصب/اشتراک)، plugin_loader.py، follow.py، rerun.py، retention.py، release_links.py، timeutil.py، appearance.py
- scripts/: اسکریپت‌هایی که داخل workflowها اجرا می‌شوند (aparat_*، auto_follow، batch_download، cleanup_releases، storage_*، finglish_name، mornye_fetch، xh_*، xray_setup، ...)
- java/org/redi2213/ytbridge/BrowserHelper.java، intent_filters.xml، buildozer.spec، version.txt، tests/

## main: workflowها (.github/workflows/)
- دانلود: download.yml، download-batch.yml، list-formats.yml، list-playlist.yml، aparat-download.yml، telegram-download.yml، instagram-downloader.yml، filimo-direct-link.yml، google-play-download.yml، Series-Links.yml، mornye-from-links.yml
- آپلود/ذخیره: Any-Site-Upload.yml، upload-file.yml، drive-to-release.yml، arvan-from-link.yml، arvan-manage.yml، arvan-upload.yml، zip-release.yml
- خودکار: Auto-Follow.yml، backup-project.yml (zip از main + config در Release)، build-apk.yml
- پاک‌سازی: cleanup-artifacts.yml، cleanup-releases.yml، standalone-cleanup-all-artifacts.yml
- پروکسی: find-proxies.yml
- Lab: lab-*.yml (download، find-proxies، free-iran-proxy-list، links، pornhub-search-scraper، refresh-configs، run، schedule، site-suj-mobi، workflow)

## کجا دنبال چه چیزی بگردیم
- متن/برچسب فارسی: core/fa_strings*.py
- منوی Download Anything/دکمه‌ها: config.json (شاخه config) + screens/actions_dynamic.py
- Release History / حذف / انتخاب: screens/history.py + api/github/releases.py
- Downloads (مدیر دانلود): screens/downloads.py + core/download_manager.py + services/file_download_service.py
- مرورگر داخلی: screens/browser.py (UI، تنظیمات، فیلتر) + core/browser_media.py (قوانین نوع فایل و Session؛ بدون Build) + services/browser_service.py (probe هدرها) + screens/browser_pages.py (منو، تب‌ها، History، Bookmark) + core/browser_tabs.py (داده‌ی تب‌ها/History/Bookmark؛ بدون Build) + api/browser_prefs.py + core/android_browser.py + java/.../BrowserHelper.java (تغییر جاوا = Build؛ switchTab/forgetTab برای حفظ وضعیت صفحه‌ی تب‌ها) + tests/browser_tabs_test.py + core/browser_tools.py (ترجمه‌ی لینک با translate.goog؛ بدون Build) + screens/browser_tools.py (بخش Page tools منو، نوار Find، تأیید پاک‌سازی) + tests/browser_tools_test.py + screens/browser_cookies.py (Export cookies: انتخاب دامنه، cookies.txt، هدرهای yt-dlp/curl، ارسال به Secret؛ بدون Build) + core/browser_cookies.py (منطق خالص کوکی/هدر) + services/cookie_secret_service.py (Secretهای YTDLP_COOKIES و COOKIES_TXT) + tests/browser_cookies_test.py؛ BrowserHelper.exportCookies (Build: خواندن کوکی از CookieManager)؛ BrowserHelper.java حالا Desktop view/Dark/Find/Block images-videos/Clear cache-data هم دارد (Build)
- Browser pack (به‌روزرسانی آنلاین مرورگر بدون Build): core/browser_pack.py (لودر: دانلود از config/plugins/browser، بررسی sha256/سینتکس/قرارداد، فعال‌سازی، rollback خودکار، PACK_FILES = فایل‌های قابل آنلاین‌شدن، NATIVE_API) + screens/browser_pack_screen.py (Settings > App tools > Browser online update؛ عمداً خارج از pack) + scripts/publish_browser_pack.py + .github/workflows/publish-browser-pack.yml (با هر push روی main که فایل‌های مرورگر را عوض کند، pack را به config منتشر می‌کند) + tests/browser_pack_test.py + core/fa_strings_browser_pack.py. تغییر فایل‌های PACK_FILES روی main = به‌روزرسانی بدون Build؛ تغییر Java/android_browser.py/browser_pack.py/browser_prefs.py = Build (و اگر کد جدید pack به Java جدید نیاز دارد NATIVE_API را بالا ببر)
- خطای workflow: .github/workflows/<n>.yml + scripts/<n>.py + core/error_help.py
- Lab و Promote: شاخه lab → lab/promote.py، lab/lib/promote_*.py، lab/wf_import.py
- نسخه/ساخت APK: version.txt، build-apk.yml، buildozer.spec
- بکاپ پروژه: .github/workflows/backup-project.yml (خروجی: zip در Release)

## قوانین کار
- تغییر ظاهری/متنی → معمولاً فقط main. افزودن منبع دانلود → معمولاً config.json در شاخه config.
- workflowهای lab-* در هر دو شاخه main و lab هستند (نسخه‌ها متفاوت‌اند)؛ قبل از تغییر، شاخه‌ی درست را مشخص کن.
- فایل بزرگ (navigator.py، fa_strings_more.py، releases.py، history.py) را کامل بازنویسی نکن؛ فقط بخش لازم.
