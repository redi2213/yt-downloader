# YT Bridge — خلاصه‌ی فنی پروژه

## معماری کلی

اپ اندرویدی (Python/Kivy) که به‌جای سرور شخصی، از **GitHub Actions به‌عنوان بک‌اند سرورلس** استفاده می‌کند. اپ فقط دیسپچ ورک‌فلو می‌کند، وضعیت را پول می‌کند، و لینک نهایی (از GitHub Releases) را نشان می‌دهد.

**ریپازیتوری**: `github.com/redi2213/yt-downloader`
**برنچ فعال**: `V4` (`package.name = ytbridge_v4`)، قابل نصب هم‌زمان با `V3`
**برنچ کانفیگ ریموت**: `config` (مستقل از نسخه‌ی اپ، مشترک بین همه‌ی build ها)

## لایه‌بندی کد (Refactor شده)

---

## ذخیره‌سازی: ریلیز گیت‌هاب و/یا آروان‌کلاد

اپ یک انتخاب سه‌حالته دارد (دکمه‌ی «Storage» در صفحه‌ی اصلی، یا Settings ← Storage): `github` (پیش‌فرض)، `arvan`، `both`.
انتخاب با دو ورودی `storage` و `arvan_bucket` به هر workflowی که فایل می‌سازد فرستاده می‌شود
(`api/github/workflows.py` ← `STORAGE_WORKFLOWS`): download، upload-file، Any-Site-Upload، filimo-direct-link،
google-play-download، aparat-download، telegram-download. اگر فایل workflow این ورودی‌ها را نشناسد (خطای ۴۲۲)،
بدون آن‌ها دوباره فرستاده می‌شود و فایل روی گیت‌هاب می‌ماند.

**Secretهای مخزن** (Settings ← Secrets and variables ← Actions) - باکت اصلی:
`ARVAN_ACCESS_KEY` و `ARVAN_SECRET_KEY`؛ اختیاری: `ARVAN_BUCKET` (پیش‌فرض `my-files-telegram`)،
`ARVAN_ENDPOINT` (پیش‌فرض `https://s3.ir-thr-at1.arvanstorage.ir`)، `ARVAN_QUOTA_GB` (پیش‌فرض ۵).
باکت‌های بیشتر: همین نام‌ها با عدد در وسط: `ARVAN_2_ACCESS_KEY`، `ARVAN_2_BUCKET` و ...
اپ آن‌ها را از Settings ← Storage ← Add a bucket می‌سازد/حذف می‌کند (توکن باید اجازه‌ی نوشتن Secret داشته باشد:
توکن classic با scope `repo`، یا GitHub App با «Secrets: Read and write»). مقدارها داخل اپ با `core/sealedbox.py`
(sealed box سازگار با libsodium، پایتون خالص، بدون PyNaCl) رمز می‌شوند.

**طرز کار**
- `scripts/storage_publish.py` (صدازده‌شده از workflowها) اول به باکت ترجیحی آپلود می‌کند؛ اگر پر باشد (فضای خالی
  روی کل باکت حساب می‌شود) یا فایل را نپذیرد، به باکت بعدی می‌رود. کلید فایل `ytbridge/run-<id>/<name>` و لینک عمومی است.
- `github` = رفتار قبلی. `arvan` = فقط آروان؛ اگر آروان شکست بخورد فایل روی گیت‌هاب می‌ماند و هشدار نوشته می‌شود.
  `both` = هر دو (فایل ۲ گیگ به بالا فقط روی آروان می‌ماند).
- لینک‌ها و هشدارها در توضیحات ریلیز به‌صورت بلوک پنهان `<!--ytb-storage:{json}-->` نوشته می‌شوند
  (خوانده‌شده در `api/github/releases.py`). ریلیز فقط‌آروان هیچ asset ندارد.
