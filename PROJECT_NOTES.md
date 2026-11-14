# YT Bridge — یادداشت‌های فنی (خلاصه‌شده 2026-11-14)

> فقط وقتی لازم شد بخوان (مرجع جزئیات رفتار قابلیت‌ها). ساختار فایل‌ها: REPO_MAP.md. لایه‌بندی: ARCHITECTURE.md.
> این فایل از روی نسخه‌ی قدیمی‌تر فشرده شد. قابلیت‌های جدیدتر (آبان ۱۴۰۵ به بعد: Downloads هوشمند، تاریخ شمسی، انتخاب/حذف موازی در History و ...) اینجا نیستند؛ برای آن‌ها کد را بخوان.

## کلیات
- اپ اندروید (Python/Kivy) با GitHub Actions به‌عنوان بک‌اند سرورلس: اپ workflow را dispatch می‌کند، وضعیت را poll می‌کند و لینک نهایی (GitHub Releases) را نشان می‌دهد.
- ریپو: redi2213/yt-downloader. شاخه‌ها: main (کد+workflowها)، config (کانفیگ ریموت، مستقل از نسخه‌ی اپ)، lab (آزمایشی)، backup. `package.name = ytbridge_v4`.
- نسخه: `version.txt` با هر بیلد موفق `build-apk.yml` یکی بالا می‌رود (بیلد ناموفق شماره نمی‌سوزاند)؛ APK با اسم `YT-Bridge-<نسخه>.apk`؛ `core/_version.py` و `version =` در `buildozer.spec` موقع بیلد ساخته می‌شوند. آپدیت از داخل اپ هرگز `version.txt` را عوض نمی‌کند (`repo_update_service.PROTECTED_FILE`).
- پوشه‌ی دانلود: `Download/Yt-bridge/<دسته>` (APK, Backup, YouTube, Aparat, Telegram, Filimo, Any-site, Auto, Browser, Logs, Other) از `core/android_downloads.category_for_workflow`. پوشه‌ی دلخواه با `api/download_folder_prefs.py`.

## چطور ران پیدا و نشان داده می‌شود
- `api/github/workflows.dispatch_and_find_run` ورودی‌ها + `job_id` یکتا (و `run_title`, `rerun`) می‌فرستد؛ workflow آن‌ها را در `run-name` می‌گذارد تا اپ ران خودش را پیدا کند.
- خروجی در ریلیز `run-<run_id>`؛ بلوک‌های مخفی در توضیح ریلیز: `ytb-quality`, `ytb-storage`, `ytb-keep` (خوانده‌شده در `api/github/releases.py`).
- **Run again** (`core/rerun.py`): ورودی‌ها (zlib+base64url) در اسم ران: `<عنوان> [<توکن>] ~<ورودی‌ها>`؛ workflowها ورودی اختیاری `rerun` دارند و اگر نشناسند (HTTP 422) بدون آن دوباره فرستاده می‌شود. `job_id/run_title/storage/arvan_bucket` تکرار نمی‌شوند.
- لیست ران‌ها: `services/runs_service.py`, `screens/runs_browser.py` (Runs by workflow / by app menu، صفحه‌بندی، اجرای دستی با `name=value`، Copy error، Download log).

## کیفیت کنار حجم
- `scripts/quality_probe.py` (ffprobe؛ در نبودش کیفیت از نام فایل؛ در صورت نبودن ffprobe روی runner خودش ffmpeg نصب می‌کند) و `storage_publish.py` بلوک `ytb-quality` را با کلید `by_file` (نام فایل ← resolution/codec/fps/audio_only) می‌نویسند.
- اپ نام فایل را بدون توجه به فاصله/نویسه‌ی خاص مقایسه می‌کند (GitHub نام asset را عوض می‌کند)؛ اگر چند فایل بود و نام پیدا نشد حدس نمی‌زند. ویدیوی عمودی 1080x1920 → 1080p.
- فونت اپ ایموجی ندارد؛ متن ساده («Quality: 1080p VP9»).
- «Another quality»: فرم همان ابزار با ورودی‌های قبلی (`show_action_input(action, initial=...)`)؛ یوتیوب: صفحه‌ی YouTube Download با لینک.
- سابقه‌ی باگ: در حالت ذخیره‌ی `github` کیفیتِ matrix (Any site/Upload file) ثبت نمی‌شد چون شرط روی `arvan/both` بود؛ برداشته شد.

