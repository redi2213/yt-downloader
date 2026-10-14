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