- workflowهای ماتریسی (upload-file، Any-Site-Upload): هر پایه آپلود می‌کند و یک artifact کوچک می‌سازد؛
  job به اسم `finalize` همه را در توضیحات ریلیز ادغام می‌کند.
- `arvan-maintenance.yml`: هر روز فایل‌های این پروژه (پیشوند `ytbridge/`) که بیشتر از ۷ روز دارند را پاک می‌کند
  (فایل‌های دیگر باکت مشترک، مثل فایل‌های ربات تلگرام، دست نمی‌خورند). با `action=info` (از Settings ← Storage ←
  Arvan usage and files) حجم مصرفی و لیست فایل‌ها را در توضیحات یک ریلیز می‌نویسد.
- خروجی «links» آپارات و حالت «Direct link only» فیلیمو هنوز asset گیت‌هاب‌اند (اپ متن را می‌خواند).
- API ذخیره‌سازی آروان ترافیک باقی‌مانده را نمی‌دهد؛ صفحه‌ی usage همین را می‌گوید (پنل آروان را ببین).

---

## نسخه، پوشه‌ی دانلود، مرورگر ران‌ها (۱۸ مهر)

- **نسخه‌ی خودکار**: فایل `version.txt` (مثلاً `2.4`) با هر بیلد **موفق** یکی بالا می‌رود (۲٫۱، ۲٫۲، ...). `build-apk.yml` نسخه‌ی بعدی را حساب می‌کند،
  `core/_version.py` (گیت‌ایگنور، مثل `_branch.py`) و `version =` در `buildozer.spec` را می‌سازد، APK را با اسم `YT-Bridge-<نسخه>.apk` منتشر می‌کند
  و آخر کار `version.txt` را روی همان برنچ کامیت می‌کند. بیلد ناموفق شماره نمی‌سوزاند. نسخه در About و اسم بکاپ (`project-backup-v2.4-...zip`) دیده می‌شود.
  آپدیت از داخل اپ هرگز `version.txt` را عوض نمی‌کند (`repo_update_service.PROTECTED_FILE`).
- **پوشه‌ی دانلود**: هر چیزی که اپ دانلود می‌کند در `Download/Yt-bridge/<دسته>` ذخیره می‌شود: APK, Backup, YouTube, Aparat, Telegram, Filimo, Any-site, Logs, Other
  (`core/android_downloads.py` ← `category_for_workflow`). دکمه‌ی «Download in app» روی همه‌ی صفحه‌های نتیجه و گزارش پلی‌لیست هست.
- **نصب APK**: بعد از دانلود APK دکمه‌ی Install، نصب‌کننده‌ی اندروید را روی فایل ذخیره‌شده باز می‌کند (`core/android_install.py`؛ پرمیشن `REQUEST_INSTALL_PACKAGES`).
- **آخرین ران‌ها**: دو دکمه‌ی «Runs by workflow» (همه‌ی ورک‌فلوهای ریپو) و «Runs by app menu» (گروه‌ها). ران‌ها صفحه‌به‌صفحه (Previous/Next)،
  اجرای دستی هر ورک‌فلو با خطوط `name=value`، و در ران خطادار: قدم خطادار + Copy error + Download log (`services/runs_service.py`, `screens/runs_browser.py`).
- **یوتیوب**: کادرها چندخطی‌اند؛ چند لینک در Quick Download = برای هر لینک یک ران جدا. پلی‌لیست فقط لینک اول را می‌خواند. دکمه‌ی Best به پلی‌لیست اضافه شد.
- **آپارات**: فرم نوع لینک را تشخیص می‌دهد (`screens/aparat_form.py`)، Output دو مرحله‌ای است، صفحه‌ی انتخاب ویدیو دکمه‌های کیفیت دارد.

---

## دور دوم (۱۸ مهر): لاگ، Result، حجم، اجرا روی گوشی، اسم ران‌ها

