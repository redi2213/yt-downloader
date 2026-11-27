# DIAG_TOOLS (فهرست ابزارهای تست و عیب‌یابی)

هدف: Claude قبل از اینکه از کاربر بخواهد چیزی را دستی تست کند، فقط این فایل را بخواند و اول از ابزار موجود استفاده کند. ابزار جدید ساخته شد، همان لحظه اینجا ثبت شود.

## روال
1. Claude فایل `diag-jobs/next.json` را در شاخه‌ی config می‌نویسد (id، title، steps؛ هر step = یک id از جدول پایین + آرگومان‌هایش مثل url) و به کاربر فقط می‌گوید «Lab > Diagnostics > Run Claude's job را بزن». کاربر چیزی تایپ نمی‌کند.
   **اجرای خودکار (۱۴۰۵/۰۹/۰۶):** وقتی اپ باز است و Lab > Diagnostics یک‌بار باز شده باشد (کلید «Auto-run Claude's jobs: ON»، پیش‌فرض روشن)، یک حلقه‌ی پس‌زمینه هر ۱۵ ثانیه `diag-jobs/next.json` را می‌خواند و job با `id` جدید را خودش اجرا می‌کند و نتیجه را در `diag-results/latest.txt` می‌نویسد؛ پس نیازی به زدن دکمه نیست. Claude بعد از نوشتن job، حدود ۳۰ ثانیه بعد latest.txt را چک می‌کند و اگر خط `job: <id>` همان id نبود، یعنی اپ بسته است یا Diagnostics باز نشده؛ آن‌وقت از کاربر بخواه فقط اپ را باز کند. id هر job باید یکتا باشد (job با id تکراری دوباره اجرا نمی‌شود). (برای کار ساده‌ی بدون آرگومان، دکمه‌ی خود step هم هست.)
2. کاربر می‌گوید «انجام شد» (لازم نیست چیزی بچسباند). Claude فایل `diag-results/latest.txt` را از شاخه‌ی config می‌خواند.
3. اگر ابزار مناسب نبود: یک step جدید در `lab/diag.py` (شاخه lab، بدون Build) اضافه کن (تابع `step_xxx(host)` + یک خط در `STEPS`) و همین‌جا ثبت کن. چند مرحله = چند step، و «Run all» همه را پشت‌سر هم اجرا می‌کند.

## نمونه‌ی job (config/diag-jobs/next.json)
```json
{"id": "یک-شناسه-یکتا", "title": "شرح کوتاه", "steps": [{"step": "probe", "url": "https://..."}, {"step": "media_test"}]}
```
نتیجه با خط `job: <id>` شروع می‌شود تا معلوم باشد کدام job اجرا شده.

## Diagnostics (شاخه lab → lab/diag.py؛ ثبت در lab/index.json؛ منوی Lab > Diagnostics)
| دکمه (id) | کار |
|---|---|
| Run all (all) | همه‌ی دکمه‌های زیر پشت‌سر هم |
| Environment (env) | زمان، نسخه‌ی python و kivy، پلتفرم، فضای خالی |
| yt-dlp version (ytdlp) | نسخه‌ی yt-dlp روی گوشی |
| Network reach (net) | دسترسی و زمان پاسخ GitHub، YouTube، Google از گوشی |
| GitHub access (github) | ریپو، دسترسی توکن، rate limit، شاخه‌ها |
| Last workflow runs (runs) | ۸ اجرای آخر workflow (نام، وضعیت، شاخه، لینک) |
| Lab failed-link logs (lablogs) | تعداد و ۵ نام آخر در config/lab-logs/ |
| Page probe (probe) | ورودی: لینک صفحه. صفحه را از گوشی می‌گیرد و سرنخ ویدیو را لیست می‌کند: iframe، source/video، og:video، لینک‌های m3u8/mp4/mpd، کلیدهای JSON/JS. اگر چیزی نبود یعنی ویدیو با JavaScript بارگذاری می‌شود. فقط در job (آرگومان url) یا از دکمه‌ی Page probe |
| Context grep (context) | فقط در job. آرگومان‌ها: pattern (regex)، url (خالی = صفحه‌ی probe شده؛ مسیر نسبی هم قبول است، مثلاً فایل JS)، width، limit. متن اطراف تطابق‌ها را نشان می‌دهد. با `label` می‌شود عنوان هر بخش را مشخص کرد |
| Media link test (media_test) | فقط در job. آرگومان‌ها: url (خالی = لینک‌های پیدا شده توسط probe قبلی در همان job)، referer، count. با Range و stream فقط ۱KB اول را می‌گیرد: وضعیت HTTP، هدرهای مهم، ftyp (نشانه‌ی mp4 واقعی) و متن بدنه اگر mp4 نبود؛ برای لینک اول ۴ حالت: rnd+ref+range (آدرس با `&rnd=<ms>` مثل پلیر واقعی)، rnd+ref+kt_tcookie، بدون rnd، و بدون ref/cookie (کوکی‌ها از probe همان job می‌آیند). لینک‌های get_stream زمان‌دارند، پس probe و media_test را در یک job بگذار |
| Redirect trace (redirects) | فقط در job. آرگومان‌ها: url (خالی = لینک‌های probe همان job)، referer، count، hops. ریدایرکت لینک‌های get_stream را دستی hop به hop دنبال می‌کند (وضعیت و Location هر hop، با Referer و بدون Referer) و همین کار را با yt-dlp urlopen هم می‌کند (مثل _phone_final_url در Link Lab): آدرس نهایی یا خطا |
| Link Lab rows (phone_rows) | فقط در job. آرگومان: url (خالی = صفحه‌ی probe). فرمت‌های yt-dlp برای صفحه (height و url) و ردیف‌هایی که _phone_kvs می‌سازد (h، size، url) را نشان می‌دهد؛ برای پیدا کردن منشأ ردیف «unknown height». نیاز دارد Lab > Link Lab یک بار باز شده باشد |
| Session test (session_test) | فقط در job. آرگومان‌ها: url (لینک صفحه)، count. صفحه را می‌خواند و بلافاصله لینک‌های تازه‌ی get_stream را درخواست می‌کند، سه‌بار با سه روش: host.get (نشست ماندگار اپ)، requests.Session تازه، و یک YoutubeDL (مثل Link Lab). وضعیت، آدرس نهایی بعد از ریدایرکت و نام کوکی‌های ارسال‌شده را چاپ می‌کند: برای فهمیدن اینکه get_stream به کوکی صفحه نیاز دارد یا نه |
| Rubika API test (rubika_api_test) | فقط در job. آرگومان‌ها: url (لینک صفحه‌ی vod.rubika.ir/media/<id>)، auth (خالی = auth تصادفی مهمان). از گوشی getMedia ← getSeasonEpisodes ← getPlayInfo ← خواندن master playlist را می‌زند و وضعیت هر مرحله را می‌نویسد (بدون توکن). برای تست ورکفلو rubika_vod |
| JS scan (js_scan) | فقط در job. آرگومان‌ها: url (صفحه)، pattern (regex؛ پیش‌فرض: کلمات ثبت‌نام/کلید عمومی)، width، limit. صفحه و همه‌ی chunkهای /_next آن را از گوشی می‌گیرد و متن اطراف تطابق‌ها را با نام فایل نشان می‌دهد؛ برای فهمیدن روش ثبت‌نام/امضای API یک وب‌اپ |
| JS save (js_save) | فقط در job. آرگومان‌ها: url، find (متن دقیق)، before، length، name. اولین chunk جاوااسکریپت صفحه که find را دارد پیدا می‌کند و تکه‌ای از آن را در config/diag-results/<name> ذخیره می‌کند تا Claude کد را بخواند |
| Network identity (net_identity) | job یا دکمه. کشور و شرکت ارائه‌دهنده‌ی اینترنت فعلی گوشی (ipinfo، بدون چاپ IP چون ریپو عمومی است)، IPv4/IPv6، پروکسی در محیط، و نوع آدرس سایت (آرگومان site). برای فهمیدن اینکه VPN/پروکسی/IP دیتاسنتر باعث «error 1» شده یا نه |
| HLS link test (hls_ip_test) | job. آرگومان‌ها: url (خالی = جدیدترین m3u8 که مرورگر داخلی گرفته؛ ویدیو را اول در مرورگر داخلی باز کن)، referer. از گوشی (IP ایران): کشور/شرکت اینترنت، وضعیت playlist، کلید AES و ۱KB اول سگمنت؛ برای مقایسه با ۴۰۳ ران گیت‌هاب (حدود چند KB داده). |

خروجی: `config/diag-results/latest.txt` (آخرین اجرا) + `<زمان>-<id>.txt` (۲۰ تای آخر). توکن، کوکی و هدر Authorization پنهان می‌شود. سقف: ۶۰۰۰ کاراکتر برای هر مرحله، ۲۴۰۰۰ کل. ریپو عمومی است، پس نتیجه برای همه خوانا است. روی صفحه هم دکمه‌ی Copy دارد.

## Browser capture (شاخه lab → lab/diag_browser.py؛ منوی Lab > Browser capture)
برای سایت‌هایی که با کلاینت ساده (yt-dlp، python) خطا می‌دهند ولی در مرورگر واقعی کار می‌کنند. Claude کار را در `config/diag-jobs/browser.json` می‌نویسد: `url`، `wait_s` (پیش‌فرض ۴۰)، `pattern` (regex آدرس‌های مهم)، `desktop`، `auto_play`. کاربر Lab > Browser capture > «Start Claude's browser job» را می‌زند (اگر ویدیو خودکار پخش نشد یک بار روی play می‌زند). خروجی در `latest.txt`: آدرس نهایی، user agent، نام کوکی‌ها، وضعیت و حجم درخواست‌های مدیا در مرورگر، وضعیت عناصر video، و تست fetch داخل صفحه (۱KB اول، با همان کوکی‌ها) با hex و متن بایت‌های اول.

## ابزارهای موجود دیگر (جزئیات در REPO_MAP.md)
- مرورگر داخلی > Menu > Inspect page (to share): کپی HTML صفحه، لینک‌ها، navigation log (دستی؛ کاربر کپی می‌کند)
- مرورگر داخلی > Export cookies > Network requests: لاگ Fetch/XHR، Copy as cURL، Copy response body (دستی)
- Lab > Link Lab: هر لینک ناموفق خودکار یک فایل در `config/lab-logs/` می‌شود
- Lab > Get links only (با گوشی): کیفیت‌های یک لینک با yt-dlp روی گوشی
- Lab > Add workflow: اجرا، Check و گزارش خطای قابل کپی برای workflowها
- Lab > Page Sniffer: گرفتن m3u8 با ورود کاربر
- Lab > Copy tools: کپی امن workflow یا plugin برای تست
