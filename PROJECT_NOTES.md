# YT Bridge — خلاصه‌ی فنی پروژه

## معماری کلی

اپ اندرویدی (Python/Kivy) که به‌جای سرور شخصی، از **GitHub Actions به‌عنوان بک‌اند سرورلس** استفاده می‌کند. اپ فقط دیسپچ ورک‌فلو می‌کند، وضعیت را پول می‌کند، و لینک نهایی (از GitHub Releases) را نشان می‌دهد.

**ریپازیتوری**: `github.com/redi2213/yt-downloader`
**برنچ فعال**: `V4` (`package.name = ytbridge_v4`)، قابل نصب هم‌زمان با `V3`
**برنچ کانفیگ ریموت**: `config` (مستقل از نسخه‌ی اپ، مشترک بین همه‌ی build ها)

## لایه‌بندی کد (Refactor شده)

---

## ذخیره‌سازی: ریلیز گیت‌هاب و/یا آروان‌کلاد (حالت قدیمی)

> **وضعیت فعلی:** این «حالت ذخیره‌سازی» غیرفعال است (`api/storage_prefs.get_mode()` همیشه `github` برمی‌گرداند). آروان حالا با ورک‌فلوهای جدا و بخش «Arvan files» کار می‌کند؛ پایین‌تر را ببین.

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


---

## آپدیت ۲ از ۳ (۲۰ مهر): ستینگ دسته‌بندی‌شده، فارسی + RTL، تم/رنگ/فونت/اندازه، پوشه ذخیره

- **ستینگ**: صفحه‌ی اول فقط ۶ دکمه دارد: Appearance and language / Downloads and storage / Notifications and health / Account and sign-in / App tools / About.
  هر گروه صفحه‌ی خودش را دارد (`settings.build_section`)؛ بازگشت هر گروه به منوی ستینگ است.
- **ظاهر** (`screens/appearance.py`، `core/appearance.py`، `api/appearance_prefs.py`):
  زبان (انگلیسی پیش‌فرض / فارسی)، ۷ تم آماده، رنگ دلخواه برای ۶ بخش (پس‌زمینه، متن، دکمه‌ها و منوها، متن دکمه، کارت‌ها، آیتم انتخاب‌شده) با پالت یا کد `#RRGGBB`،
  فونت، اندازه‌ی متن و اندازه‌ی کادرها/دکمه‌ها (۴ پله). تم `classic` همان ظاهر همیشگی است و تا وقتی انتخاب باشد هیچ ویجتی دست نمی‌خورد.
- **چطور اعمال می‌شود** (`screens/style.py`): `Widget.add_widget` یک بار در `main.py` پچ می‌شود؛ هر ویجتی که روی صفحه می‌آید یک بار استایل می‌گیرد
  (رنگ، فونت، اندازه) و در حالت فارسی متنش ترجمه، شکل‌دهی (arabic_reshaper + bidi) و راست‌چین می‌شود؛ ردیف‌های افقی برعکس می‌شوند.
  متن اصلی انگلیسی در `widget._ytb_src` می‌ماند (کلید Back دکمه‌ی «Back» را با آن پیدا می‌کند). Spinner و ToggleButton ترجمه نمی‌شوند (کد متنشان را مقایسه می‌کند).
  `CARD` و `CARD_ON` در `screens/common.py` حالا list هستند تا تم آن‌ها را در جا عوض کند.
- **ترجمه** (`core/i18n.py`، `core/fa_strings.py`): `EXACT` = متن کامل، `PATTERNS` = متن‌هایی با عدد/نام. متنی که در جدول نباشد انگلیسی می‌ماند؛ برای اضافه کردن فقط همین فایل را ویرایش کن.
- **فونت**: فهرست = فونت پیش‌فرض + فایل‌های ttf/otf داخل `assets/fonts/` (مثلاً `Vazirmatn-Regular.ttf` را آنجا بگذار و دوباره بساز) + چند فونت سیستمی اندروید که روی گوشی باشند.
  متن فارسی با فونتی که فارسی ندارد به DejaVuSans برمی‌گردد.