- **لاگ**: هر ران (نه فقط خطادار) دکمه‌ی Copy log / Download log دارد؛ **Result** فایل‌های ریلیز همان ران را با حجم و Download in app نشان می‌دهد.
- **گزارش پلی‌لیست** روی گوشی ذخیره می‌شود (`core/playlist_reports.py`) و از «Playlist reports» در آخرین ران‌ها دوباره باز می‌شود.
- **حجم فایل** روی همه‌ی صفحه‌های نتیجه و APK/Backup (`file_download_service.start_sizes`).
- **اجرا روی گوشی**: Settings > Run on (Auto / GitHub / Phone) در `api/run_mode_prefs.py`؛ فقط «لیست ویدیوهای پلی‌لیست» و «کیفیت‌های یک ویدیو» با yt-dlp داخل اپ
  (`services/phone_youtube_service.py`). کیفیت‌های گوشی فقط ارتفاع دارند (`bestvideo[height<=N]`) چون شناسه‌های فرمت گیت‌هاب (SABR) روی گوشی نیست؛ دکمه‌ی
  «Full list from GitHub (codecs)» لیست کامل را می‌دهد. در حالت Auto اگر گوشی نتواند، همان کار روی گیت‌هاب اجرا می‌شود. دانلود فایل همیشه روی گیت‌هاب است.
- **اسم ران‌ها**: عنوان همان‌طور که هست (فارسی هم)، ۲ بار تلاش؛ Any-Site-Upload.yml و filimo-direct-link.yml حالا `run_title` و `job_id` را می‌شناسند.


---

## Any site: Check formats (۱۹ مهر)

- `Any-Site-Upload.yml`: کیفیت `check` فقط لیست فرمت‌ها را می‌سازد (جدول در لاگ/Summary، artifact `formats-N` و یک خط `FORMATS_JSON={...}` در لاگ)؛ چیزی دانلود/آپلود نمی‌شود.
  ورودی جدید `format_id` (اختیاری): اگر پر باشد همان فرمت دقیق دانلود می‌شود و کیفیت نادیده گرفته می‌شود.
- برای کیفیت عددی/highest: بین فرمت‌های هم‌رزولوشن، کم‌حجم‌ترین انتخاب می‌شود (حجم از هدر سرور با درخواست Range خوانده می‌شود چون Eporner حجم نمی‌دهد).
- استخراج با ۳ تلاش معمولی، ۳ تلاش با `--impersonate chrome`، و در آخر yt-dlp nightly؛ در شکست نهایی لاگ verbose چاپ می‌شود (خطای ناپایدار `Unable to extract hash` در Eporner).
- اپ: اکشن `any_site_upload` در config.json حالا `"handler": "anysite"` و گزینه‌ی کیفیت «Check formats» دارد.
  `services/anysite_service.py` ران را اجرا می‌کند و `FORMATS_JSON` را از لاگ جاب‌های `link N` می‌خواند؛ `screens/anysite_formats.py` فرمت‌ها را دکمه‌دکمه نشان می‌دهد
  (کم‌حجم‌ترین هر رزولوشن علامت دارد)؛ لمس یک دکمه یک ران معمولی با `format_id` و فقط همان لینک می‌فرستد (`generic_action_service._resolve_inputs`).
  APK قدیمی گزینه‌ی Check را ندارد؛ اگر `handler` را نشناسد فقط ران عادی می‌فرستد.


---

## بسته‌ی اول ۲۸ مهر: Run again، ntfy، راهنمای خطا، Health، Series Links