## ذخیره‌سازی و آروان‌کلاد
- حالت قدیمی Storage (`github|arvan|both`) **غیرفعال** است (`api/storage_prefs.get_mode()` همیشه `github`). ورودی‌های `storage`/`arvan_bucket` هنوز به `STORAGE_WORKFLOWS` در `api/github/workflows.py` فرستاده می‌شوند و در 422 بدون آن‌ها تکرار می‌شوند. `scripts/storage_publish.py` ریلیز را می‌سازد (`publish`، `upload`+`finalize` برای matrix، `quality`، `--append`، `--split`).
- روش جدید: `arvan-upload.yml`، `arvan-from-link.yml`، `arvan-manage.yml` (`list|delete|rename`) با `scripts/arvan_tool.py`؛ Secretها `ARVAN_ACCESS_KEY/SECRET_KEY/BUCKET/ENDPOINT` (باکت‌های بیشتر: `ARVAN_2_...`). لیست باکت: asset `arvan-list.json` در ریلیز `arvan-index`. UI: Release History > «Arvan files»، «To Arvan» (`screens/arvan.py`, `arvan_controller.py`، mixin در Navigator). مقدار Secret با `core/sealedbox.py` رمز می‌شود (توکن باید اجازه‌ی نوشتن Secret داشته باشد).
- API آروان ترافیک باقی‌مانده را نمی‌دهد.

## نگه‌داری فایل‌ها (retention)
- `scripts/retention_core.py` (مشترک اپ/ورک‌فلو): فایل‌های `run-*`, `auto-*`, `tg-*`/`url-*` بعد از ۷ روز پاک می‌شوند؛ `job-*` دست‌نخورده. کاربر می‌تواند عقب بیندازد/forever کند (بلوک `ytb-keep`؛ پیش‌تنظیم ۳/۷/۱۴/۳۰ روز).
- `cleanup-releases.yml` هر روز 03:00 UTC (`dry_run` دارد؛ APK و بکاپ می‌مانند)؛ `standalone-cleanup-all-artifacts.yml` و `cleanup-artifacts.yml` برای artifactها.

## Release History و Downloads
- History صفحه‌ای: ۲۰ فایل در هر صفحه (`HISTORY_PAGE_SIZE = 20`)؛ ریلیزها ۱۰۰تا۱۰۰تا خوانده می‌شوند. فقط تگ‌های `run-`/`job-` در لیست اصلی؛ `auto-*` جداست (دکمه‌ی هر کانال Auto follow).
- مسیر «Download in app»: `core/download_manager.run()` (صف، Pause/Resume/Stop، ثبت در `api/downloads_history.py`)، دانلود چندتکه‌ای با Range (`core/segmented_download.py`: ۱ تا ۱۶ تکه، هر تکه ≥۱MB، ۵ بار تلاش؛ سرور بدون Range = یک جریان)، ساخت فایل خالی (`RandomAccessFile.setLength`، sparse). کار نیمه‌تمام بعد از بستن اپ ادامه نمی‌یابد.
- Open/Share بعد از دانلود: `core/android_open.py` (نیاز به `Saved.location`، اندروید ۱۰+). نصب APK: `core/android_install.py`.

## یوتیوب / آپارات / Any site
- کادر هوشمند یوتیوب (`core/youtube_links.py`): نوع لینک (ویدیو/پلی‌لیست/کانال) دکمه‌ها را تعیین می‌کند. دانلود دسته‌ای: `download-batch.yml` + `scripts/batch_download.py` (`max_parallel` ۱ تا ۲۰، پیش‌فرض ۶، خط `RESULT` برای هر ویدیو).
- اجرای روی گوشی (Settings > Run on: Auto/GitHub/Phone، `api/run_mode_prefs.py`): فقط لیست پلی‌لیست و کیفیت‌های یک ویدیو با yt-dlp داخل اپ (`services/phone_youtube_service.py`)؛ کیفیت گوشی فقط ارتفاع دارد (شناسه‌ی فرمت SABR گیت‌هاب نیست). دانلود فایل همیشه روی GitHub.
- Any site (`Any-Site-Upload.yml`): کیفیت `check` فقط فرمت‌ها را می‌سازد (`FORMATS_JSON={...}` در لاگ)؛ `format_id` اختیاری؛ برای کیفیت عددی/highest بین هم‌رزولوشن‌ها کم‌حجم‌ترین انتخاب می‌شود (حجم با Range از هدر)؛ استخراج: ۳ تلاش معمولی، ۳ تلاش `--impersonate chrome`، آخر yt-dlp nightly. اپ: `"handler": "anysite"` در config.json، `services/anysite_service.py`, `screens/anysite_formats.py`. نسخه‌ی گوشی: `services/anysite_phone_service.py` (محدودیت: لینک وابسته به IP گوشی ممکن است روی GitHub 403 بدهد).
- پروکسی/v2ray: Secret `V2RAY_CONFIG` (فقط «saved/not saved»)، `scripts/xray_setup.py` (SOCKS5 محلی `127.0.0.1:10808`، فقط برای خواندن صفحه)، `find-proxies.yml` ← `working_proxies.txt` در config.