- **پوشه ذخیره** (`api/download_folder_prefs.py`، `core/android_files.pick_folder`، `core/android_downloads._save_in_tree`):
  پیش‌فرض `Download/Yt-bridge` (MediaStore)؛ با «Change folder» پوشه‌ی دلخواه (انتخاب‌گر پوشه‌ی اندروید، دسترسی دائمی) و گزینه‌ی زیرپوشه بر اساس نوع.
  اندروید خود پوشه‌ی اصلی Download را قبول نمی‌کند. اگر پوشه‌ی انتخابی از دسترس برود فایل در پوشه‌ی پیش‌فرض ذخیره می‌شود.
- **Auto follow**: دکمه‌ی «Files» از صفحه‌ی کانال برداشته شد. در Release History (صفحه‌ی اول) برای هر کانال یک دکمه هست: «Auto follow channel: <نام>  [NEW n] / files of this channel».
  بازگشت از فایل‌های کانال به Release History است.


---

## آپدیت ۳ از ۳ (۲۱ مهر): صفحه Downloads، مدیر دانلود، دانلود چندتکه‌ای

- **مسیر دانلود**: هر «Download in app» (نتیجه‌ی اجرا، APK، بکاپ، گزارش پلی‌لیست) از `core/download_manager.run()` رد می‌شود
  (`android_downloads.download_to_downloads` به آن واگذار شده). مدیر: صف با «تعداد فایل همزمان»، `Task` زنده برای هر فایل، Pause / Resume / Stop،
  بعد از موفقیت ذخیره در پوشه‌ی ذخیره و ثبت در `api/downloads_history.py` (۳۰۰ مورد آخر). Pause جای خودش در صف را آزاد می‌کند.
- **چندتکه‌ای** (`core/segmented_download.py`): با `Range: bytes=a-b` فایل به N تکه (۱ تا ۱۶، هر تکه حداقل ۱ مگابایت) تقسیم و همزمان در جای خودش نوشته می‌شود.
  تکه‌ای که قطع شود از همان‌جا ادامه می‌دهد (۵ بار تلاش)، پس Pause و قطع اینترنت هزینه‌ای ندارند. سروری که Range نداشته باشد با یک جریان خوانده می‌شود (و بعد از قطع از اول).
  لینک‌های ریلیز خصوصی GitHub (API + توکن) هم Range را می‌پذیرند چون ریدایرکت به آدرس امضاشده است.
- **Create empty file first**: پیش از اولین بایت فایل با حجم نهایی ساخته می‌شود؛ در اندروید با `java.io.RandomAccessFile.setLength()` (pyjnius) و در غیر این صورت `truncate`.
  توجه: `setLength` فایل را با حجم نهایی می‌سازد اما در بیشتر فایل‌سیستم‌های اندروید «sparse» است؛ تضمین نمی‌کند بلوک‌ها پشت‌سرهم رزرو شوند.
- **تنظیمات** (`api/download_manager_prefs.py`، ستینگ > Downloads and storage > Download manager): تکه‌ها (۱،۲،۴،۸،۱۶ - پیش‌فرض ۴)، فایل همزمان (۱ تا ۴ - پیش‌فرض ۲)، ساخت فایل خالی (پیش‌فرض روشن).
- **صفحه Downloads** (`screens/downloads.py`، دکمه‌ی خانه): جستجو در نام فایل‌ها + فیلتر نوع (All / Video / Audio / APK / Zip / Other)،
  کارت‌های زنده (هر ثانیه در جا به‌روز می‌شوند، نه بازسازی) با Pause / Resume / Stop، و فایل‌های ذخیره‌شده با Open / Share / Delete (حذف خود فایل با تأیید دوباره‌زدن).
  «Clear list» فقط فهرست را پاک می‌کند، نه فایل‌ها.
- **محدودیت‌ها**: کارهای نیمه‌تمام بعد از بستن برنامه ادامه پیدا نمی‌کنند (فقط در همان اجرای برنامه Pause/Resume کار می‌کند). فایل‌های لاگ (`save_text_file`) در این فهرست نیستند.
- تست‌های بیرون از گوشی (سرور محلی با Range): چندتکه، قطع اتصال، Pause/Resume، Stop، صف و آزادشدن جا هنگام Pause.


---

