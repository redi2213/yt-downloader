# DIAG_TOOLS (فهرست ابزارهای تست و عیب‌یابی)

هدف: Claude قبل از اینکه از کاربر بخواهد چیزی را دستی تست کند، فقط این فایل را بخواند و اول از ابزار موجود استفاده کند. ابزار جدید ساخته شد، همان لحظه اینجا ثبت شود.

## روال
1. اگر برای کار فعلی ابزار مناسب هست: به کاربر بگو «Lab > Diagnostics > دکمه‌ی X را بزن».
2. کاربر می‌گوید «انجام شد» (لازم نیست چیزی بچسباند). Claude فایل `diag-results/latest.txt` را از شاخه‌ی config می‌خواند.
3. اگر ابزار مناسب نبود: یک step جدید در `lab/diag.py` (شاخه lab، بدون Build) اضافه کن (تابع `step_xxx(host)` + یک خط در `STEPS`) و همین‌جا ثبت کن. چند مرحله = چند step، و «Run all» همه را پشت‌سر هم اجرا می‌کند.

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

خروجی: `config/diag-results/latest.txt` (آخرین اجرا) + `<زمان>-<id>.txt` (۲۰ تای آخر). توکن، کوکی و هدر Authorization پنهان می‌شود. سقف: ۶۰۰۰ کاراکتر برای هر مرحله، ۲۴۰۰۰ کل. روی صفحه هم دکمه‌ی Copy دارد.

## ابزارهای موجود دیگر (جزئیات در REPO_MAP.md)
- مرورگر داخلی > Menu > Inspect page (to share): کپی HTML صفحه، لینک‌ها، navigation log (دستی؛ کاربر کپی می‌کند)
- مرورگر داخلی > Export cookies > Network requests: لاگ Fetch/XHR، Copy as cURL، Copy response body (دستی)
- Lab > Link Lab: هر لینک ناموفق خودکار یک فایل در `config/lab-logs/` می‌شود
- Lab > Get links only (با گوشی): کیفیت‌های یک لینک با yt-dlp روی گوشی
- Lab > Add workflow: اجرا، Check و گزارش خطای قابل کپی برای workflowها
- Lab > Page Sniffer: گرفتن m3u8 با ورود کاربر
- Lab > Copy tools: کپی امن workflow یا plugin برای تست