- **Run again** (`core/rerun.py`, `services/runs_service.py`): GitHub ورودی‌های ران را نمی‌دهد، پس اپ ورودی‌ها را (zlib+base64url، یک خط) در **اسم ران** می‌گذارد:
  `<عنوان> [<توکن ۱۲hex>] ~<ورودی‌ها>`. ورک‌فلوها ورودی اختیاری `rerun` دارند و `run-name` آن‌ها `${{ inputs.rerun && format(' ~{0}', inputs.rerun) || '' }}` را اضافه می‌کند
  (`_dispatch_and_find_run` اول با rerun می‌فرستد، اگر ورک‌فلو نشناخت HTTP 422 → بدون آن). لیست ران‌ها این دنباله را پنهان می‌کند. دکمه‌ی **Run again** در صفحه‌ی هر ران:
  ورودی‌ها از اسم خوانده می‌شود؛ اگر نبود (ران قدیمی/دستی)، صفحه‌ی اجرای دستی با `name=value` پر می‌شود (ورودی‌ها از خود فایل ورک‌فلو). `job_id/run_title/storage/arvan_bucket` تکرار نمی‌شوند (توکن و ذخیره‌ساز فعلی دوباره ساخته می‌شود).
- **ntfy**: آخرین قدم ورک‌فلوها (`Notify (ntfy)`؛ برای ورک‌فلوهای چندجابی یک job به اسم `notify`) پیام می‌فرستد. topic در Settings > Notifications تنظیم می‌شود و در فایل **`ntfy.json`** برنچ `config`
  (`{"topic": "...", "server": "https://ntfy.sh"}`) ذخیره می‌شود؛ ورک‌فلو آن را با `GITHUB_TOKEN` از API می‌خواند، پس چیزی به ورک‌فلوها داده نمی‌شود. topic خالی = خاموش.
  `list-formats.yml` و `list-playlist.yml` فقط وقتی خطا بدهند پیام می‌فرستند (نویز نشود). `arvan-maintenance.yml`/cleanup/zip-release نوتیف ندارند.
- **راهنمای خطای فارسی**: کلید `error_help` در `config.json` (برنچ config): لیست `{id, match:[متن یا re:regex], title, tip}`؛ ۲ مورد اول که بخورد زیر دکمه‌های Copy error نشان داده می‌شود.
  نسخه‌ی داخلی در `core/error_help.py` (`DEFAULT_PATTERNS`) برای وقتی که config خوانده نشود. `services/error_help_service.py`.
- **Health** (Settings > Health check): توکن (معتبر/دسترسی/تاریخ انقضا)، نسخه و برنچ، ورک‌فلوهای ضروری، Secretها (فقط نام)، دقیقه‌های Actions این ماه (`services/health_service.py`, `screens/health.py`).
  دقیقه‌ها فقط با توکن classic دارای scope `user` خوانده می‌شود؛ ریپوی public رایگان است. لیست `REQUIRED_WORKFLOWS` و `SECRET_SPECS` بالای فایل سرویس است.
- **Series Links** (`Series-Links.yml`، دکمه‌ی «Series links» در Download Anything از config.json): از لینک یک قسمت، لینک کل سریال را می‌سازد/چک می‌کند، `links.txt` + نت‌ها را در ریلیز `run-<id>` می‌گذارد،
  و در حالت upload فایل‌ها را با `upload-file.yml` آپلود می‌کند. نتیجه‌ی upload در ریلیز فرزند است: ورک‌فلو `UPLOAD_RELEASE_TAG=run-N` را در نت‌های ریلیز می‌نویسد و `generic_action_service._finish_action` همان را نشان می‌دهد.


---

## بسته‌ی دوم ۲۸ مهر: Auto follow (دنبال کردن کانال و دانلود زمان‌بندی‌شده)

- **منوی «Auto follow»** در صفحه‌ی اصلی (`screens/follow.py`, `services/follow_service.py`, `core/follow.py`): لیست کانال‌ها، افزودن (اول فقط لینک، بعد فرم با کشویی/سوئیچ)، صفحه‌ی هر کانال
  (Files با نشانک NEW، Check now، Pause/Resume، Edit، Delete)، «Check all channels now» و «Update schedule».