## کیفیت کنار حجم برای همه‌ی ابزارها + «Another quality» (۲۱ مهر)

- **اصل کار** (از تو): ورک‌فلو یک بلوک مخفی `<!--ytb-quality:{...}-->` در توضیح ریلیز می‌نویسد، `releases.py` آن را می‌خواند و `result.py` / `history.py` نشان می‌دهند.
  فقط `download.yml` (یوتیوب) این بلوک را می‌ساخت.
- **حالا همه‌ی ابزارها**: `scripts/quality_probe.py` هر فایل ویدیو/صوت را اندازه می‌گیرد (ffprobe؛ اگر نبود کیفیتِ نوشته‌شده در نام فایل مثل `_720p_30fps`).
  `storage_publish.py` آن را خودش صدا می‌زند: `publish` (Any site تک‌لینکی، Aparat، Telegram، Filimo، Google Play)، `upload` + `finalize` (چندلینکی: Any site، Upload file).
  برای ورک‌فلوهایی که ریلیز را خودشان می‌سازند (`drive-to-release.yml`، `mediafire-to-release.yml`) دستور جدید `storage_publish.py quality --file ... --tag ...` و یک step بعد از ساخت ریلیز اضافه شد.
- **هر فایل کیفیت خودش را دارد**: بلوک یک کلید `by_file` دارد (نام فایل -> resolution/codec/fps/audio_only)؛ بالای بلوک مشخصات فایل اول یا `QUALITY_META` یوتیوب می‌ماند.
  اپ (`quality_label(body, name)`) نام فایل را بدون توجه به فاصله و نویسه‌های خاص مقایسه می‌کند، چون GitHub نام asset را عوض می‌کند. اگر چند فایل بود و نام پیدا نشد، حدس نمی‌زند.
  صفحه‌ی نتیجه با چند فایل، کیفیت‌های متفاوت را در یک خط می‌نویسد (`720p H264 · 360p H264`).
- **Another quality**: برای ابزارهای Download Anything فرم همان ابزار را با ورودی‌های قبلی باز می‌کند (`show_action_input(action, initial=...)`)، برای یوتیوب صفحه‌ی YouTube Download با لینک.
- فونت اپ ایموجی ندارد (🎬 مربع می‌شد)، پس متن ساده است: `Quality: 1080p VP9` و دکمه‌ی `Another quality` (ترجمه‌ی فارسی دارد).
- ویدیوی عمودی (مثلاً 1080x1920) ۱۰۸۰p نوشته می‌شود، نه ۱۹۲۰p.

- **چرا Any site / Upload file کیفیت نمی‌نوشتند (۲۲ مهر)**: نتیجه‌ی هر پای matrix (`meta-IDX.json`) فقط وقتی جمع می‌شد که ذخیره‌سازی `arvan` یا `both` بود
  (هم step آپلود artifact و هم job `finalize` شرط داشتند). در حالت پیش‌فرض `github` هیچ‌وقت کیفیت به توضیح ریلیز نمی‌رسید. شرط‌ها برداشته شد؛
  `finalize` در حالت github اگر کیفیتی نبود هنوز چیزی را عوض نمی‌کند.
- `quality_probe.py`: اگر روی runner `ffprobe` نبود، یک بار `ffmpeg` را با apt نصب می‌کند (فقط وقتی `GITHUB_ACTIONS=true`)، پس برای همه‌ی ورک‌فلوها بدون تغییر YAML کار می‌کند.

---

## به‌روزرسانی‌های آبان ۱۴۰۵ (تا نسخه‌ی ۲٫۴۲)

### آروان‌کلاد (روش جدید، مستقل از حالت ذخیره‌سازی قدیمی)
- ورک‌فلوها: `arvan-upload.yml` (آپلود فایل‌های ریلیز با asset id)، `arvan-from-link.yml` (دانلود لینک مستقیم و آپلود)، `arvan-manage.yml` (`action=list|delete|rename`). همه با `scripts/arvan_tool.py`؛ کلیدها از Secretهای `ARVAN_ACCESS_KEY/SECRET_KEY/BUCKET/ENDPOINT`، فایل‌ها زیر یک prefix ثابت.
- لیست کل باکت به‌صورت asset به اسم `arvan-list.json` در ریلیز `arvan-index` می‌آید؛ هر ران manage دوباره آن را می‌نویسد (`services/arvan_service.py`).
- UI: Release History > «Arvan files» (انتخاب، کپی لینک، تغییر نام، حذف) و «To Arvan» روی فایل‌ها (`screens/arvan.py`، منطق در `screens/arvan_controller.py` که به Navigator اضافه شده: `Navigator(ArvanController)`).

