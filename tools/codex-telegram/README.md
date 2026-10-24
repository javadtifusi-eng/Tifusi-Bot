# پل تلگرام Codex

کپی بدون credential از پل عملیاتی؛ TG_TOKEN و OWNER_ID فقط از environment خوانده می‌شوند. state.json و فایل‌های inbox/کلیدها نباید به گیت اضافه شوند.

اصلاح 2026-10-24: خروجی JSONL هنگام اجرای Codex خوانده می‌شود و فقط item.completed از نوع agent_message، با فاصله حداقل سه ثانیه، پیام وضعیت تلگرام را ویرایش می‌کند. خروجی ابزار/دستور و reasoning ارسال نمی‌شود؛ جواب نهایی و فایل‌ها مثل قبل در پایان ارسال می‌شوند. این تغییر زمان محاسبه مدل را کم نمی‌کند؛ گزارش پیشرفت را تا پایان معطل نمی‌کند.

بررسی: py_compile و اجرای ask_codex با subprocess ساختگی (پیام پیشرفت، عدم ارسال خروجی ابزار، حفظ final و thread_id) موفق. مدل و effort تغییر نکرده‌اند. سند رسمی رویدادها: https://learn.chatgpt.com/docs/non-interactive-mode

Caddyfile.example ورودی کمکی پنل روی https://app.bomalo.ir:8443 را نشان می‌دهد؛ IP این ورودی با سرور VPN فرق دارد، TLS upstream اعتبارسنجی می‌شود و احراز هویت پنل حفظ است. این ورودی جایگزین آدرس ساب/پروفایل نیست. تست HTTP صفحه و API برابر۲۰۰، صفحه دقیقاً برابر پنل اصلی و API محافظت‌شده بدون ورود۴۰۱ بود. تست واقعی از ایران هنوز لازم است؛ دورزدن مسیر endpoint یک فرضیه است، نه علت قطعی گزارش کاربر.

بکاپ زنده: /root/backups/bridge-progress-20261024/codex_tg.py.before و Caddyfile.before؛ برگشت با کپی هر فایل قبل و restart codex-tg/reload caddy. هنگام اجرای درخواست فعال، پل را restart نکنید چون KillMode=control-group آن درخواست را متوقف می‌کند.
