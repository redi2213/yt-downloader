# REPO_MAP (نقشه کوتاه ریپو)

هدف: Claude اول این فایل را بخواند، نه کل درخت ریپو را. هر وقت فایل/پوشه‌ی مهمی اضافه، حذف یا جابجا شد، همین فایل را به‌روز کن.
جزئیات بیشتر: ARCHITECTURE.md (لایه‌بندی و جریان اجرا؛ به‌روز؛ فقط برای کار معماری) و PROJECT_NOTES.md (رفتار قابلیت‌ها، ~۱۴KB، خلاصه‌شده ۱۴۰۵/۰۸؛ قابلیت‌های جدیدتر در آن نیست؛ فقط وقتی صریحاً لازم شد).

## شاخه‌ها
- main: کد اپ (Kivy/Android) + همه workflowهای GitHub Actions + version.txt
- config: داده و تنظیم، بدون کد اپ: config.json، follows.json، follow-state.json، ntfy.json، promotions.json، site-log.jsonl، working_proxies.txt، plugins/، lab/ (کپی‌های کاری)، logs/، lab-logs/ (لاگ خطای Lab: یک فایل برای هر لینک ناموفق)
- lab: محیط آزمایشی Lab: workflowهای lab-*، lab/lib/*، lab_scripts/*، راهنماها (LAB.md, WORKFLOW_GUIDE.md, LINKLAB_SITE_GUIDE.md)
- بکاپ: شاخه‌ی backup و پوشه‌ی config/backups/ حذف شده‌اند (۱۴۰۵/۰۸). بکاپ پروژه فقط با backup-project.yml ساخته می‌شود و zip آن در Release آپلود می‌شود (نه در هیچ شاخه‌ای).

## main: کد اپ
- main.py: ورودی اپ
- screens/: صفحه‌ها (UI)
  - navigator.py (خیلی بزرگ، ~119KB: مسیریابی و منوها؛ فقط بخش لازم را بخوان)
  - history.py (Release History)، downloads.py (Downloads)، youtube_download.py، playlist.py
  - settings.py، appearance.py، app_update.py، follow.py، health.py، lab.py، plugin_host.py، arvan.py، storage.py، browser.py
  - home_menu.py (منوی آبشاری Home: دکمه‌ی «Home» در نوار بالای همه‌ی صفحه‌ها (main.py: topbar/show_topbar؛ در Home و صفحه‌ی مرورگر پنهان است) و در Menu مرورگر؛ لیست دکمه‌های اصلی داخل خود فایل)
  - actions_dynamic.py / actions_status.py (دکمه‌های Download Anything و وضعیت اجرا)
- services/: منطق و ارتباط با GitHub (download_service، history_service، runs_service، playlist_service، follow_service، file_download_service، repo_update_service، health_service، arvan_service، cookie_secret_service، visibility_service (دکمه‌ی Settings > App tools > Repository visibility)، ...)
- api/: GitHub API و تنظیمات ذخیره‌شده
  - api/github/: client، releases (بزرگ)، workflows، logs، remote_config، repo_files، auth، visibility (عمومی/خصوصی کردن ریپو)
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
- خودکار: graph-report.yml (روزانه؛ اگر چیزی بیرون docs/ عوض نشده باشد اجرا نمی‌شود؛ docs/GRAPH_REPORT.md و docs/GRAPH_SOURCE_SHA.txt را به‌روز می‌کند؛ دستی هم قابل اجراست)، Auto-Follow.yml، backup-project.yml (zip از main + config در Release)، build-apk.yml
- پاک‌سازی: cleanup-artifacts.yml، cleanup-releases.yml، standalone-cleanup-all-artifacts.yml
- پروکسی: find-proxies.yml
- Lab: lab-*.yml (download، find-proxies، free-iran-proxy-list، links، pornhub-search-scraper، refresh-configs، run، schedule، site-suj-mobi، workflow)

## کجا دنبال چه چیزی بگردیم
- متن/برچسب فارسی: core/fa_strings*.py
- منوی Download Anything/دکمه‌ها: config.json (شاخه config) + screens/actions_dynamic.py
- Release History / حذف / انتخاب: screens/history.py + api/github/releases.py
- Downloads (مدیر دانلود): screens/downloads.py + core/download_manager.py + services/file_download_service.py + core/download_schedule.py (ساعت‌های زمان‌بند؛ بدون Kivy) + api/download_queue_prefs.py (تنظیم زمان‌بند و ذخیره‌ی فایل‌های Adding/Scheduler) + tests/download_schedule_test.py؛ تب‌ها: All / Downloading / Adding / Finished / Error / Scheduler؛ در مرورگر: «Add to the list» و «Add to the scheduler» در screens/browser.py
- باز کردن لینک GitHub (دکمه‌های «Open on GitHub»: انتخاب GitHub app / Chrome / مرورگر داخلی + «Remember my choice»): screens/navigator.py (open_run_on_github، _open_github_url) + screens/dialogs.py (choose_open) + api/open_link_prefs.py (ذخیره‌ی انتخاب؛ تغییرش: Settings > App tools > «Open GitHub links with») + core/android_actions.py (open_in_github_app، open_in_browser)
- مرورگر داخلی: screens/browser.py (UI، تنظیمات، فیلتر) + core/browser_media.py (قوانین نوع فایل و Session؛ بدون Build) + services/browser_service.py (probe هدرها) + screens/browser_pages.py (منو، تب‌ها، History، Bookmark) + core/browser_tabs.py (داده‌ی تب‌ها/History/Bookmark؛ بدون Build) + api/browser_prefs.py + core/android_browser.py + java/.../BrowserHelper.java (تغییر جاوا = Build؛ switchTab/forgetTab برای حفظ وضعیت صفحه‌ی تب‌ها) + tests/browser_tabs_test.py + core/browser_tools.py (ترجمه‌ی لینک با translate.goog؛ بدون Build) + screens/browser_tools.py (بخش Page tools منو، نوار Find، تأیید پاک‌سازی) + tests/browser_tools_test.py + screens/browser_cookies.py (Export cookies: انتخاب دامنه، cookies.txt، هدرهای yt-dlp/curl، ارسال به Secret؛ بدون Build) + core/browser_cookies.py (منطق خالص کوکی/هدر) + services/cookie_secret_service.py (Secretهای YTDLP_COOKIES و COOKIES_TXT) + tests/browser_cookies_test.py؛ BrowserHelper.exportCookies (Build: خواندن کوکی از CookieManager) + BrowserHelper.netLog (Build: لاگ درخواست‌های Fetch/XHR با هدر، بدنه و بدنه‌ی پاسخ؛ صفحه‌ی Network requests (فیلتر دامنه، Copy as cURL، Copy response body) زیر Export cookies در screens/browser_cookies.py (open_netlog) و core/browser_cookies.py: net_curl)؛ BrowserHelper.java حالا Desktop view/Dark/Find/Block images-videos/Clear cache-data هم دارد (Build)؛ مسدودسازی تبلیغ و پاپ‌آپ (Build): setAdBlock + AD_HOSTS + AD_JS + PopupGuard (onCreateWindow) + SHORT_HOSTS/unwrapAll (رد کردن لینک‌کوتاه‌کننده‌ها مثل shrinkearn با خواندن url=) در BrowserHelper.java، set_adblock در core/android_browser.py، فلگ ads_off (پیش‌فرض روشن) در services/browser_service.py، دکمه‌ی «Block ads and pop-ups» در screens/browser_tools.py؛ بازرس صفحه برای فرستادن به Claude (Build): منوی Browser > «Inspect page (to share)» = Copy page HTML / links / navigation log (BrowserHelper.inspect، inspectResult، navLogText؛ android_browser.inspect/nav_log؛ UI در screens/browser_tools.py)
- Browser pack (به‌روزرسانی آنلاین مرورگر بدون Build): core/browser_pack.py (لودر: دانلود از config/plugins/browser، بررسی sha256/سینتکس/قرارداد، فعال‌سازی، rollback خودکار، PACK_FILES = فایل‌های قابل آنلاین‌شدن، NATIVE_API) + screens/browser_pack_screen.py (Settings > App tools > Browser online update؛ عمداً خارج از pack) + scripts/publish_browser_pack.py + .github/workflows/publish-browser-pack.yml (با هر push روی main که فایل‌های مرورگر را عوض کند، pack را به config منتشر می‌کند) + tests/browser_pack_test.py + core/fa_strings_browser_pack.py. تغییر فایل‌های PACK_FILES روی main = به‌روزرسانی بدون Build؛ تغییر Java/android_browser.py/browser_pack.py/browser_prefs.py = Build (و اگر کد جدید pack به Java جدید نیاز دارد NATIVE_API را بالا ببر)
- خطای workflow: .github/workflows/<n>.yml + scripts/<n>.py + core/error_help.py
- پخش روی تلویزیون (DLNA/UPnP، تست در Lab): شاخه lab → lab/dlna_tv.py (UI) + lab/lib/dlna_core.py (SSDP، SOAP، سرور HTTP با Range، دانلود/اسکن)؛ مجوزهای ACCESS_WIFI_STATE/CHANGE_WIFI_MULTICAST_STATE در buildozer.spec (نیاز به Build)
- Lab و Promote: شاخه lab → lab/promote.py، lab/lib/promote_*.py، lab/wf_import.py
- Link Lab و «Get links only (this phone)» (اندازه‌ی کیفیت‌ها، پیشنهاد VPN): شاخه lab → lab/link_lab.py (توابع _phone_*)؛ نمایش جاب‌های Action هنگام ران ورکفلو در Lab: lab/lib/lab_jobs.py (در modules فایل lab/index.json ثبت شده)
- لاگ خطای Lab (هر لینک ناموفق = یک فایل در config/lab-logs/): شاخه lab → lab_scripts/lab_log.py (نوشتن فایل، پنهان‌کردن توکن/کانفیگ) + lab_scripts/lab_log_push.py (commit به config؛ ۳۰۰ فایل آخر) + استفاده در lab_scripts/links.py و download.py (متغیر LAB_LOG_MODE) + مرحله‌ی آخر lab-links.yml و lab-download.yml؛ حالت گوشی: دکمه‌ی «Save log of failed links» در lab/link_lab.py (_phone_save_logs)
- نسخه/ساخت APK: version.txt، build-apk.yml، buildozer.spec
- بکاپ پروژه: .github/workflows/backup-project.yml (خروجی: zip در Release)

- عمومی/خصوصی کردن ریپو از Lab (دستی، بدون Build): شاخه lab → lab/repo_visibility.py
- آرشیو README قدیمی: docs/README_ARCHIVE.md
## گزارش گراف کد (Graphify)
- docs/GRAPH_REPORT.md (~۵۶KB، شاخه main): کامیونیتی‌ها و نودهای پرارتباط (Navigator، run_in_background، Label، Button ...). فقط وقتی REPO_MAP برای پیدا کردن فایل کافی نبود (مثلاً «این تابع از کجا صدا زده می‌شود»)، فقط بخش لازم را بخوان. روزانه با graph-report.yml به‌روز می‌شود — graphify query روی Termux قابل نصب نیست (tree-sitter build fail)؛ جایگزین ندارد.

## قوانین کار
- تغییر ظاهری/متنی → معمولاً فقط main. افزودن منبع دانلود → معمولاً config.json در شاخه config.
- workflowهای lab-* در هر دو شاخه main و lab هستند (نسخه‌ها متفاوت‌اند)؛ قبل از تغییر، شاخه‌ی درست را مشخص کن.
- فایل بزرگ (navigator.py، fa_strings_more.py، releases.py، history.py) را کامل بازنویسی نکن؛ فقط بخش لازم.