### نگه‌داری فایل‌ها (retention)
- `scripts/retention_core.py` (مشترک بین اپ و ورک‌فلو، `core/retention.py` فقط واسط است): فایل‌های ریلیزهای `run-*`، `auto-*` و ربات تلگرام (`tg-*`/`url-*`) بعد از **۷ روز** پاک می‌شوند؛ `job-*` فعلاً دست‌نخورده (`JOB_EXPIRES=False`). فایل‌های قدیمی Auto follow و ربات تا `GRACE_UNTIL` مهلت دارند.
- کاربر می‌تواند تاریخ حذف یک فایل را عقب بیندازد یا «forever» کند؛ در توضیح ریلیز به‌صورت بلوک `<!--ytb-keep:{...}-->` نوشته می‌شود (تاریخ حذف = دیرترین بین تاریخ عادی و تاریخ نوشته‌شده). پیش‌تنظیم‌ها: ۳، ۷، ۱۴، ۳۰ روز. صفحه‌های `show_extend_prompt` و `show_deadlines`.
- `cleanup-releases.yml` هر روز ساعت ۰۳:۰۰ UTC اجرا می‌شود (ریلیزهای بدون فایل + فایل‌های منقضی؛ APK و بکاپ نگه داشته می‌شوند؛ `dry_run` دارد) با `scripts/cleanup_releases.py`. ورک‌فلوی `standalone-cleanup-all-artifacts.yml` مستقل از اپ است و همه‌ی artifactها را پاک می‌کند.

### یوتیوب
- **کادر هوشمند** (`screens/youtube_download.py`، `core/youtube_links.py`): نوع لینک (ویدیو / پلی‌لیست / کانال) تعیین می‌کند کدام دکمه‌ها بیایند. برای یک ویدیو «More from this video's channel» (آخرین یا پربازدیدترین ویدیوهای کانال) هم هست.
- **دانلود دسته‌ای** (`download-batch.yml`، `scripts/batch_download.py`): چند ویدیو در یک ران روی گیت‌هاب، `max_parallel` (۱ تا ۲۰، پیش‌فرض ۶)؛ برای هر ویدیو یک خط `RESULT` چاپ می‌شود که اپ می‌خواند و هر ویدیو ریلیز `run-<id>` خودش را دارد؛ اپ می‌تواند بسته باشد.

### Any site
- **نسخه‌ی گوشی** (`services/anysite_phone_service.py`): خود گوشی صفحه را با yt-dlp می‌خواند (IP گوشی)، فقط فرمت‌هایی که تک‌فایل و دارای تصویر و صدا هستند پیشنهاد می‌شوند و لینک انتخابی به `upload-file.yml` می‌رود. محدودیت: لینکِ وابسته به IP گوشی ممکن است هنگام دانلود روی گیت‌هاب ۴۰۳ بدهد (`show_anysite_phone_formats`).
- **پروکسی / v2ray**: Settings > Downloads and storage > «Proxy / v2ray config». کانفیگ به‌صورت Secret با نام `V2RAY_CONFIG` ذخیره می‌شود و قابل خواندن نیست (فقط «saved / not saved»)؛ باکس v2ray در Any site برای همان یک ران جای آن را می‌گیرد. `scripts/xray_setup.py` یک Xray SOCKS5 محلی (`127.0.0.1:10808`) از share link، اشتراک یا JSON می‌سازد و فقط برای خواندن صفحه است؛ اگر نشد فقط هشدار می‌دهد و ادامه می‌دهد.
- `find-proxies.yml` پروکسی‌های رایگان کارآمد را در `working_proxies.txt` برنچ config نگه می‌دارد.