- **داده‌ها روی برنچ `config`**: `follows.json` (اپ می‌نویسد؛ فرمت کانال در سربرگ `scripts/auto_follow.py`) و `follow-state.json` (فقط ورک‌فلو می‌نویسد؛ آخرین قسمت، ویدیوهای دیده‌شده، آخرین بررسی) تا هیچ‌وقت هم را بازنویسی نکنند.
- **زمان‌بند** `.github/workflows/Auto-Follow.yml`: cron → اول مرحله‌ی ارزان `--due-only` (آیا کانالی در بازه‌ی خودش «نوبتی» است؟)؛ اگر نه همان‌جا تمام می‌شود (حدود ۱ دقیقه Actions).
  اگر بله: yt-dlp، `scripts/auto_follow.py` لیست کانال را می‌گیرد، ویدیوهای جدید را انتخاب می‌کند و **ورک‌فلوهای عادی را dispatch می‌کند** (`download.yml` برای یوتیوب، `aparat-download.yml` برای آپارات) با ورودی‌های `release_tag=auto-<slug>` و `split_large=true`؛
  بعد state را روی برنچ config کامیت می‌کند و ntfy می‌فرستد (فقط اگر چیزی شروع شد یا خطا بود). `concurrency: auto-follow` جلوی اجرای هم‌زمان را می‌گیرد.
- **cron را اپ کوتاه می‌کند**: `core.follow.cron_for` فقط ساعت‌هایی از UTC را می‌گذارد که بازه‌ی کانال‌ها لازم دارد (دقیقه‌های ۷ و ۳۷؛ ایران UTC+3:30) و `follow_service.sync_schedule` خط `- cron: '...'` فایل ورک‌فلو را روی **برنچ پیش‌فرض ریپو** عوض می‌کند
  (ورک‌فلوی زمان‌بندی‌شده فقط از آن‌جا اجرا می‌شود). توکن باید مجوز `workflow` داشته باشد؛ وگرنه پیام می‌دهد و cron پیش‌فرض (ساعتی، `17 * * * *`) می‌ماند.
- **ریلیز ثابت هر کانال** `auto-<slug>`: `storage_publish.py publish --append [--split]` به ریلیز موجود اضافه می‌کند (نام تکراری → تاریخ جلوی نام)، فایل ۲ گیگ+ را با ffmpeg (segment) به بخش‌های قابل‌پخش `name.part1.mkv`… می‌شکند (اگر نشد: تکه‌های خام `.part1`).
  لیست Release History فقط تگ‌های `run-`/`job-` را نشان می‌دهد، پس ریلیزهای `auto-` خودکار جدا هستند. فایل‌ها در گوشی به `Download/Yt-bridge/Auto` می‌روند (`releases._tag_for` تگ `auto-...` را هم می‌فهمد).
- **حالت‌ها**: `series` (شماره‌ی قسمت از عنوان، فارسی/انگلیسی؛ قسمت بعدی = بزرگ‌تر از آخرین قسمت، حداکثر تا قسمت پایان) و `latest` (هر N روز، ویدیوهای جدید). نقطه‌ی شروع: از همین حالا / از قسمت N / از تاریخ / N ویدیوی آخر هم.
  فیلتر: حداقل/حداکثر طول (یوتیوب)، کلمه‌های لازم/ممنوع در عنوان. توقف: قسمت، تاریخ یا تعداد. آپارات: فقط `latest`، گزینه‌ی zip، بدون فیلتر طول.
- **محدودیت‌ها**: ورک‌فلوهای دانلود بعد از dispatch مستقل‌اند؛ اگر یکی خطا بدهد دوباره خودکار تکرار نمی‌شود (ویدیو «دیده‌شده» حساب شده)، ntfy خطا را می‌فرستد و در صفحه‌ی ران، Run again هست.
  ذخیره‌ی Arvan برای این ریلیزها استفاده نمی‌شود (فقط GitHub).

