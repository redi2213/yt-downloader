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