### Mornye (موسیقی lossless، فقط روی گوشی)
- `api.zarz.moe` به IP رانرهای گیت‌هاب چالش Cloudflare می‌دهد، پس لینک‌ها از شبکه‌ی خود گوشی گرفته می‌شود (`api/mornye.py`، `services/mornye_link_service.py`): لینک Spotify ← لیست ترک‌ها ← ISRC و Tidal id ← نشست امضاشده (یک بار تأیید مرورگر و چسباندن کد؛ حدود ۲ ساعت) ← لینک مستقیم FLAC.
- دانلود روی گوشی: `core/mornye_download.py`؛ فایل DASH بدون ffmpeg به FLAC تبدیل می‌شود (`core/fmp4_flac.py`) و تگ و کاور با `core/flac_tags.py` نوشته می‌شود.
- گزینه‌ی روی گیت‌هاب: `mornye-from-links.yml` + `scripts/mornye_fetch.py` (لینک‌ها از گوشی می‌آید، ورک‌فلو فقط دانلود و انتشار می‌کند). لاگ بدون راز بعد از هر اجرا در `logs/` برنچ config ذخیره می‌شود.

### Lab و پلاگین‌ها
- پلاگین = فایل پایتون با `def build(host)`. منبع (`core/plugin_loader.py`): `lab` (برنچ `lab`، پوشه‌ی `lab/`، ابزارهای در حال آزمایش)، `config` (برنچ config، پوشه‌ی `plugins/`، ابزارهای نهایی در Download Anything)، `bundled` (پوشه‌ی `plugins_bundled/` داخل APK).
- کد از طریق GitHub API با توکن خود اپ خوانده می‌شود و آخرین نسخه‌ی سالم روی گوشی می‌ماند. هنگام بالا آمدن اپ هیچ پلاگینی اجرا نمی‌شود، فقط وقتی کاربر بازش کند (پلاگین خراب جلوی باز شدن اپ را نمی‌گیرد).
- `screens/plugin_host.py` شیء `host` را می‌سازد (show/replace/back، title/text/button/input/choice، status و ...)، `screens/plugin_runner.py` اجرا می‌کند، `screens/lab.py` فهرست `lab/index.json` را نشان می‌دهد. حذف `screens/lab.py` دکمه‌ی Lab را از صفحه‌ی اصلی برمی‌دارد.
- ورک‌فلوهای Lab: `lab-run.yml` فقط stub ثبت‌نام است (تعریف واقعی روی برنچ `lab` اجرا می‌شود)؛ `lab-download`، `lab-links`، `lab-workflow` (Pinterest)، `lab-find-proxies`، `lab-refresh-configs`. `lab-schedule.yml` روی main است چون زمان‌بندی فقط از main اجرا می‌شود و هر ۱۲ ساعت پروکسی‌ها و هر ۲۴ ساعت کانفیگ‌ها را روی برنچ lab تازه می‌کند (تنظیم در `lab/default_sources.json`). `lab_examples` و `tests` در بیلد APK نمی‌آیند.

### موارد دیگر
- **اعلان اندروید** (`core/android_notify.py`): با pyjnius ساخته می‌شود؛ لمس آن اپ را روی همان job باز می‌کند (`core/android_share.py` شناسه‌ی job و run را به Navigator می‌دهد). در صورت شکست به plyer برمی‌گردد.
- **بررسی نسخه‌ی جدید** (`core/version_check.py`، `services/update_check_service.py`): نسخه‌ی اپ با `version.txt` برنچ main مقایسه می‌شود؛ بیلد از برنچ‌های دیگر مثل `2.25-dev.7` است.
- **اینستاگرام**: ورک‌فلوی `instagram-downloader.yml`.
- **ظاهر**: صفحه‌ی `show_appearance_date` (نمایش تاریخ). **صفحه‌ی اصلی**: کادر «Paste any link here» + Go.
- **بیلد**: آیکون و presplash در `assets/`، مجوزهای جدید (`ACCESS_NETWORK_STATE`، `WAKE_LOCK`، `FOREGROUND_SERVICE`، `VIBRATE`، `READ_MEDIA_*`).
- **Secretها**: `V2RAY_CONFIG` و `PROXY` به لیست قبلی اضافه شدند.