- **Files کانال خودکار = همان صفحه‌ی Release History** (`nav.show_follow_history`): `releases.get_live_history(tag)` فقط فایل‌های ریلیز `auto-<slug>` را می‌دهد؛ همان کارت‌ها (انتخاب، Copy، Share، Rename، Zip، Delete، حذف گروهی) و دکمه‌ی بالا برای «Download in app / copy all links».
  لیست اصلی Release History هنوز فقط `run-`/`job-` را نشان می‌دهد (خودکارها شلوغش نمی‌کنند؛ منوی خانه با `show_release_history` فیلتر را پاک می‌کند). `LIST_LIMIT` اسکریپت زمان‌بند ۱۲۰ است (کلیپ‌های روزانه قسمت‌های قدیمی را از ۴۰ ویدیوی آخر بیرون می‌اندازد).

- **فرم Auto follow ساده و تاشو** (`screens/follow.py`): فقط لینک، نام، «Series / Latest» و Save همیشه دیده می‌شود؛ سؤال‌های هر حالت فقط وقتی انتخاب شد می‌آید (Series: از قسمت N + حداقل طول؛ Latest: هر چند روز + بار اول؛ آپارات: بدون Series/فیلتر طول و با zip).
  بخش‌های «When to check»، «Quality and amount»، «More options» بسته‌اند و خلاصه‌شان در عنوان است (با لمس باز می‌شوند). فرم با تغییر Series/Latest، اسپینر «بار اول» و نوع لینک (یوتیوب/آپارات/ویدیوی تکی) دوباره کشیده می‌شود و مقدارها در `draft` می‌مانند.
  لینک ویدیوی تکی (youtu.be/…، watch?v=…) رد می‌شود: برای دنبال کردن لینک **کانال** لازم است (`core.follow.looks_like_video`).


---

## آپدیت ۱ از ۳ (۲۰ مهر): تاریخچه صفحه‌ای، Open/Share، Google Drive

- **Release History صفحه‌ای**: هر صفحه ۲۰ فایل (نه ۲۰ ریلیز) با دکمه‌های Previous/Next (`releases.get_live_history_page`، `HISTORY_PAGE_SIZE = 20`).
  قبلاً فقط ۳۰ ریلیز اول خوانده می‌شد و ریلیزهای غیر `run-`/`job-` (مثل `auto-*`) حذف می‌شدند، برای همین حدود ۱۵ فایل می‌ماند.
  حالا ریلیزها ۱۰۰ تا ۱۰۰ تا خوانده می‌شوند تا صفحه پر شود؛ صفحه‌ی بعد از آخر (مثلاً بعد از حذف) به آخرین صفحه برمی‌گردد.
  لیست یک کانال Auto follow صفحه‌بندی نمی‌شود.
- **Open file / Share file** (`core/android_open.py`): بعد از «Download in app» برای هر فایل ذخیره‌شده یک ردیف «Open: نام» (منوی «Open with…» اندروید، هر بار) و «Share» (خود فایل، نه لینک)
  هست (حداکثر ۸ ردیف). صفحه‌ی APK/Backup هم دکمه‌های Open file و Share file دارد. نیازمند `Saved.location` (content uri، اندروید ۱۰+).
- **Google Drive**: `drive-to-release.yml` حالا مثل بقیه ابزارها `job_id` / `run_title` / `rerun` را می‌شناسد، ریلیز را `run-<run id>` می‌سازد
  (`release_tag` دستی اختیاری است) و ntfy می‌فرستد. دکمه‌اش در `config.json` (برنچ config، نسخه ۱۸) با `"group": "upload"` تعریف شده.
- **گروه در Download Anything**: هر action با `"group": "<نام>"` پشت یک دکمه‌ی گروه می‌رود (`actions_dynamic.build_group`). گروه `upload` = «Upload / import files»
  شامل Upload a file، Any site و Google Drive. نسخه‌های قدیمی اپ فیلد `group` را نادیده می‌گیرند و لیست تخت را نشان می‌دهند.