## Series Links و Auto follow
- `Series-Links.yml`: از لینک یک قسمت لینک کل سریال را می‌سازد/چک می‌کند، `links.txt` در ریلیز `run-<id>`، در حالت upload با `upload-file.yml`؛ نتیجه با `UPLOAD_RELEASE_TAG=run-N` در نت‌های ریلیز (`generic_action_service._finish_action`).
- Auto follow (`screens/follow.py`, `services/follow_service.py`, `core/follow.py`, `scripts/auto_follow.py`, `Auto-Follow.yml`): داده روی config: `follows.json` (اپ می‌نویسد) و `follow-state.json` (فقط workflow می‌نویسد). cron: ابتدا مرحله‌ی ارزان `--due-only`؛ اگر نوبتی بود workflow عادی dispatch می‌شود (`download.yml` یوتیوب، `aparat-download.yml` آپارات) با `release_tag=auto-<slug>` و `split_large=true`؛ `concurrency: auto-follow`.
- cron را اپ کوتاه می‌کند (`core.follow.cron_for`، دقیقه‌های ۷ و ۳۷ UTC) و `follow_service.sync_schedule` خط `- cron:` را روی **شاخه‌ی پیش‌فرض** عوض می‌کند (توکن باید مجوز `workflow` داشته باشد؛ وگرنه cron پیش‌فرض `17 * * * *`).
- ریلیز ثابت `auto-<slug>` با `--append`؛ فایل ۲GB+ با ffmpeg به `name.part1.mkv`… (نشد: تکه‌های خام). حالت‌ها `series` (شماره‌ی قسمت از عنوان) و `latest`؛ فیلتر طول/کلمه؛ آپارات فقط `latest`. محدودیت: dispatch شده‌ی خطادار خودکار تکرار نمی‌شود (ویدیو «دیده‌شده» است)، ntfy خطا را می‌فرستد. `LIST_LIMIT=120`.
- لینک ویدیوی تکی رد می‌شود (`core.follow.looks_like_video`).

## ntfy، راهنمای خطا، Health
- ntfy: آخرین step ورک‌فلوها؛ topic در `ntfy.json` روی config (خالی = خاموش)؛ `list-formats.yml` و `list-playlist.yml` فقط روی خطا.
- راهنمای خطای فارسی: `error_help` در config.json (`{id, match:[متن|re:regex], title, tip}`، ۲ مورد اول)؛ پشتیبان داخلی `core/error_help.py`.
- Health (`services/health_service.py`): توکن، نسخه/شاخه، `REQUIRED_WORKFLOWS`، نام Secretها، دقیقه‌های Actions (فقط توکن classic با scope `user`).

## ظاهر و فارسی
- `screens/style.py`: `Widget.add_widget` یک‌بار در `main.py` پچ می‌شود؛ هر ویجت استایل می‌گیرد؛ در حالت فارسی ترجمه + arabic_reshaper + bidi + راست‌چین؛ متن اصلی در `widget._ytb_src` (Back با آن دکمه را پیدا می‌کند). Spinner/ToggleButton ترجمه نمی‌شوند. `CARD`/`CARD_ON` list هستند.
- ترجمه: `core/i18n.py` + `core/fa_strings*.py` (`EXACT` متن کامل، `PATTERNS` الگو). متن بدون ورودی انگلیسی می‌ماند؛ فقط همین فایل‌ها را ویرایش کن.
- تم `classic` = ظاهر اصلی (هیچ ویجتی دست نمی‌خورد). فونت‌ها: `assets/fonts/` (فارسی نداشتن ← DejaVuSans).
- Download Anything: هر action با `"group"` پشت دکمه‌ی گروه می‌رود (`actions_dynamic.build_group`)، اپ قدیمی `group` را نادیده می‌گیرد.

## Mornye (فقط گوشی)
- `api.zarz.moe` به IP رانرهای GitHub چالش Cloudflare می‌دهد، پس لینک‌ها از شبکه‌ی گوشی گرفته می‌شود (`api/mornye.py`, `services/mornye_link_service.py`): Spotify ← ترک‌ها ← ISRC/Tidal id ← نشست امضاشده (تأیید مرورگر، ~۲ ساعت) ← لینک FLAC. DASH بدون ffmpeg به FLAC (`core/fmp4_flac.py`)، تگ/کاور `core/flac_tags.py`. روی GitHub: `mornye-from-links.yml` + `scripts/mornye_fetch.py`؛ لاگ‌ها در `logs/` شاخه‌ی config.

## Lab و پلاگین‌ها
- پلاگین = فایل پایتون با `def build(host)`؛ منبع (`core/plugin_loader.py`): `lab` (شاخه‌ی lab، پوشه‌ی `lab/`)، `config` (پوشه‌ی `plugins/`)، `bundled` (داخل APK؛ در حال حاضر پوشه‌ی `plugins_bundled/` در main نیست). کد با توکن خود اپ خوانده می‌شود؛ در شروع اپ هیچ پلاگینی اجرا نمی‌شود. `screens/plugin_host.py` (شیء `host`)، `plugin_runner.py`، `lab.py` (فهرست `lab/index.json`؛ حذف `lab.py` دکمه‌ی Lab را برمی‌دارد).
- `lab-run.yml` فقط stub ثبت‌نام است (تعریف واقعی روی شاخه‌ی lab)؛ `lab-schedule.yml` روی main است چون cron فقط از main اجرا می‌شود (پروکسی هر ۱۲ ساعت، کانفیگ هر ۲۴ ساعت، تنظیم در `lab/default_sources.json`). `lab_examples` و `tests` در بیلد APK نمی‌آیند.

## مرورگر داخلی
- `screens/browser.py` + WebView اندروید؛ pyjnius نمی‌تواند `WebViewClient` را ارث ببرد، پس `java/org/redi2213/ytbridge/BrowserHelper.java` (`android.add_src = java`) و `core/android_browser.py` هر ۰٫۵ ثانیه `poll()`. تشخیص: درخواست‌های mp4/webm/mkv/mov/m3u8/mpd/mp3/m4a (با Referer/UA/کوکی) + اسکن `<video>/<source>/og:video`؛ `blob:` نادیده. داده در `core/browser_media.py`.
- دانلود (`Navigator.browser_download`): فایل مستقیم ← مدیر دانلود (`Download/Yt-bridge/Browser`)؛ خطا ← GitHub (Any site)؛ HLS/DASH ← GitHub؛ یوتیوب ← دانلود عادی. محدودیت: فقط HTTPS؛ HLS/DASH/یوتیوب روی خود گوشی نیست؛ Referer/کوکی به GitHub نمی‌رسد؛ `blob:` (MSE) دانلود نمی‌شود. Back اول در تاریخچه‌ی WebView (`Navigator.back_hook`).

## موارد دیگر
- اعلان اندروید: `core/android_notify.py` (pyjnius؛ لمس ← job/run)، fallback plyer. بررسی نسخه: `services/update_check_service.py` (با `version.txt` شاخه‌ی main؛ بیلد شاخه‌های دیگر مثل `2.25-dev.7`).
- Google Drive: `drive-to-release.yml` (`job_id/run_title/rerun`, ریلیز `run-<id>`)، group `upload` در config.json.
- مجوزهای بیلد: `REQUEST_INSTALL_PACKAGES`, `ACCESS_NETWORK_STATE`, `WAKE_LOCK`, `FOREGROUND_SERVICE`, `VIBRATE`, `READ_MEDIA_*`.
- Secretها: `ARVAN_*`, `V2RAY_CONFIG`, `PROXY`.
