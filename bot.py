# -*- coding: utf-8 -*-
# Tifusi Bot — Copyright (c) 2025-2026 javadtifusi-eng (Tifusi). All rights reserved.
# Source-available, not open source: copying, modifying, redistributing or rebranding
# this code without written permission is prohibited. See LICENSE.
"""ربات فروش اشتراک VPN — تک‌فایلی (همه‌چیز در همین یک فایل) — فقط Tifusi Panel | چندپنلی.
پروتکل‌هایی که فروخته می‌شوند از خود پنل خوانده می‌شوند.
فقط BOT_TOKEN و ADMIN_ID را در بالای فایل پر کنید و اجرا کنید: python bot.py"""
import re
import json
import time
import io
import html
import secrets
import asyncio
import logging
import datetime
import os
import shutil
import tempfile
import weakref

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, WebAppInfo
from telegram.error import RetryAfter, Forbidden, BadRequest
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

import sqlite3
import threading
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("vpn_bot")
logging.getLogger("httpx").setLevel(logging.WARNING)  # httpx logs full URLs, which contain the bot token

# ══════════════════════ تنظیمات — فقط همین دو مقدار را پر کنید ══════════════════════
BOT_TOKEN = ""      # توکن ربات از @BotFather
ADMIN_ID = 0        # آیدی عددی ادمین از @userinfobot
BOT_VERSION = "4.2"
BOT_VERSION_DATE = "2026-09-17"
DEFAULT_PANEL_MAX_USERS = 200   # سقف پیش‌فرض کاربر هر پنل — وقتی پنل به این عدد برسد، خریدهای جدید می‌روند پنل بعدی (تمدیدها همیشه روی همان پنل انجام می‌شوند)
# ════════════════════════════════════════════════════════════════════════════════════



# ══════════════════════ سرویس‌ها (services) ══════════════════════

# همه‌ی سرویس‌هایی که ربات می‌شناسد، به ترتیب دکمه‌های خرید. اینکه کدام‌شان واقعاً فروخته شود از خود پنل
# خوانده می‌شود: سرویسی نشان داده می‌شود که حداقل یک پنل فعال برای یکی از پروتکل‌هایش هاست داشته باشد.
# پس اگر فردا روی پنل مثلاً Hysteria2 یا WireGuard اضافه شد، کافی است ادمین «بررسی اتصال» را بزند
# (یا چک خودکار ۵ دقیقه‌ای برسد) تا در ربات ظاهر شود؛ پروتکلی که هاستش حذف شد هم از فروش خارج می‌شود.
SERVICES = {
    "xray": "Xray",
    "hysteria2": "Hysteria2",
    "ikev2": "IKEv2 · L2TP · PPTP",
    "l2tp": "L2TP",
    "pptp": "PPTP",
    "wireguard": "WireGuard",
}
# پروتکل‌های پنل برای هر سرویس — کاربر ساخته‌شده فقط به همین پروتکل‌ها دسترسی می‌گیرد
SERVICE_PROTOCOLS = {
    "xray": ["vless", "vmess", "trojan", "shadowsocks"],
    "hysteria2": ["hysteria2"],
    # یک پلن برای هر سه: همان نام کاربری و رمز روی IKEv2 و L2TP و PPTP کار می‌کند،
    # پس گوشی جدید و قدیم با یک خرید وصل می‌شوند (تمدید هم دسترسی سفارش‌های قبلی را کامل می‌کند).
    "ikev2": ["ikev2", "l2tp", "pptp"],
    "l2tp": ["l2tp"],
    "pptp": ["pptp"],
    "wireguard": ["wireguard"],
}
# اکانت تست روی اولین سرویسِ در دسترس به همین ترتیب ساخته می‌شود
TEST_SERVICE_ORDER = ["ikev2", "xray", "hysteria2", "l2tp", "pptp", "wireguard"]
# سفارش‌های نسخه‌ی ۴.۰ که یک سرویس کلی Tifusi بودند (بدون محدودیت پروتکل)
GENERIC_ORDER_KEY = "tifusi"


# فونت و نشان‌های کارت تحویل؛ نصب‌کننده آن‌ها را کنار bot.py از همین مخزن می‌گیرد.
ASSET_DIR = "/root/tifusi-bot-assets"
CARD_W = 900
CARD_TILE_H = 128
CARD_GROUND, CARD_PANEL, CARD_HAIR = "#0a0a0a", "#141414", "#232323"
CARD_ACCENT, CARD_TEXT, CARD_MUTED, CARD_DIM = "#f97316", "#f5f5f5", "#8b8b8b", "#d4d4d4"

# سرویس‌هایی که مشتری با نام کاربری و رمز به آن‌ها وصل می‌شود و موقع خرید رمز دلخواه می‌گیرند
IPSEC_SERVICES = {"ikev2", "l2tp", "pptp"}
# رمز فقط ۶ رقم است چون مشتری آن را دستی در تنظیمات VPN گوشی تایپ می‌کند
# (در قاعده‌ی پنل، IPSEC_PASSWORD_PATTERN، هم جا می‌شود)
IPSEC_PASSWORD_RE = re.compile(r"[0-9]{6}")
IPSEC_PASSWORD_RULES = "رمز باید دقیقاً ۶ رقم باشد (فقط عدد)."


# ══════════════════════ آموزش اتصال (training) ══════════════════════

# هر آموزش فقط سیستم‌عامل‌هایی را دارد که برایش معنی دارد؛ اگر یکی باشد مستقیم همان نمایش داده می‌شود
TUT_OS = [("android", "🤖 اندروید"), ("ios", "🍎 آیفون")]

TRAININGS = {
    "ikev2": {
        "title": "🤖 اندروید: IKEv2 (بدون نصب اپ)",
        "android": """🤖 اندروید — IKEv2، با خود تنظیمات گوشی:

1️⃣ تنظیمات ← اتصالات ← تنظیمات بیشتر اتصال ← VPN
   (در گوشی‌های غیرسامسونگ: تنظیمات ← شبکه و اینترنت ← VPN)
2️⃣ «➕ افزودن نمایه‌ی VPN» را بزنید
3️⃣ نام: Tifusi (هر اسمی)
4️⃣ نوع: IKEv2/IPSec MSCHAPv2
5️⃣ نشانی سرور: همان «🌐 سرور» که ربات فرستاده
6️⃣ شناسه‌ی IPSec: نام کاربری خودتان
7️⃣ گواهی CA: «استفاده از گواهی‌های سیستم» — گواهی سرور: «دریافت از سرور»
8️⃣ نام کاربری و رمز عبوری که ربات فرستاده را وارد و ذخیره کنید
9️⃣ روی نمایه بزنید و «اتصال» را بزنید ✅

💡 اگر گزینه‌ی IKEv2 در گوشی‌تان نیست (اندروید ۱۰ و قدیمی‌تر)، از آموزش L2TP استفاده کنید.""",
    },
    "l2tp": {
        "title": "📶 L2TP (گوشی‌های قدیمی‌تر)",
        "android": """🤖 اندروید — L2TP:

1️⃣ تنظیمات ← اتصالات ← تنظیمات بیشتر اتصال ← VPN ← «➕ افزودن نمایه‌ی VPN»
2️⃣ نوع: L2TP/IPSec PSK
3️⃣ نشانی سرور: «🌐 سرور» که ربات فرستاده
4️⃣ کلید از پیش مشترک IPSec: «🔐 سکرت» که ربات فرستاده
5️⃣ نام کاربری و رمز عبور را وارد و ذخیره کنید، بعد «اتصال» را بزنید ✅""",
        "ios": """🍎 آیفون — L2TP:

ساده‌ترین راه: دکمه‌ی « نصب پروفایل آیفون» را بزنید، در Safari باز کنید و از Settings پروفایل را Install کنید.

یا دستی: Settings ← General ← VPN & Device Management ← VPN ← Add VPN Configuration
نوع: L2TP — Server: سرور، Account: نام کاربری، Password: رمز، Secret: سکرت
«Send All Traffic» را روشن بگذارید و Done را بزنید ✅""",
    },
    "pptp": {
        "title": "📟 PPTP (قدیمی‌ترین گوشی‌ها)",
        "android": """🤖 اندروید قدیمی — PPTP:

1️⃣ تنظیمات ← اتصالات ← تنظیمات بیشتر اتصال ← VPN ← «➕ افزودن نمایه‌ی VPN»
2️⃣ نوع: PPTP
3️⃣ نشانی سرور: «🌐 سرور» که ربات فرستاده
4️⃣ «رمزگذاری PPP (MPPE)» را روشن بگذارید
5️⃣ نام کاربری و رمز عبور را وارد و ذخیره کنید، بعد «اتصال» را بزنید ✅

💡 فقط برای گوشی‌هایی که IKEv2 و L2TP ندارند. آیفون PPTP ندارد.""",
    },
    "iphone": {
        "title": "🍎 آیفون / مک",
        "ios": """🍎 آیفون و مک:

1️⃣ «🔗 لینک اشتراک» را لمس کنید تا در Safari باز شود
2️⃣ برای IKEv2: در صفحه‌ی باز شده «نصب مستقیم روی iOS/macOS» را بزنید و اجازه‌ی دانلود پروفایل را بدهید
3️⃣ Settings ← General ← VPN & Device Management ← پروفایل را باز کنید و Install را بزنید
4️⃣ از Settings ← VPN اتصال را روشن کنید

🌐 برای Xray روی آیفون: اپ Streisand یا V2Box را نصب کنید، ➕ را بزنید و لینک اشتراک را به‌عنوان Subscription اضافه کنید.
🔗 برای L2TP: اطلاعات سرور، نام کاربری، رمز و کلید مشترک در همان صفحه‌ی لینک اشتراک نوشته شده است؛ آن‌ها را در Settings ← VPN ← Add VPN Configuration ← L2TP وارد کنید.""",
    },
    "xray": {
        "title": "🌐 Xray با اپ‌های دیگر (v2rayNG / Streisand)",
        "android": """🤖 اندروید (v2rayNG):

1️⃣ اپ v2rayNG را نصب کنید
2️⃣ لینک اشتراک را کپی کنید
3️⃣ منوی ☰ ← Subscription group setting ← ➕ و لینک را اضافه کنید
4️⃣ منوی ⋮ ← Update subscription، یک کانفیگ را انتخاب و ▶️ را بزنید""",
        "ios": """🍎 آیفون (Streisand / V2Box):

1️⃣ اپ Streisand یا V2Box را از اپ‌استور نصب کنید
2️⃣ لینک اشتراک را کپی کنید
3️⃣ ➕ را بزنید و لینک را به‌عنوان Subscription اضافه کنید
4️⃣ یک سرور را انتخاب کنید و اتصال را روشن کنید""",
    },
}


# ══════════════════════ اتصال به Tifusi Panel (panel) ══════════════════════

class PanelError(Exception):
    pass


class TifusiPanelAPI:
    """کلاینت API پنل Tifusi Panel. هر کاربر یک لینک اشتراک می‌گیرد و رمز IKEv2/L2TP او را خود پنل مدیریت می‌کند.

    یک نمونه برای هر پنل نگه داشته می‌شود (panel_client): توکن ورود ۲۴ ساعت معتبر است، پس به‌جای ورود دوباره
    برای هر خرید یک بار وارد می‌شود و فقط وقتی پنل 401 داد دوباره لاگین می‌کند. درخواست‌های یک پنل با قفل
    پشت‌سرهم اجرا می‌شوند چون requests.Session برای استفاده‌ی همزمان از چند thread امن نیست."""

    def __init__(self, url, username, password, timeout=15):
        self.base = url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers.update({"Accept": "application/json"})
        # اول گواهی SSL بررسی می‌شود؛ پنل با گواهی self-signed کار می‌کند ولی insecure=True می‌شود تا به ادمین هشدار داده شود
        self.s.verify = True
        self.insecure = False
        self.token = None
        self.lock = threading.RLock()

    def _u(self, path):
        return self.base + path

    def _send(self, method, path, **kwargs):
        try:
            return self.s.request(method.upper(), self._u(path), timeout=self.timeout, **kwargs)
        except requests.exceptions.SSLError:
            if self.s.verify is False:
                raise PanelError("خطای SSL در اتصال به پنل")
            self.s.verify = False
            self.insecure = True
            try:
                return self.s.request(method.upper(), self._u(path), timeout=self.timeout, **kwargs)
            except requests.RequestException as e:
                raise PanelError(f"خطای اتصال: {e}")
        except requests.RequestException as e:
            raise PanelError(f"خطای اتصال: {e}")

    def login(self):
        with self.lock:
            # کلید API پنل (tifusi_…) به‌جای رمز: نیازی به ورود نیست و با ۲FA ادمین هم کار می‌کند
            if (self.password or "").startswith("tifusi_"):
                self.token = self.password
                self.s.headers.update({"Authorization": f"Bearer {self.password}"})
                return True
            r = self._send("post", "/api/auth/login", json={"username": self.username, "password": self.password})
            if r.status_code == 429:
                raise PanelError("تلاش ورود زیاد بود؛ چند دقیقه بعد دوباره امتحان کنید")
            if r.status_code == 403:
                raise PanelError("حساب ادمین ربات در پنل غیرفعال شده است")
            if r.status_code != 200:
                raise PanelError("ورود به پنل ناموفق بود (آدرس/یوزرنیم/پسورد را چک کنید)")
            try:
                token = r.json().get("access_token")
            except ValueError:
                token = None
            if not token:
                raise PanelError("ورود به پنل ناموفق بود (توکن دریافت نشد)")
            self.token = token
            self.s.headers.update({"Authorization": f"Bearer {token}"})
            return True

    def _call(self, path, method="get", **kwargs):
        with self.lock:
            if not self.token:
                self.login()
            r = self._send(method, path, **kwargs)
            if r.status_code == 401:
                # توکن منقضی یا باطل شده (مثلاً رمز ادمین در پنل عوض شده) — یک بار ورود دوباره
                self.login()
                r = self._send(method, path, **kwargs)
            if r.status_code >= 400:
                try:
                    detail = r.json().get("detail")
                except ValueError:
                    detail = None
                if isinstance(detail, list):  # خطای اعتبارسنجی FastAPI
                    detail = "؛ ".join(str(d.get("msg", d)) for d in detail)
                err = PanelError(str(detail) if detail else f"عملیات ناموفق (HTTP {r.status_code})")
                err.status = r.status_code
                raise err
            if not r.content:
                return None
            try:
                return r.json()
            except ValueError:
                return None

    def list_groups(self):
        """گروه‌های پنل برای نگاشت سرویس ← گروه. پنلی که گروه ندارد همه‌ی سرورهایش عمومی است،
        برای همین یک ردیف «سرورهای عمومی» (بدون گروه، شناسه ۰) هم همیشه اول لیست می‌آید."""
        try:
            obj = self._call("/api/groups") or {}
        except PanelError as e:
            # ادمین ربات در پنل دسترسی «گروه‌ها» ندارد: فقط سرورهای عمومی قابل انتخاب است
            if getattr(e, "status", None) != 403:
                raise
            obj = {}
        groups = obj.get("groups", []) if isinstance(obj, dict) else (obj or [])
        result = [{"id": 0, "name": "سرورهای عمومی (همه‌ی هاست‌های بدون گروه)"}]
        result += [{"id": int(g.get("id")), "name": g.get("name", "") or f"#{g.get('id')}"} for g in groups]
        return result

    def list_protocols(self):
        """{پروتکل: تعداد هاست} برای پروتکل‌هایی که روی پنل حداقل یک هاست دارند.
        پنل‌های جدید endpoint سبک /api/system/protocols دارند؛ پنل قدیمی‌تر از لیست هاست‌ها خوانده می‌شود."""
        try:
            rows = self._call("/api/system/protocols") or []
            return {str(r["protocol"]): int(r.get("hosts") or 0) for r in rows if r.get("protocol")}
        except PanelError as e:
            if getattr(e, "status", None) not in (404, 405):
                raise
        obj = self._call("/api/hosts") or {}
        counts = {}
        for h in obj.get("hosts", []):
            counts[h.get("protocol")] = counts.get(h.get("protocol"), 0) + 1
        return {k: v for k, v in counts.items() if k}

    def find_user(self, username):
        obj = self._call("/api/users", params={"q": username, "limit": 200}) or {}
        for u in obj.get("users", []):
            if u.get("username") == username:
                return u
        return None

    def get_user(self, username):
        try:
            return self.find_user(username)
        except PanelError:
            return None

    def _with_links(self, user):
        links = self._call(f"/api/users/{int(user['id'])}/links") or {}
        return {"user": user, "subscription_url": links.get("subscription_url", ""),
                "app_code": links.get("app_code", ""),
                "ikev2_configs": links.get("ikev2_configs") or [],
                "l2tp_configs": links.get("l2tp_configs") or [],
                "pptp_configs": links.get("pptp_configs") or []}

    def links(self, username):
        """لینک‌ها و اطلاعات اتصال IKEv2/L2TP کاربر همان‌طور که پنل الان می‌دهد؛ None اگر کاربر روی پنل نبود."""
        user = self.find_user(username)
        return self._with_links(user) if user else None

    @staticmethod
    def _limits(total_gb, expire_ts):
        # حجم ۰ یعنی نامحدود؛ انقضا با منطقه‌ی زمانی UTC فرستاده می‌شود
        expire = datetime.datetime.fromtimestamp(int(expire_ts), tz=datetime.timezone.utc).isoformat()
        return expire, (int(total_gb) * 1024 ** 3 if total_gb else None)

    def add_user(self, group_ids, username, total_gb, expire_ts, protocols=None, device_limit=0, ipsec_password=None):
        """protocols: پروتکل‌هایی که کاربر به آن‌ها دسترسی دارد (None = همه). device_limit: سقف دستگاه همزمان (۰ = نامحدود).
        ipsec_password: رمز ورود IKEv2/L2TP؛ None یعنی پنل مثل قبل از رمز خودش استفاده کند."""
        expire, data_limit = self._limits(total_gb, expire_ts)
        body = {"username": username, "status": "active", "expire": expire, "data_limit": data_limit,
                "group_ids": [int(g) for g in group_ids if int(g)], "note": "Tifusi Bot",
                "hwid_limit": int(device_limit or 0) or None}
        if protocols:
            body["protocols"] = list(protocols)
        if ipsec_password:
            body["ipsec_password"] = ipsec_password
        return self._with_links(self._call("/api/users", "post", json=body))

    def renew_user(self, username, total_gb, expire_ts, protocols=None, device_limit=0):
        """همان کاربر به‌روز می‌شود تا لینک اشتراک و شناسه عوض نشوند؛ حجم جدید روی مصرف فعلی اضافه می‌شود
        چون پنل مصرف را صفر نمی‌کند. اگر کاربر روی پنل نبود None برمی‌گرداند."""
        user = self.find_user(username)
        if not user:
            return None
        expire, extra = self._limits(total_gb, expire_ts)
        data_limit = int(user.get("used_traffic") or 0) + extra if extra else None
        body = {"status": "active", "expire": expire, "data_limit": data_limit}
        if device_limit is not None:
            body["hwid_limit"] = int(device_limit) or None
        if protocols:
            body["protocols"] = list(protocols)
        user = self._call(f"/api/users/{int(user['id'])}", "put", json=body)
        return self._with_links(user)

    def set_status(self, username, status):
        """روشن/خاموش کردن کاربر روی پنل (active/disabled)؛ False اگر کاربر روی پنل نبود."""
        user = self.find_user(username)
        if not user:
            return False
        self._call(f"/api/users/{int(user['id'])}", "put", json={"status": status})
        return True

    def del_user(self, username):
        """True اگر حذف شد یا اصلاً روی پنل نبود؛ خطای پنل به‌صورت PanelError بالا می‌رود
        تا بازگشت وجه برای سرویسی که هنوز روی پنل فعال است انجام نشود."""
        user = self.find_user(username)
        if user:
            self._call(f"/api/users/{int(user['id'])}", "delete")
        return True

    def usage(self, username):
        """مصرف کاربر به بایت، یا None اگر پیدا نشد."""
        user = self.find_user(username)
        return int(user.get("used_traffic") or 0) if user else None

    def ping(self):
        t0 = time.time()
        self.login()
        return int((time.time() - t0) * 1000)


# ══════════════════════ دیتابیس SQLite (database) ══════════════════════

class DB:
    def __init__(self, path="vpn_bot.db"):
        self.path = path
        self.lock = threading.RLock()
        self._connect()
        self._init()

    def _connect(self):
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

    def _init(self):
        with self.lock:
            c = self.conn.cursor()
            c.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                balance INTEGER DEFAULT 0,
                referred_by INTEGER,
                state TEXT DEFAULT 'none',
                state_data TEXT DEFAULT '{}',
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                url TEXT,
                username TEXT,
                password TEXT,
                location TEXT DEFAULT '',
                max_users INTEGER DEFAULT 200,
                status TEXT DEFAULT 'active',
                type TEXT DEFAULT 'tifusi',
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS panel_inbounds (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                panel_id INTEGER,
                inbound_id INTEGER,
                protocol TEXT,
                port INTEGER,
                enabled INTEGER DEFAULT 1,
                remark TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                volume_gb INTEGER,
                days INTEGER,
                price INTEGER,
                active INTEGER DEFAULT 1,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                panel_id INTEGER,
                plan_id INTEGER,
                protocol TEXT,
                username TEXT,
                password TEXT,
                psk TEXT DEFAULT '',
                inbound_id INTEGER DEFAULT 0,
                extra_inbound_id INTEGER DEFAULT 0,
                third_inbound_id INTEGER DEFAULT 0,
                price INTEGER DEFAULT 0,
                volume_gb INTEGER DEFAULT 0,
                days INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_at INTEGER,
                expire_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                rtype TEXT,
                photo_id TEXT,
                meta TEXT DEFAULT '{}',
                status TEXT DEFAULT 'pending',
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message TEXT,
                photo_id TEXT,
                status TEXT DEFAULT 'open',
                reply TEXT,
                created_at INTEGER
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)
            self.conn.commit()
        # مهاجرت: ستون عنوان پلن
        try:
            self.x("ALTER TABLE plans ADD COLUMN title TEXT DEFAULT ''")
        except Exception:
            pass
        # مهاجرت: ستون تعداد کاربر (دستگاه همزمان) برای هر پلن — 0 یعنی بدون محدودیت
        try:
            self.x("ALTER TABLE plans ADD COLUMN user_limit INTEGER DEFAULT 0")
        except Exception:
            pass
        # مهاجرت: هر پلن مال یک سرویس است؛ پلن‌های قبل از این نسخه (سرویس خالی) برای همه‌ی سرویس‌ها
        # نشان داده می‌شوند تا فروش ربات بعد از آپدیت قطع نشود، تا وقتی ادمین سرویسشان را تعیین کند
        try:
            self.x("ALTER TABLE plans ADD COLUMN service TEXT DEFAULT ''")
        except Exception:
            pass
        # پلن پیش‌فرضی ساخته نمی‌شود — ادمین بعد از استارت خودش پلن‌ها را
        # از بخش مدیریت پلن‌ها تعریف می‌کند (عنوان → قیمت → مدت → تعداد کاربر).
        # مهاجرت: ستون بلاک کاربر
        try:
            self.x("ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0")
        except Exception:
            pass
        # مهاجرت: صفحه‌ی مدیریت کاربر — درصد تخفیف، سقف اکانت تست و آخرین استفاده از ربات
        for sql in ("ALTER TABLE users ADD COLUMN discount_pct INTEGER DEFAULT 0",
                    "ALTER TABLE users ADD COLUMN test_limit INTEGER DEFAULT 1",
                    "ALTER TABLE users ADD COLUMN last_seen INTEGER DEFAULT 0"):
            try:
                self.x(sql)
            except Exception:
                pass
        # مهاجرت: نوع پنل. فقط 'tifusi' استفاده می‌شود؛ پنل‌های دیتابیس‌های خیلی قدیمی که این ستون را
        # نداشتند 'legacy' می‌شوند و مثل هر نوع دیگری غیر از tifusi فقط به‌عنوان «قدیمی» نمایش داده می‌شوند.
        try:
            self.x("ALTER TABLE panels ADD COLUMN type TEXT DEFAULT 'legacy'")
        except Exception:
            pass
        # مهاجرت: نام گروه پنل در نگاشت سرویس ← گروه (جدول panel_inbounds)
        try:
            self.x("ALTER TABLE panel_inbounds ADD COLUMN remark TEXT DEFAULT ''")
        except Exception:
            pass
        # مهاجرت: لینک اشتراک سفارش
        try:
            self.x("ALTER TABLE orders ADD COLUMN sub_url TEXT DEFAULT ''")
        except Exception:
            pass
        # مهاجرت: شناسه‌ی اپ Tifusi VPN برای سفارش‌های Tifusi Panel
        try:
            self.x("ALTER TABLE orders ADD COLUMN app_code TEXT DEFAULT ''")
        except Exception:
            pass
        # مهاجرت ۴.۱: پروتکل‌های خوانده‌شده از پنل ({پروتکل: تعداد هاست})، زمان آخرین بررسی و هشدار SSL
        for sql in ("ALTER TABLE panels ADD COLUMN protocols TEXT DEFAULT '{}'",
                    "ALTER TABLE panels ADD COLUMN checked_at INTEGER DEFAULT 0",
                    "ALTER TABLE panels ADD COLUMN tls_insecure INTEGER DEFAULT 0",
                    # یادآوری‌های ارسال‌شده برای هر سفارش: 1 = سه روز مانده، 2 = یک روز مانده، 4 = منقضی شد
                    "ALTER TABLE orders ADD COLUMN reminded INTEGER DEFAULT 0"):
            try:
                self.x(sql)
            except Exception:
                pass
        self._archive_legacy()
        self._migrate_41()

    def _migrate_41(self):
        """یک بار هنگام ارتقا به ۴.۱:
        - در ۴.۰ «روی این پنل فروخته نشود» یعنی نبودن ردیف؛ در ۴.۱ نبودن ردیف یعنی «هنوز تصمیم گرفته نشده» و
          ممکن است خودکار فعال شود. پس برای پنل‌های موجود، سرویس‌های بدون ردیف صریحاً «فروخته نشود» ثبت می‌شوند.
        - سفارش‌هایی که قبل از ارتقا منقضی شده‌اند یادآوری انقضا نمی‌گیرند."""
        if self.one("SELECT value FROM settings WHERE key='migrated_41'"):
            return
        with self.lock:
            for (pid,) in self.conn.execute("SELECT id FROM panels").fetchall():
                have = {r[0] for r in self.conn.execute("SELECT protocol FROM panel_inbounds WHERE panel_id=?", (pid,))}
                for svc in SERVICES:
                    if svc not in have:
                        self.conn.execute("INSERT INTO panel_inbounds (panel_id,inbound_id,protocol,port,enabled,remark) "
                                          "VALUES (?,0,?,0,0,'')", (pid, svc))
            self.conn.execute("UPDATE orders SET reminded=7 WHERE expire_at > 0 AND expire_at < ?", (int(time.time()),))
            self.conn.execute("INSERT OR REPLACE INTO settings (key,value) VALUES ('migrated_41','1')")
            self.conn.commit()

    def _archive_legacy(self):
        """ربات فقط با Tifusi Panel کار می‌کند. پنل‌های نسخه‌های خیلی قدیمی (vpn-ui و ...) حذف می‌شوند و
        سفارش‌هایشان «archived» می‌شوند: در تاریخچه و آمار می‌مانند ولی در سرویس‌های کاربر نمی‌آیند."""
        legacy = [r["id"] for r in self.q("SELECT id FROM panels WHERE COALESCE(type,'') != 'tifusi'")]
        for pid in legacy:
            self.x("UPDATE orders SET status='archived' WHERE panel_id=? AND status IN ('active','delreq_pending')", (pid,))
            self.x("DELETE FROM panel_inbounds WHERE panel_id=?", (pid,))
            self.x("DELETE FROM panels WHERE id=?", (pid,))
        keys = tuple(SERVICES) + (GENERIC_ORDER_KEY,)
        marks = ",".join("?" * len(keys))
        self.x(f"UPDATE orders SET status='archived' WHERE protocol NOT IN ({marks}) AND status IN ('active','delreq_pending')", keys)
        if legacy:
            log.info("archived %d legacy panel(s) from an older bot version", len(legacy))

    def backup_to(self, dest):
        """کپی سازگار دیتابیس در حال اجرا (SQLite online backup) — حتی وسط نوشتن هم فایل خراب نمی‌دهد."""
        with self.lock:
            out = sqlite3.connect(dest)
            try:
                self.conn.backup(out)
            finally:
                out.close()

    def restore_from(self, src):
        """جایگزینی دیتابیس با فایل بکاپ؛ نسخه‌ی فعلی قبلش کنار فایل با پسوند .before-restore نگه داشته می‌شود."""
        with self.lock:
            self.backup_to(self.path + ".before-restore")
            self.conn.close()
            shutil.copyfile(src, self.path)
            self._connect()
            self._init()

    # ---------- ابزار داخلی ----------
    def q(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            return cur.fetchall()

    def one(self, sql, params=()):
        rows = self.q(sql, params)
        return rows[0] if rows else None

    def x(self, sql, params=()):
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    # ---------- کاربران ----------
    def get_user(self, uid):
        return self.one("SELECT * FROM users WHERE id=?", (uid,))

    def ensure_user(self, uid, username="", full_name=""):
        u = self.get_user(uid)
        if not u:
            self.x("INSERT INTO users (id,username,full_name,balance,state,state_data,created_at) VALUES (?,?,?,0,'none','{}',?)",
                   (uid, username or "", full_name or "", int(time.time())))
        else:
            self.x("UPDATE users SET username=?, full_name=?, last_seen=? WHERE id=?",
                   (username or "", full_name or "", int(time.time()), uid))
        return self.get_user(uid)

    def set_state(self, uid, state, data=None):
        self.x("UPDATE users SET state=?, state_data=? WHERE id=?",
               (state, json.dumps(data or {}, ensure_ascii=False), uid))

    def get_state(self, uid):
        u = self.get_user(uid)
        if not u:
            return "none", {}
        try:
            return u["state"] or "none", json.loads(u["state_data"] or "{}")
        except Exception:
            return "none", {}

    def add_balance(self, uid, amount):
        self.x("UPDATE users SET balance = balance + ? WHERE id=?", (int(amount), uid))

    def try_spend(self, uid, amount):
        """کسر اتمیک از کیف پول: فقط اگر موجودی کافی باشد کم می‌کند و True برمی‌گرداند.
        جلوی خرید دوباره با یک موجودی را می‌گیرد، حتی اگر کاربر دو بار پشت‌سرهم دکمه را بزند."""
        with self.lock:
            cur = self.conn.execute("UPDATE users SET balance = balance - ? WHERE id=? AND balance >= ?",
                                    (int(amount), uid, int(amount)))
            self.conn.commit()
            return cur.rowcount == 1

    def all_user_ids(self):
        return [r["id"] for r in self.q("SELECT id FROM users WHERE COALESCE(is_blocked,0)=0")]

    def get_balance(self, uid):
        u = self.get_user(uid)
        return u["balance"] if u else 0

    def referral_count(self, uid):
        return self.one("SELECT COUNT(*) c FROM users WHERE referred_by=?", (uid,))["c"]

    def find_user(self, query):
        try:
            uid = int(query)
            u = self.get_user(uid)
            if u:
                return u
        except ValueError:
            pass
        return self.one("SELECT * FROM users WHERE username=?", (query.lstrip("@"),))

    # ---------- تنظیمات ----------
    def setting(self, key, default=""):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return r["value"] if r else default

    def set_setting(self, key, value):
        self.x("INSERT INTO settings (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
               (key, str(value)))

    # ---------- پنل‌ها ----------
    def add_panel(self, d):
        return self.x("""INSERT INTO panels (name,url,username,password,location,max_users,status,type,created_at,
            protocols,checked_at,tls_insecure) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d.get("name", ""), d.get("url", ""), d.get("username", ""), d.get("password", ""),
             d.get("location", ""), int(d.get("max_users", 200)), d.get("status", "active"),
             "tifusi", int(time.time()), json.dumps(d.get("protocols") or {}), int(time.time()),
             1 if d.get("tls_insecure") else 0))

    def get_panels(self, active_only=False):
        if active_only:
            return self.q("SELECT * FROM panels WHERE status='active'")
        return self.q("SELECT * FROM panels ORDER BY id")

    def get_panel(self, pid):
        return self.one("SELECT * FROM panels WHERE id=?", (pid,))

    def update_panel(self, pid, **fields):
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE panels SET {sets} WHERE id=?", (*fields.values(), pid))

    def delete_panel(self, pid):
        self.x("DELETE FROM panel_inbounds WHERE panel_id=?", (pid,))
        self.x("DELETE FROM panels WHERE id=?", (pid,))

    def set_service_map(self, panel_id, mapping):
        """نگاشت سرویس ← گروه پنل در جدول panel_inbounds: protocol = کلید سرویس، inbound_id = شناسه‌ی گروه
        (۰ = سرورهای عمومی)، remark = نام گروه، enabled = 0 یعنی «روی این پنل فروخته نشود».
        mapping: {service: {"id": ..., "name": ...} یا None}. فقط کلیدهای داده‌شده عوض می‌شوند."""
        for key, g in mapping.items():
            if key not in SERVICES:
                continue
            self.x("DELETE FROM panel_inbounds WHERE panel_id=? AND protocol=?", (panel_id, key))
            self.x("INSERT INTO panel_inbounds (panel_id,inbound_id,protocol,port,enabled,remark) VALUES (?,?,?,0,?,?)",
                   (panel_id, int((g or {}).get("id") or 0), key, 1 if g else 0, (g or {}).get("name", "")))

    def get_service_map(self, panel_id):
        """{کلید سرویس: ردیف} برای سرویس‌هایی که روی این پنل فروخته می‌شوند."""
        rows = self.q("SELECT * FROM panel_inbounds WHERE panel_id=? AND enabled=1 ORDER BY id", (panel_id,))
        return {r["protocol"]: r for r in rows if r["protocol"] in SERVICES}

    def get_service_rows(self, panel_id):
        """همه‌ی تصمیم‌های ادمین برای این پنل، شامل «فروخته نشود»."""
        rows = self.q("SELECT * FROM panel_inbounds WHERE panel_id=? ORDER BY id", (panel_id,))
        return {r["protocol"]: r for r in rows if r["protocol"] in SERVICES}

    # ---------- پلن‌ها ----------
    def add_plan(self, volume_gb, days, price, title="", user_limit=0, service=""):
        return self.x("INSERT INTO plans (volume_gb,days,price,active,created_at,title,user_limit,service) VALUES (?,?,?,1,?,?,?,?)",
                      (int(volume_gb), int(days), int(price), int(time.time()), title, int(user_limit), service))

    def get_plans(self, active_only=False, service=None):
        """service: فقط پلن‌های همان سرویس (به‌علاوه‌ی پلن‌های قدیمی بدون سرویس)."""
        where, args = [], []
        if active_only:
            where.append("active=1")
        if service is not None:
            where.append("service IN (?, '')")
            args.append(service)
        sql = "SELECT * FROM plans" + (" WHERE " + " AND ".join(where) if where else "")
        # حجمی‌ها از کم به زیاد، نامحدودها (حجم 0) ته لیست
        return self.q(sql + " ORDER BY volume_gb = 0, volume_gb, user_limit, price", tuple(args))

    def get_plan(self, pid):
        return self.one("SELECT * FROM plans WHERE id=?", (pid,))

    def update_plan(self, pid, **fields):
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE plans SET {sets} WHERE id=?", (*fields.values(), pid))

    def delete_plan(self, pid):
        self.x("DELETE FROM plans WHERE id=?", (pid,))

    # ---------- سفارش‌ها ----------
    def create_order(self, d):
        # ستون‌های password/psk/extra_inbound_id/third_inbound_id فقط برای نمایش سفارش‌های قدیمی نگه داشته شده‌اند
        return self.x("""INSERT INTO orders (user_id,panel_id,plan_id,protocol,username,password,
            inbound_id,price,volume_gb,days,status,created_at,expire_at,sub_url,app_code)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (d["user_id"], d["panel_id"], d.get("plan_id", 0), d["protocol"], d["username"], d.get("password", ""),
             d.get("inbound_id", 0), d.get("price", 0), d.get("volume_gb", 0), d.get("days", 0), "active",
             int(time.time()), d.get("expire_at", 0), d.get("sub_url", ""), d.get("app_code", "")))

    def get_order(self, oid):
        return self.one("SELECT * FROM orders WHERE id=?", (oid,))

    def orders_to_remind(self):
        return self.q("SELECT * FROM orders WHERE status='active' AND expire_at > 0 AND expire_at < ?",
                      (int(time.time()) + 3 * 86400,))

    def get_user_orders(self, uid, active_only=True):
        sql = "SELECT * FROM orders WHERE user_id=?"
        if active_only:
            sql += " AND status IN ('active','delreq_pending')"
        return self.q(sql + " ORDER BY id DESC", (uid,))

    def pending_delete_requests(self):
        return self.q("SELECT * FROM orders WHERE status='delreq_pending' ORDER BY id")

    def update_order(self, oid, **fields):
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE orders SET {sets} WHERE id=?", (*fields.values(), oid))

    def claim_order(self, oid, from_status, to_status):
        """تغییر وضعیت فقط اگر هنوز from_status باشد؛ True یعنی همین فراخوانی آن را گرفت (دو ادمین همزمان = یک برنده)."""
        with self.lock:
            cur = self.conn.execute("UPDATE orders SET status=? WHERE id=? AND status=?", (to_status, oid, from_status))
            self.conn.commit()
            return cur.rowcount == 1

    def count_panel_active_orders(self, panel_id):
        # سفارش منقضی‌شده جایی در پنل اشغال نمی‌کند؛ اگر شمرده می‌شد پنل‌ها با گذشت زمان «پر» می‌شدند
        return self.one("SELECT COUNT(*) c FROM orders WHERE panel_id=? AND status='active' AND expire_at > ?",
                        (panel_id, int(time.time())))["c"]

    # ---------- رسیدها ----------
    def create_receipt(self, uid, amount, rtype, photo_id, meta=None):
        return self.x("INSERT INTO receipts (user_id,amount,rtype,photo_id,meta,status,created_at) VALUES (?,?,?,?,?,'pending',?)",
                      (uid, int(amount), rtype, photo_id, json.dumps(meta or {}, ensure_ascii=False), int(time.time())))

    def get_receipt(self, rid):
        return self.one("SELECT * FROM receipts WHERE id=?", (rid,))

    def set_receipt_status(self, rid, status):
        self.x("UPDATE receipts SET status=? WHERE id=?", (status, rid))

    def pending_receipts(self):
        return self.q("SELECT * FROM receipts WHERE status='pending' ORDER BY id DESC")

    # ---------- تیکت‌ها ----------
    def create_ticket(self, uid, message, photo_id=""):
        return self.x("INSERT INTO tickets (user_id,message,photo_id,status,created_at) VALUES (?,?,?,'open',?)",
                      (uid, message, photo_id, int(time.time())))

    def get_ticket(self, tid):
        return self.one("SELECT * FROM tickets WHERE id=?", (tid,))

    def set_ticket(self, tid, status, reply=None):
        if reply is not None:
            self.x("UPDATE tickets SET status=?, reply=? WHERE id=?", (status, reply, tid))
        else:
            self.x("UPDATE tickets SET status=? WHERE id=?", (status, tid))

    def open_tickets(self):
        return self.q("SELECT * FROM tickets WHERE status='open' ORDER BY id DESC")

    # ---------- آمار ----------
    def stats_since(self, ts):
        return {
            "new_users": self.one("SELECT COUNT(*) c FROM users WHERE created_at>=?", (ts,))["c"],
            "new_orders": self.one("SELECT COUNT(*) c FROM orders WHERE created_at>=?", (ts,))["c"],
            "revenue": self.one("SELECT COALESCE(SUM(price),0) s FROM orders WHERE created_at>=?", (ts,))["s"],
        }

    def totals(self):
        return {
            "users": self.one("SELECT COUNT(*) c FROM users")["c"],
            "orders": self.one("SELECT COUNT(*) c FROM orders")["c"],
            "active": self.one("SELECT COUNT(*) c FROM orders WHERE status='active'")["c"],
            "revenue": self.one("SELECT COALESCE(SUM(price),0) s FROM orders")["s"],
            "tickets_open": self.one("SELECT COUNT(*) c FROM tickets WHERE status='open'")["c"],
            "pending_receipts": self.one("SELECT COUNT(*) c FROM receipts WHERE status='pending'")["c"],
        }


# ══════════════════════ بدنه اصلی ربات ══════════════════════

db = DB()

def service_name(key):
    if key in SERVICES:
        return SERVICES[key]
    if key == GENERIC_ORDER_KEY:
        return "📱 سرویس Tifusi"
    return f"🗄 سرویس بایگانی‌شده ({key})"


def order_name(o):
    return service_name(o["protocol"])


def panel_protocols(panel):
    """{پروتکل: تعداد هاست} آخرین باری که پنل بررسی شد."""
    try:
        data = json.loads(panel["protocols"] or "{}")
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError, KeyError, IndexError):
        return {}


# پروتکل‌هایی که پنل امروز در فیلد protocols کاربر قبول می‌کند؛ پروتکل تازه‌ی پنل (مثلاً wireguard)
# به‌محض اینکه روی پنل هاست بگیرد هم پذیرفته می‌شود.
PANEL_KNOWN_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2", "ikev2", "l2tp", "pptp"}


def service_protocols_on(panel, service):
    """پروتکل‌های این سرویس که روی این پنل هاست دارند (به ترتیب SERVICE_PROTOCOLS) — برای تصمیم فروش."""
    available = panel_protocols(panel)
    return [p for p in SERVICE_PROTOCOLS.get(service, []) if available.get(p)]


def service_access_protocols(panel, service):
    """پروتکل‌هایی که کاربرِ این سرویس به آن‌ها دسترسی می‌گیرد: کل خانواده‌ی سرویس (نه فقط آن‌هایی که الان هاست دارند)
    تا اگر بعداً مثلاً Trojan به Xray اضافه شد، مشتریان فعلی Xray هم بدون تمدید به آن دسترسی داشته باشند."""
    available = panel_protocols(panel)
    return [p for p in SERVICE_PROTOCOLS.get(service, []) if p in PANEL_KNOWN_PROTOCOLS or available.get(p)]


def md(s):
    """فرار از کاراکترهای Markdown قدیمی تلگرام برای متن آزاد (نام پنل، عنوان پلن و ...)."""
    return re.sub(r"([_*`\[])", r"\\\1", str(s or ""))


# ---------- ابزارها ----------
def now():
    return int(time.time())


def fmt(n):
    return f"{int(n):,}"



def get_admins():
    """لیست ادمین‌های اضافه‌شده (علاوه بر ادمین اصلی) — همه دسترسی کامل دارند."""
    try:
        return [int(x) for x in json.loads(db.setting("admins", "[]") or "[]")]
    except Exception:
        return []


def is_admin(uid):
    return uid == ADMIN_ID or uid in get_admins()


def jdate(ts, with_time=True):
    """تاریخ شمسی به وقت ایران (۱۴۰۵/۰۷/۱۰ ۲۰:۴۷:۳۶)."""
    if not ts:
        return "—"
    t = datetime.datetime.utcfromtimestamp(int(ts) + 12600)
    gy, gm, gd = t.year, t.month, t.day
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    out = f"{jy}/{jm:02d}/{jd:02d}"
    return out + t.strftime(" %H:%M:%S") if with_time else out


def user_discount(uid):
    u = db.get_user(uid)
    try:
        return max(0, min(100, int(u["discount_pct"] or 0))) if u else 0
    except (IndexError, KeyError):
        return 0


def user_plan(pid, uid):
    """پلن با قیمتِ همین کاربر (درصد تخفیفی که ادمین برایش گذاشته). همه‌ی مسیرهای خرید و تمدید
    مشتری از این می‌خوانند تا پیش‌فاکتور، کیف پول و رسید کارت به کارت یک عدد ببینند."""
    p = db.get_plan(pid) if pid else None
    if not p:
        return None
    p = dict(p)
    off = user_discount(uid)
    if off:
        p["price"] = int(p["price"] * (100 - off) / 100)
    return p


def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


def copy_text_button(label, value):
    """دکمه‌ای که با یک لمس متن را کپی می‌کند (Bot API 8.0). روی نسخه‌های قدیمی‌تر
    python-telegram-bot وجود ندارد، آن‌وقت None برمی‌گردد."""
    try:
        from telegram import CopyTextButton
        return InlineKeyboardButton(label, copy_text=CopyTextButton(value))
    except Exception:
        return None


def pbtn(text, data):
    """دکمه پهن — با فاصله نامرئی دو طرف متن تا ستون‌ها کل عرض صفحه را پر کنند."""
    return InlineKeyboardButton(f"⠀{text}⠀", callback_data=data)



def remaining_text(expire_at):
    left = expire_at - now()
    if left <= 0:
        return "منقضی شده"
    d, h = left // 86400, (left % 86400) // 3600
    return f"{d} روز و {h} ساعت"


def gb(b):
    return round(b / 1024 ** 3, 2)


def parse_volume_from_title(title):
    """استخراج حجم از عنوان پلن — عدد داخل عنوان (حتی فارسی) = گیگ، «نامحدود» یا بدون عدد = نامحدود."""
    if "نامحدود" in (title or ""):
        return 0
    t = (title or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
    m = re.search(r"\d+", t)
    return int(m.group()) if m else 0


def vol_text(v):
    """حجم 0 یعنی نامحدود."""
    return "نامحدود ♾" if not v else f"{v} گیگ"


def plan_label(p):
    """لیبل پلن — اگر عنوان دارد همان، وگرنه ساخته می‌شود."""
    try:
        t = p["title"] or ""
    except Exception:
        t = ""
    if t:
        return t
    return f"{vol_text(p['volume_gb'])} | {p['days']} روز | {fmt(p['price'])} تومان"


def plan_service(p):
    try:
        return p["service"] or ""
    except (IndexError, KeyError):
        return ""


def plan_fits(p, service):
    """پلن برای این سرویس فروخته می‌شود؟ پلن قدیمی بدون سرویس برای همه."""
    return plan_service(p) in ("", service)


def plan_service_name(p):
    return SERVICES.get(plan_service(p), "همه‌ی سرویس‌ها (پلن قدیمی)")


def plan_line(p):
    """خط تعرفه: 🛍️ عنوان — قیمت (اعداد انگلیسی). اگر عنوان ندارد، لیبل کامل ساخته می‌شود."""
    try:
        t = p["title"] or ""
    except Exception:
        t = ""
    if t:
        return f"🛍️ {t} | {fmt(p['price'])} تومان"
    return f"🛍️ {plan_label(p)}"


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    msg = query.message
    if msg and msg.photo and (msg.caption or "").startswith("🛍"):
        # «My services» picture: Telegram cannot turn a photo into text, so send the text and drop the photo.
        try:
            await msg.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            await msg.delete()
            return
        except Exception:
            pass
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


# ---------- ظاهر صفحه‌های مدیریت ----------
# همه‌ی صفحه‌های پنل مدیریت با HTML ساخته می‌شوند: عنوان پررنگ، هر دسته اطلاعات داخل یک کادر (blockquote)
NOT_SET = "<i>تنظیم نشده</i>"


def h(v):
    return html.escape(str(v))


def val(v):
    """مقدار کاربر/دیتابیس برای نمایش؛ خالی = «تنظیم نشده»."""
    return f"<b>{h(v)}</b>" if v not in (None, "", "—", "-") else NOT_SET


def card(title, *blocks, note=None):
    """title: متن ثابت خود ربات (escape نمی‌شود). blocks: لیست خط‌ها، هر لیست یک کادر."""
    parts = [f"<b>{title}</b>"]
    for b in blocks:
        b = [x for x in (b or []) if x]
        if b:
            parts.append("<blockquote>" + "\n".join(b) + "</blockquote>")
    if note:
        parts.append(f"<i>{note}</i>")
    return "\n\n".join(parts)


def bar(n, total, width=10):
    """نوار پر شدن ظرفیت: ▰▰▰▱▱▱▱▱▱▱ ۳۰٪"""
    total = max(int(total or 0), 1)
    frac = min(max(n / total, 0), 1)
    full = round(frac * width)
    return "▰" * full + "▱" * (width - full) + f" {round(frac * 100)}٪"


def back_row(data="admin:menu", label="🔙 بازگشت"):
    return [btn(label, data)]


async def page(query, text, rows):
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="HTML")


async def notify_admin(bot, text, reply_markup=None):
    for aid in {ADMIN_ID, *get_admins()}:
        try:
            await bot.send_message(aid, text, reply_markup=reply_markup)
        except Exception as e:
            log.warning("notify_admin failed for %s: %s", aid, e)


async def notify_admins_photo(bot, photo_id, caption, reply_markup=None):
    """ارسال عکس رسید به همه ادمین‌ها تا هرکدام بتوانند تایید/رد کنند."""
    for aid in {ADMIN_ID, *get_admins()}:
        try:
            await bot.send_photo(aid, photo_id, caption=caption, reply_markup=reply_markup)
        except Exception as e:
            log.warning("notify_admins_photo failed for %s: %s", aid, e)


# ---------- گزارش لحظه‌ای در گروه گزارش (تنظیمات ← 👥 آیدی گروه) ----------
_group_tasks = set()


def _chat_target(value):
    """@name, or the numeric -100… id as an int; None when not set."""
    v = (value or "").strip()
    if not v:
        return None
    return int(v) if v.lstrip("-").isdigit() else v


def who(uid):
    """«name @username (id)» for a report line."""
    u = db.get_user(uid)
    if not u:
        return str(uid)
    tag = f"@{u['username']}" if u["username"] else ""
    return " ".join(x for x in ((u["full_name"] or "").strip(), tag, f"({uid})") if x)


def group_thread(topic):
    """Thread id of a report topic in the group (settings topic_<name>); None without topics."""
    v = (db.setting(f"topic_{topic}") or "").strip() if topic else ""
    return int(v) if v.isdigit() else None


async def _send_group(bot, text, topic=None):
    target = _chat_target(db.setting("group_id"))
    if target is None:
        return
    text = f"{text}\n🕓 {jdate(now())}"
    thread = group_thread(topic)
    try:
        await bot.send_message(target, text, message_thread_id=thread)
    except Exception as e:
        if thread and "thread" in str(e).lower():
            # The topic was deleted in the group: still report, in General.
            try:
                await bot.send_message(target, text)
                return
            except Exception as e2:
                e = e2
        log.warning("group report failed: %s", e)


def notify_group(bot, text, topic=None):
    """گزارش لحظه‌ای به گروه گزارش، بدون منتظر ماندن: گروهِ کند یا خراب هیچ‌وقت خرید را معطل نمی‌کند.
    رمز سرویس مشتری، شماره کارت و توکن هرگز در این متن‌ها نمی‌آیند."""
    if _chat_target(db.setting("group_id")) is None:
        return
    task = asyncio.create_task(_send_group(bot, text, topic))
    _group_tasks.add(task)
    task.add_done_callback(_group_tasks.discard)


async def send_receipt_to_admins(bot, rid, photo_id, caption):
    """ارسال رسید به همه ادمین‌ها + ذخیره آیدی پیام‌ها تا بعداً برای بقیه بسته شود."""
    msgs = []
    for aid in {ADMIN_ID, *get_admins()}:
        try:
            m = await bot.send_photo(aid, photo_id, caption=caption,
                                     reply_markup=receipt_admin_kb(rid))
            msgs.append([aid, m.message_id])
        except Exception as e:
            log.warning("send_receipt_to_admins failed for %s: %s", aid, e)
    try:
        r = db.get_receipt(rid)
        kinds = {"wallet_charge": "شارژ کیف پول", "purchase": "خرید", "renew": "تمدید"}
        notify_group(bot, f"🧾 رسید جدید منتظر تأیید — R{rid}\n👤 {who(r['user_id'])}\n"
                          f"📌 {kinds.get(r['rtype'], r['rtype'])} | 💸 {fmt(r['amount'])} تومان", topic="pay")
        meta = json.loads(r["meta"] or "{}")
        meta["admin_msgs"] = msgs
        db.x("UPDATE receipts SET meta=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), rid))
    except Exception as e:
        log.warning("save admin_msgs failed: %s", e)


async def close_receipt_for_others(bot, rid, except_chat_id, note):
    """وقتی یک ادمین رسید را بررسی کرد، پیام بقیه ادمین‌ها بسته (بدون دکمه) می‌شود."""
    try:
        r = db.get_receipt(rid)
        if not r:
            return
        meta = json.loads(r["meta"] or "{}")
        caption = receipt_caption(r, note)
        for aid, mid in meta.get("admin_msgs", []):
            if aid == except_chat_id:
                continue
            try:
                await bot.edit_message_caption(chat_id=aid, message_id=mid, caption=caption)
            except Exception:
                pass
    except Exception as e:
        log.warning("close_receipt_for_others failed: %s", e)


# ---------- کیبوردها ----------
def main_menu_kb(uid, force=False):
    """منوی پایین قدیمی. کاربرهای مینی‌اپ (is_miniapp_user) آن را نمی‌بینند، مگر ادمین با /admin (force)."""
    if not force and is_miniapp_user(uid):
        return ReplyKeyboardRemove()
    rows = [
        ["🔐 خرید اشتراک", "♻️ تمدید سرویس"],
        ["🔑 اکانت تست"],
        ["🏦 کیف پول + شارژ", "🛍 سرویس‌های من"],
        ["💵 تعرفه اشتراک ها", "👥 زیرمجموعه گیری"],
        ["📚 آموزش", "☎️ پشتیبانی"],
    ]
    if is_admin(uid):
        rows.append(["🧑‍💼 پنل مدیریت"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


FAQ_DEFAULT = """💡 سوالات متداول ⁉️

1️⃣ فیلترشکن شما از چه نوعیه؟
✅ سرویس‌های ما روی Tifusi Panel هستند: IKEv2 و L2TP (بدون نصب اپ، با خود تنظیمات گوشی) و Xray (VLESS/VMess/Trojan با v2rayNG یا Streisand). روی آیفون پروفایل با یک لمس نصب می‌شود.

2️⃣ اگر قبل از منقضی شدن اکانت تمدید کنم، روزهای باقی‌مانده می‌سوزد؟
✅ خیر، روزهای باقی‌مانده محاسبه و به تمدید اضافه می‌شود.

3️⃣ اگر حجم سرویس تمام شود چه اتفاقی می‌افتد؟
✅ سرویس متوقف می‌شود؛ کافی است از منوی «♻️ تمدید سرویس» آن را تمدید کنید.

4️⃣ فیلترشکن وصل نمی‌شود، چکار کنم؟
✅ اول از منوی «📚 آموزش» آموزش اتصال را ببینید، اگر حل نشد به «☎️ پشتیبانی» پیام دهید.

5️⃣ امکان بازگشت وجه دارید؟
✅ بله، با «🗑 درخواست حذف» مبلغ روزهای باقی‌مانده به کیف پول شما برمی‌گردد.

💡 اگر جواب سوالتان را پیدا نکردید، به «☎️ پشتیبانی» مراجعه کنید."""


def back_kb():
    return InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:back")]])


# پنل مدیریت: کیبورد پایین صفحه (تمام‌عرض، مثل منوی اصلی) — متن دکمه ← کار ادمین
ADMIN_MENU_ROWS = [
    [("📊 آمار ربات", "stats")],
    [("🚀 پنل نمایندگی", "soon"), ("🎫 لیست تیکت ها", "tickets")],
    [("✏️ مدیریت پنل", "panels"), ("🖥 اضافه کردن پنل", "addpanel")],
    [("💸 قیمت سرویس دلخواه", "g:price")],
    [("👤 مدیریت کاربر", "g:users"), ("🏬 تنظیمات فروشگاه", "g:shop")],
    [("💎 مالی", "report")],
    [("🆕 آپدیت ربات", "g:update"), ("🛠 قابلیت های پنل", "panels_cap")],
    [("⚙️ تنظیمات عمومی", "settings"), ("💵 رسید های تایید نشده", "receipts")],
    [("⚙️ تنظیمات مینی اپ", "soon"), ("📚 بخش آموزش", "soon")],
]
ADMIN_MENU_ACTIONS = {label: what for row in ADMIN_MENU_ROWS for label, what in row}
ADMIN_HOME = "🏠 بازگشت به منوی اصلی"


def admin_menu_kb():
    rows = [[label for label, _ in row] for row in ADMIN_MENU_ROWS] + [[ADMIN_HOME]]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# زیرمنوهای پنل مدیریت: کلید ← (عنوان، دکمه‌های داخلش)
ADMIN_GROUPS = {
    "price": ("💸 قیمت سرویس دلخواه", [("💸 قیمت سرویس", "admin:plans_view"), ("📦 مدیریت پلن‌ها", "admin:plans")]),
    "users": ("👤 مدیریت کاربر", [("👥 لیست کاربران", "au:list:0"), ("🔍 جستجوی کاربر", "admin:users"),
                                 ("👑 مدیریت ادمین‌ها", "admin:admins"), ("🗑 درخواست‌های حذف", "admin:delreqs")]),
    "shop": ("🏬 تنظیمات فروشگاه", [("📣 پیام همگانی", "admin:broadcast"), ("📢 کانال/گروه گزارش", "admin:channel")]),
    "update": ("🆕 آپدیت ربات", [("🆕 نسخه و آپدیت", "admin:update"), ("💾 بکاپ", "admin:backup")]),
}


# منوی «مدیریت کاربر» چیدمان خودش را دارد (سه لیست تمام‌عرض، بقیه دوتایی، اولی سمت راست)
USERS_MENU = [
    [("💰 لیست کاربرانی که موجودی دارند", "au:list:0:bal")],
    [("👥 لیست کاربرانی که زیرمجموعه دارند", "au:list:0:ref")],
    [("➖ لیست کاربرانی که موجودی منفی دارند", "au:list:0:neg")],
    [("📋 لیست کل کاربران", "au:list:0"), ("👑 مدیریت ادمین‌ها", "admin:admins")],
    [("👥 شارژ همگانی", "au:chargeall:0"), ("🛍 جستجو سفارش", "au:findorder:0")],
    [("📩 بخش ارسال پیام", "admin:broadcast"), ("🔍 جستجو کاربر", "admin:users")],
    [("🗑 درخواست‌های حذف", "admin:delreqs")],
]


def admin_group_kb(key):
    if key == "users":
        return InlineKeyboardMarkup([[btn(label, data) for label, data in row] for row in USERS_MENU]
                                    + [[btn("🔙 بازگشت", "admin:menu")]])
    items = [btn(label, data) for label, data in ADMIN_GROUPS[key][1]]
    rows = [items[i:i + 2][::-1] for i in range(0, len(items), 2)]  # دو ستونه، اولی سمت راست
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    return InlineKeyboardMarkup(rows)


# ---------- شروع ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    ref = None
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref = int(context.args[0][4:])
        except ValueError:
            ref = None
    existed = db.get_user(u.id)
    if ref and (ref == u.id or not db.get_user(ref)):
        ref = None
    db.ensure_user(u.id, u.username, u.full_name)
    if not existed and ref:
        db.x("UPDATE users SET referred_by=? WHERE id=?", (ref, u.id))
    if not existed:
        await notify_admin(context.bot,
            f"👤 کاربر جدید ربات را استارت کرد:\n\n"
            f"نام: {u.full_name}\n"
            f"یوزرنیم: @{u.username or '—'}\n"
            f"آیدی: `{u.id}`", )
        notify_group(context.bot, f"👤 عضو جدید ربات: {who(u.id)}", topic="users")
    db.set_state(u.id, "none")
    if is_miniapp_user(u.id):
        await send_miniapp_only(update.message)
        return
    await update.message.reply_text(
        f"سلام {u.first_name} عزیز به ربات خوش آمدی 🌹👋\n\nاز منوی زیر استفاده کنید:",
        reply_markup=main_menu_kb(u.id))


MINIAPP_URL = "https://app.bomalo.ir/"


def is_miniapp_user(uid):
    """فقط مینی‌اپ: یا برای همه روشن است (تنظیم miniapp_all = 1) یا این کاربر در لیست تست است."""
    return db.setting("miniapp_all", "0") == "1" or uid in miniapp_only_ids()


def miniapp_only_ids():
    """کاربرهایی که به‌جای منوی قدیمی ربات فقط مینی‌اپ را می‌بینند (دوره‌ی تست: حساب‌های جواد).
    تنظیم «miniapp_only» در دیتابیس؛ وقتی برای همه روشن شد این لیست کنار می‌رود."""
    try:
        return {int(x) for x in json.loads(db.setting("miniapp_only", "[]") or "[]")}
    except Exception:
        return set()


MINIAPP_WELCOME = os.path.join(ASSET_DIR, "welcome-miniapp.jpg")


async def send_miniapp_only(message):
    # منوی پایین قدیمی برداشته می‌شود (پیام کمکی همان لحظه پاک می‌شود) و فقط عکسی می‌ماند
    # که با فلش به دکمه‌ی «Tifusi» کنار کادر پیام اشاره می‌کند.
    try:
        tmp = await message.reply_text("⏳", reply_markup=ReplyKeyboardRemove())
        await tmp.delete()
    except Exception as e:
        log.info("miniapp keyboard remove: %s", e)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Open", web_app=WebAppInfo(url=MINIAPP_URL), style="primary")]])
    cached = db.setting("miniapp_welcome_file_id", "")
    try:
        if cached:
            await message.reply_photo(cached, reply_markup=kb)
            return
        with open(MINIAPP_WELCOME, "rb") as f:
            sent = await message.reply_photo(f, reply_markup=kb)
        db.set_setting("miniapp_welcome_file_id", sent.photo[-1].file_id)
    except Exception as e:
        log.warning("miniapp welcome photo failed: %s", e)
        await message.reply_text("👇", reply_markup=kb)


async def admin_menu_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin: منوی کامل قدیمی برای ادمین، حتی وقتی برایش فقط مینی‌اپ روشن است."""
    u = update.effective_user
    if not is_admin(u.id):
        return
    db.set_state(u.id, "none")
    await update.message.reply_text("👑 منوی ربات:", reply_markup=main_menu_kb(u.id, force=True))


# ---------- فلوی کاربر: منوها ----------
async def show_buy_services(query, uid):
    """قدم اول خرید: فقط سرویس‌هایی که همین الان روی پنل‌ها هاست و ظرفیت خالی دارند."""
    db.set_state(uid, "none")
    # سرویسی که هنوز پلنی ندارد نشان داده نمی‌شود تا مشتری به صفحه‌ی خالی نرسد
    services = [s for s in available_services() if db.get_plans(active_only=True, service=s)]
    # L2TP و PPTP جدا فروخته نمی‌شوند: داخل همان پلن IKEv2 هستند. سفارش‌های قبلی‌شان تمدید می‌شوند.
    if "ikev2" in services:
        services = [s for s in services if s not in ("l2tp", "pptp")]
    if not services:
        await safe_edit(query, "❌ فعلاً سرویسی برای فروش در دسترس نیست. کمی بعد دوباره امتحان کنید.", reply_markup=back_kb())
        return
    rows = [[btn(SERVICES[svc], f"proto:{svc}")] for svc in services]
    rows.append([btn("🔙 بازگشت", "menu:back")])
    await safe_edit(query, "🔐 خرید اشتراک\n\n🧩 سرویس (پروتکل) مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))


async def show_plans(query, uid, service):
    """قدم دوم خرید: پلن‌های همان سرویس انتخاب‌شده، هر کدام با قیمت خودش."""
    plans = db.get_plans(active_only=True, service=service)
    if not plans:
        await safe_edit(query, f"❌ فعلاً پلنی برای {SERVICES[service]} تعریف نشده است.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:buy")]]))
        return
    db.set_state(uid, "buy_plan", {"protocol": service})
    rows = [[btn(plan_line(p), f"plan:{p['id']}")] for p in plans]
    rows.append([btn("🔙 بازگشت", "menu:buy")])
    await safe_edit(query, f"🔐 خرید اشتراک — {SERVICES[service]}\n\nلطفاً پلن مورد نظر را انتخاب کنید:",
                    reply_markup=InlineKeyboardMarkup(rows))


async def show_wallet(query, uid):
    bal = db.get_balance(uid)
    kb = InlineKeyboardMarkup([
        [btn("💰 افزایش موجودی (کارت به کارت)", "wallet:charge")],
        [btn("👤 حساب کاربری", "acc:show"), btn("🏠 بازگشت به منوی اصلی", "menu:back")],
    ])
    await safe_edit(query, f"🏦 کیف پول شما\n💰 موجودی: {fmt(bal)} تومان", reply_markup=kb)


async def show_tutorial_menu(query):
    rows = [[btn(t["title"], f"tut:{key}")] for key, t in TRAININGS.items()]
    rows.append([btn("🔙 بازگشت", "menu:back")])
    await safe_edit(query, "📚 آموزش اتصال\n\nکدام آموزش را می‌خواهید ببینید؟", reply_markup=InlineKeyboardMarkup(rows))


async def show_referral(query, context, uid):
    botuser = (await context.bot.get_me()).username
    count = db.referral_count(uid)
    link = f"https://t.me/{botuser}?start=ref_{uid}"
    await safe_edit(query,
        f"👥 زیرمجموعه‌گیری\n\n🔗 لینک دعوت شما:\n{link}\n\n"
        f"👤 تعداد زیرمجموعه‌های شما: {count} نفر",
        reply_markup=back_kb())


async def show_tariff(query):
    text = "💵 تعرفه‌ها (الگوی قیمت)\n"
    for service in available_services():
        plans = db.get_plans(active_only=True, service=service)
        if plans:
            text += f"\n{SERVICES[service]}\n" + "".join(plan_line(p) + "\n" for p in plans)
    await safe_edit(query, text, reply_markup=back_kb())


# ---------- ساخت سرویس ----------
def pick_panel(service, prefer_panel_id=None):
    """Load Balancing: خلوت‌ترین پنل فعال با ظرفیت خالی که این سرویس را می‌فروشد و پروتکلش روی آن هاست دارد.
    اگر prefer_panel_id هنوز شرایط را دارد همان برمی‌گردد (یوزرنیم مشتری روی همان پنل چک شده بود)."""
    candidates = []
    for p in db.get_panels(active_only=True):
        if service not in db.get_service_map(p["id"]) or not service_protocols_on(p, service):
            continue
        cnt = db.count_panel_active_orders(p["id"])
        if cnt >= p["max_users"]:
            continue
        if prefer_panel_id and p["id"] == prefer_panel_id:
            return p
        candidates.append((cnt, p))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1]


def available_services():
    """سرویس‌هایی (به ترتیب SERVICES) که حداقل یک پنل فعال با ظرفیت خالی برایشان هاست دارد."""
    return [s for s in SERVICES if pick_panel(s)]


_clients = {}
_clients_lock = threading.Lock()


def panel_client(panel):
    """یک کلاینت برای هر پنل تا توکن ورود دوباره استفاده شود؛ با عوض شدن آدرس/یوزر/پسورد نمونه‌ی تازه ساخته می‌شود."""
    key = (panel["url"], panel["username"], panel["password"])
    with _clients_lock:
        cached = _clients.get(panel["id"])
        if cached and cached[0] == key:
            return cached[1]
        client = TifusiPanelAPI(panel["url"], panel["username"], panel["password"])
        _clients[panel["id"]] = (key, client)
        return client


def refresh_panel(panel):
    """ورود به پنل و خواندن دوباره‌ی پروتکل‌ها (در thread اجرا شود). خروجی: (قبلی، فعلی) به شکل {پروتکل: تعداد}.
    سرویس تازه‌ای که ادمین هنوز برایش تصمیمی نگرفته روی «سرورهای عمومی» فروخته می‌شود تا بدون کار اضافه
    در ربات ظاهر شود؛ اگر ادمین «فروخته نشود» زده باشد همان می‌ماند."""
    client = panel_client(panel)
    client.login()
    before = panel_protocols(panel)
    after = client.list_protocols()
    db.update_panel(panel["id"], protocols=json.dumps(after), checked_at=now(), tls_insecure=1 if client.insecure else 0)
    decided = db.get_service_rows(panel["id"])
    fresh = [svc for svc in SERVICES if svc not in decided and any(after.get(p) for p in SERVICE_PROTOCOLS[svc])]
    if fresh:
        # بدون گروه، همه‌ی هاست‌ها عمومی‌اند و فروش روی «سرورهای عمومی» درست است. اگر پنل گروه دارد ممکن است
        # هاست‌های این پروتکل داخل گروهی باشند که کاربر بدون گروه به آن دسترسی ندارد؛ پس ادمین باید گروه را انتخاب کند.
        if len(client.list_groups()) <= 1:
            db.set_service_map(panel["id"], {svc: {"id": 0, "name": "سرورهای عمومی"} for svc in fresh})
    return before, after


def protocols_diff_text(before, after):
    added = [p for p in after if p not in before]
    removed = [p for p in before if p not in after]
    lines = []
    if added:
        lines.append("➕ اضافه شد: " + "، ".join(added))
    if removed:
        lines.append("➖ حذف شد: " + "، ".join(removed))
    return "\n".join(lines)


def plan_device_limit(plan):
    """سقف دستگاه پلن؛ None یعنی «نامعلوم» (مثلاً پلن حذف شده) تا تمدید سقف فعلی روی پنل را دست نزند."""
    try:
        value = plan["user_limit"]
    except (IndexError, KeyError, TypeError):
        return None
    return None if value is None else int(value or 0)


def random_ipsec_password():
    """رمز ۶ رقمی تا مشتری راحت دستی در تنظیمات VPN گوشی تایپش کند."""
    return f"{secrets.randbelow(10**6):06d}"


def create_service_on_panel(user_id, plan, service, username, panel_id=None, ipsec_password=None):
    """ساخت کاربر روی Tifusi Panel فقط با پروتکل‌های همین سرویس، گروه انتخاب‌شده و سقف دستگاه پلن.
    برای IKEv2/L2TP رمز انتخابی مشتری فرستاده می‌شود؛ اگر نداشت (اکانت تست، یا رسیدی که قبل از این نسخه
    ثبت شده) یک رمز تصادفی ساخته می‌شود."""
    if service not in SERVICES:
        raise PanelError("این سرویس دیگر فروخته نمی‌شود؛ لطفاً یک سرویس جدید بخرید")
    panel = pick_panel(service, panel_id)
    if not panel:
        raise PanelError(f"ظرفیت پنل‌های سرویس «{SERVICES[service]}» تکمیل است یا پنلی فعال نیست")
    if service in IPSEC_SERVICES and not ipsec_password:
        ipsec_password = random_ipsec_password()
    gid = int(db.get_service_map(panel["id"])[service]["inbound_id"] or 0)
    expire_at = now() + plan["days"] * 86400
    client = panel_client(panel)
    # گروه ۰ همان «سرورهای عمومی» است و به پنل فرستاده نمی‌شود (group_ids خالی)
    res = client.add_user([gid] if gid else [], username, plan["volume_gb"], expire_at,
                          protocols=service_access_protocols(panel, service), device_limit=plan_device_limit(plan),
                          ipsec_password=ipsec_password)
    oid = db.create_order({
        "user_id": user_id, "panel_id": panel["id"], "plan_id": plan["id"],
        "protocol": service, "username": username, "password": ipsec_password or "", "inbound_id": gid,
        "price": plan["price"], "volume_gb": plan["volume_gb"], "days": plan["days"],
        "expire_at": expire_at, "sub_url": res["subscription_url"], "app_code": res["app_code"],
    })
    return db.get_order(oid), panel


# ---------- کارت تحویل سرویس گوشی: پس‌زمینه‌ی رنگی و مشخصات سرویس به‌جای بارکد ----------
PC_ROW = {"name": "#4da3ff", "service": "#a78bfa", "volume": "#f97316", "expire": "#f472b6"}
PC_PROTO = (("IKEv2", "#3ddc84"), ("L2TP", "#f5c518"), ("PPTP", "#ff5a5f"))
PC_PANEL, PC_EDGE, PC_HAIR = "#121726", "#262d44", "#1f2538"


def phone_card_ground(img):
    """Deep navy fading to black, with soft orange and teal glows behind the mark."""
    from PIL import Image, ImageDraw, ImageFilter
    w, h = img.size
    top, bottom = (16, 22, 44), (8, 8, 12)
    grad = Image.new("RGB", (1, h))
    for yy in range(h):
        k = min(1.0, yy / (h * 0.75))
        grad.putpixel((0, yy), tuple(int(top[c] + (bottom[c] - top[c]) * k) for c in range(3)))
    img = grad.resize((w, h))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    g = ImageDraw.Draw(glow)
    g.ellipse([w // 2 - 330, -40, w // 2 + 10, 300], fill=(150, 64, 10))
    g.ellipse([w // 2 - 10, -20, w // 2 + 330, 300], fill=(10, 110, 120))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    from PIL import ImageChops
    return ImageChops.add(img, glow)


def _pc_icon(d, kind, cx, cy, color):
    """A filled colour disc with a tiny white glyph: person, shield, bars or calendar."""
    r = 30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    w = "#ffffff"
    if kind == "name":
        d.ellipse([cx - 8, cy - 15, cx + 8, cy + 1], fill=w)
        d.pieslice([cx - 15, cy + 3, cx + 15, cy + 31], 180, 360, fill=w)
    elif kind == "service":
        d.polygon([(cx, cy - 16), (cx + 14, cy - 10), (cx + 12, cy + 6), (cx, cy + 17), (cx - 12, cy + 6), (cx - 14, cy - 10)], fill=w)
    elif kind == "volume":
        for k, hgt in enumerate((10, 18, 26)):
            x = cx - 14 + k * 11
            d.rounded_rectangle([x, cy + 13 - hgt, x + 7, cy + 13], radius=2, fill=w)
    else:
        d.rounded_rectangle([cx - 15, cy - 11, cx + 15, cy + 15], radius=4, fill=w)
        d.rectangle([cx - 15, cy - 4, cx + 15, cy - 1], fill=color)
        for x in (cx - 8, cx + 8):
            d.rounded_rectangle([x - 2, cy - 17, x + 2, cy - 7], radius=2, fill=w)


def phone_card_details(img, d, order, y, font, fa, width):
    """The service's name, protocols, volume and expiry in a panel with a colour strip; returns the y
    under the «active» pill."""
    from PIL import ImageFont
    L, R = 60, CARD_W - 60
    row_h = 112
    rows = ("name", "service", "volume", "expire")
    bottom = y + row_h * len(rows) + 20
    d.rounded_rectangle([L, y, R, bottom], radius=30, fill=PC_PANEL, outline=PC_EDGE, width=2)
    # colour strip along the top edge: the three protocols' colours
    seg = (R - L - 80) / 3
    for k, (_, c) in enumerate(PC_PROTO):
        d.rounded_rectangle([L + 40 + k * seg + 4, y - 3, L + 40 + (k + 1) * seg - 4, y + 5], radius=4, fill=c)
    f_lab, f_val = font("Regular", 29), font("Bold", 34)
    labels = {"name": "نام سرویس", "service": "سرویس", "volume": "حجم", "expire": "انقضا"}
    yy = y + 10
    for i, kind in enumerate(rows):
        cy = yy + row_h // 2
        _pc_icon(d, kind, R - 62, cy, PC_ROW[kind])
        lab = fa(labels[kind])
        d.text((R - 110 - width(lab, f_lab), cy - 22), lab, font=f_lab, fill="#9aa3b8")
        if kind == "service":
            # three coloured chips, IKEv2 first on the left
            f_c = font("Bold", 26)
            x = L + 30
            for name, c in PC_PROTO:
                cw = width(name, f_c) + 34
                d.rounded_rectangle([x, cy - 23, x + cw, cy + 23], radius=23, outline=c, width=3)
                d.text((x + 17, cy - 19), name, font=f_c, fill=c)
                x += cw + 10
        else:
            value = {"name": order["username"], "volume": vol_text(order["volume_gb"]),
                     "expire": datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d")}[kind]
            fv, dy = f_val, 26
            if kind == "name":
                try:
                    fv, dy = ImageFont.truetype(A_MONO_PATH, 36), 22
                except OSError:
                    pass
            d.text((L + 34, cy - dy), fa(value), font=fv, fill=PC_ROW[kind] if kind == "volume" else "#f5f7fb")
        if i < len(rows) - 1:
            d.line([L + 30, yy + row_h, R - 30, yy + row_h], fill=PC_HAIR, width=2)
        yy += row_h
    y = bottom + 34
    # what to do next, pointing down at the buttons under the photo
    hint = fa("برای اتصال، دکمه‌ی گوشی خود را بزنید")
    f_p = font("Bold", 30)
    pw = width(hint, f_p) + 100
    px = (CARD_W - pw) // 2
    d.rounded_rectangle([px, y, px + pw, y + 62], radius=31, fill="#3ddc84")
    ax = px + 40
    d.polygon([(ax - 13, y + 24), (ax + 13, y + 24), (ax, y + 40)], fill="#0b3b20")
    d.text((px + 66, y + 10), hint, font=f_p, fill="#0b3b20")
    return y + 62


# ---------- کارت لاجوردی سرویس گوشی (خرید جدید و «سرویس‌های من») ----------
LZ = {"ground": "#0A1730", "panel": "#0F2247", "line": "#1E3A6E", "track": "#1B3566", "dot": "#16305F",
      "dash": "#2A4A85", "ink": "#EAF0FF", "muted": "#9DB0D6", "turq": "#35D0C0", "silver": "#DCE4F5",
      "blue": "#7FA8FF", "orange": "#FFA94D", "red": "#FF6B6B", "dim": "#BFC9DE"}
LZ_PROTO = (("IKEv2", "turq"), ("L2TP", "blue"), ("PPTP", "silver"))
FA_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _lz_font(name, size, weight=None):
    """Vazirmatn for Persian; Unbounded and JetBrains Mono (variable fonts) for the Latin figures.
    A missing Latin face falls back to Vazirmatn so the card never fails over a font."""
    from PIL import ImageFont
    if name in ("Regular", "Bold"):
        return ImageFont.truetype(os.path.join(ASSET_DIR, f"Vazirmatn-{name}.ttf"), size)
    try:
        f = ImageFont.truetype(os.path.join(ASSET_DIR, f"{name}-VF.ttf"), size)
        if weight:
            f.set_variation_by_axes([weight])
        return f
    except (OSError, ValueError):
        return ImageFont.truetype(os.path.join(ASSET_DIR, "Vazirmatn-Bold.ttf"), size)


def _lz_num(x):
    return f"{x:g}" if x < 100 else f"{x:.0f}"


def lapis_card_png(order, used_gb=None, fresh=False):
    """The service as a lapis card: usage dial, name/protocol/expiry, days-left strip.
    fresh: just bought (nothing used yet, and a hint pointing at the buttons under the photo).
    used_gb: GB used per the panel; None means the panel did not answer. None if the card can't be drawn."""
    try:
        import math
        from PIL import Image, ImageDraw, features
        if not features.check("raqm"):
            return None
        W, P = CARD_W, 36            # card width, side gutter
        L, R = P, W - P
        img = Image.new("RGB", (W, 1700), LZ["ground"])
        d = ImageDraw.Draw(img)
        # dot grid behind everything
        for gy in range(18, 1700, 36):
            for gx in range(18, W, 36):
                d.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=LZ["dot"])
        wid = lambda t, f: d.textbbox((0, 0), t, font=f)[2] - d.textbbox((0, 0), t, font=f)[0]

        now = time.time()
        total = order["volume_gb"] or 0
        used = 0.0 if fresh else used_gb
        expired = order["expire_at"] <= now
        out = bool(total) and used is not None and used >= total
        active = order["status"] == "active" and not expired and not out
        days_left = max(0, math.ceil((order["expire_at"] - now) / 86400 - 0.01))
        days_total = max(1, int(order["days"] or 30), days_left)

        # --- top row: state on the right, brand on the left
        y = 40
        if active:
            state, dot = "فعال", (LZ["orange"] if days_left <= 3 or (total and used is not None and used / total >= .85) else LZ["turq"])
        else:
            state, dot = ("حجم تمام شد" if out else "منقضی شده" if expired else "غیرفعال"), LZ["red"]
        f_small, f_state = _lz_font("Regular", 26), _lz_font("Bold", 32)
        lab = "وضعیت سرویس"
        d.text((R - 8 - wid(lab, f_small), y + 22), lab, font=f_small, fill=LZ["muted"])
        sw = wid(state, f_state)
        d.text((R - 8 - sw, y + 62), state, font=f_state, fill=LZ["ink"])
        cx, cy = R - 8 - sw - 22, y + 86
        d.ellipse([cx - 22, cy - 22, cx + 22, cy + 22], fill=_lz_mix(dot, LZ["ground"], .22))
        d.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=dot)

        mark = Image.open(os.path.join(ASSET_DIR, "tifusi-emblem.png")).convert("RGBA")
        mark = mark.resize((196, int(196 * mark.height / mark.width)), Image.LANCZOS)
        img.paste(mark, (L, y), mark)
        f_brand, f_vpn = _lz_font("Unbounded", 44, 800), _lz_font("Unbounded", 22, 500)
        bx, by = L + mark.width + 22, y + mark.height // 2 - 38
        d.text((bx, by), "TIFUSI", font=f_brand, fill=LZ["ink"])
        x = bx + 2
        for ch in "VPN":           # letter-spaced, like the CSS
            d.text((x, by + 58), ch, font=f_vpn, fill=LZ["turq"])
            x += wid(ch, f_vpn) + 12
        y += max(mark.height, 130) + 28

        # --- usage panel with the dial
        top = y
        ph = 624
        d.rounded_rectangle([L, top, R, top + ph], radius=56, fill=LZ["panel"], outline=LZ["line"], width=3)
        D = 472
        dx, dy = (W - D) // 2, top + 44
        frac = 0.0 if not total or used is None else max(0.0, min(1.0, used / total))
        ring = LZ["turq"] if frac < .85 else LZ["orange"] if frac < 1 else LZ["red"]
        # CSS conic-gradient from 225deg (clockwise from north) = PIL angle 135, a 270° sweep
        d.arc([dx, dy, dx + D, dy + D], 135, 405, fill=LZ["track"], width=36)
        if not total and used is not None:
            d.arc([dx, dy, dx + D, dy + D], 135, 405, fill=_lz_mix(LZ["turq"], LZ["track"], .45), width=36)
        elif frac > 0:
            d.arc([dx, dy, dx + D, dy + D], 135, 135 + max(3, 270 * frac), fill=ring, width=36)
        else:
            d.arc([dx, dy, dx + D, dy + D], 135, 138, fill=LZ["turq"], width=36)
        _lz_dashed_circle(d, W // 2, dy + D // 2, D // 2 - 60, LZ["dash"])
        mid = dy + D // 2
        lab = "مصرف"
        d.text(((W - wid(lab, f_small)) // 2, mid - 112), lab, font=f_small, fill=LZ["muted"])
        if used is None:
            big, tail = "—", ""
        else:
            big, tail = _lz_num(round(used, 2)), (f"/ {_lz_num(total)}" if total else "/ ∞")
        fb = _lz_font("Unbounded", 124 if len(big) <= 2 else 96 if len(big) <= 4 else 76, 800)
        ft = _lz_font("Unbounded", 40, 500) if total else _lz_font("Regular", 46)
        bw, tw = wid(big, fb), (wid(tail, ft) + 12 if tail else 0)
        bx = (W - bw - tw) // 2
        bb = d.textbbox((bx, 0), big, font=fb)
        d.text((bx, mid + 22 - bb[3]), big, font=fb, fill=ring if total else LZ["turq"])
        if tail:
            tb = d.textbbox((0, 0), tail, font=ft)
            d.text((bx + bw + 12, mid + 22 - tb[3]), tail, font=ft, fill=LZ["muted"])
        f_gb = _lz_font("Unbounded", 24, 500)
        gbw = sum(wid(c, f_gb) for c in "GB") + 8
        x = (W - gbw) // 2
        for ch in "GB":
            d.text((x, mid + 44), ch, font=f_gb, fill=LZ["muted"])
            x += wid(ch, f_gb) + 8
        if total:
            f_end = _lz_font("JetBrainsMono", 26, 600)
            d.text((dx + 70, dy + D - 30), "0", font=f_end, fill=LZ["muted"])
            e = _lz_num(total)
            d.text((dx + D - 70 - wid(e, f_end), dy + D - 30), e, font=f_end, fill=LZ["muted"])
        # remaining row under the dial
        ry = dy + D + 30
        f_left = _lz_font("Bold", 32)
        if used is None:
            left = "مصرف فعلاً در دسترس نیست"
        elif not total:
            left = "حجم نامحدود"
        else:
            left = f"{_lz_num(max(0.0, round(total - used, 2)))} گیگ باقی‌مانده".translate(FA_DIGITS)
        d.text((R - 40 - wid(left, f_left), ry), left, font=f_left, fill=LZ["ink"])
        if total and used is not None:
            pct = f"{round(frac * 100)}%"
            f_pct = _lz_font("JetBrainsMono", 28, 700)
            pw = wid(pct, f_pct) + 48
            d.rounded_rectangle([L + 40, ry + 2, L + 40 + pw, ry + 50], radius=24, fill=ring)
            d.text((L + 64, ry + 8), pct, font=f_pct, fill=LZ["ground"])
        y = top + ph + 32

        # --- facts panel
        rows = [("نام سرویس", "name"), ("سرویس", "proto"), ("انقضا", "expire")]
        rh = 116
        top = y
        d.rounded_rectangle([L, top, R, top + rh * len(rows) + 12], radius=56, fill=LZ["panel"], outline=LZ["line"], width=3)
        f_dt = _lz_font("Regular", 28)
        yy = top + 6
        for i, (label, kind) in enumerate(rows):
            cy = yy + rh // 2
            d.text((R - 40 - wid(label, f_dt), cy - 24), label, font=f_dt, fill=LZ["muted"])
            if kind == "proto":
                f_c = _lz_font("JetBrainsMono", 26, 700)
                x = L + 40
                for name, tone in LZ_PROTO:
                    cw = wid(name, f_c) + 44
                    d.rounded_rectangle([x, cy - 26, x + cw, cy + 26], radius=20, fill=LZ[tone])
                    tb = d.textbbox((0, 0), name, font=f_c)
                    d.text((x + 22, cy - (tb[1] + tb[3]) // 2), name, font=f_c, fill=LZ["ground"])
                    x += cw + 12
            else:
                value = order["username"] if kind == "name" else \
                    datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d")
                fv = _lz_font("JetBrainsMono", 40 if kind == "name" else 36, 700)
                tb = d.textbbox((0, 0), value, font=fv)
                d.text((L + 40, cy - (tb[1] + tb[3]) // 2), value, font=fv, fill=LZ["ink"])
            if i < len(rows) - 1:
                _lz_dashed_line(d, L + 40, R - 40, yy + rh, LZ["line"])
            yy += rh
        y = top + rh * len(rows) + 12 + 32

        # --- days strip
        top = y
        sh = 200
        d.rounded_rectangle([L, top, R, top + sh], radius=56, fill=LZ["silver"])
        f_days, f_dl, f_of = _lz_font("Bold", 76), _lz_font("Bold", 32), _lz_font("Regular", 26)
        if expired:
            num, unit = "", "سرویس منقضی شده"
        else:
            num, unit = str(days_left).translate(FA_DIGITS), "روز مانده"
        nw = wid(num, f_days) if num else 0
        uw = wid(unit, f_dl)
        base = top + 112
        if num:
            nb = d.textbbox((0, 0), num, font=f_days)
            d.text((R - 40 - nw, base - nb[3]), num, font=f_days, fill=LZ["ground"])
        ub = d.textbbox((0, 0), unit, font=f_dl)
        d.text((R - 40 - nw - (14 if num else 0) - uw, base - ub[3]), unit, font=f_dl, fill=LZ["ground"])
        of = f"از {days_total} روز".translate(FA_DIGITS)
        ob = d.textbbox((0, 0), of, font=f_of)
        d.text((L + 40, base - ob[3]), of, font=f_of, fill=LZ["ground"])
        cells, gap = 30, 6
        on = cells if days_left >= days_total else round(cells * days_left / days_total)
        cw = (R - L - 80 - gap * (cells - 1)) / cells
        for k in range(cells):
            x0 = L + 40 + k * (cw + gap)
            d.rounded_rectangle([x0, top + 134, x0 + cw, top + 178], radius=6,
                                fill=LZ["ground"] if k < on else _lz_mix(LZ["ground"], LZ["silver"], .2))
        y = top + sh

        if fresh:
            y += 34
            hint = "برای اتصال، دکمه‌ی گوشی خود را بزنید"
            f_h = _lz_font("Bold", 30)
            pw = wid(hint, f_h) + 110
            px = (W - pw) // 2
            d.rounded_rectangle([px, y, px + pw, y + 64], radius=32, fill=LZ["turq"])
            ax = px + 42
            d.polygon([(ax - 13, y + 25), (ax + 13, y + 25), (ax, y + 41)], fill=LZ["ground"])
            d.text((px + 72, y + 10), hint, font=f_h, fill=LZ["ground"])
            y += 64

        buf = io.BytesIO()
        img.crop((0, 0, W, y + 44)).save(buf, format="PNG", optimize=True)
        buf.seek(0)
        buf.name = "tifusi.png"
        return buf
    except Exception as e:
        log.warning("lapis card failed: %s", e)
        return None


def _lz_mix(a, b, k):
    """Colour a at strength k over colour b (both #rrggbb)."""
    pa = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    pb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(pa[c] * k + pb[c] * (1 - k)):02x}" for c in range(3))


def _lz_dashed_line(d, x0, x1, y, color):
    x = x0
    while x < x1:
        d.line([x, y, min(x + 12, x1), y], fill=color, width=3)
        x += 22


def _lz_dashed_circle(d, cx, cy, r, color):
    import math
    n = int(2 * math.pi * r / 18)
    for k in range(0, n, 2):
        a0, a1 = 360 * k / n, 360 * (k + 1) / n
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a1, fill=color, width=3)


def service_status_png(order, used_gb=None):
    """کارت «سرویس‌های من» برای سرویس گوشی: هر بار با مصرف همان لحظه ساخته می‌شود.
    used_gb: گیگ مصرف‌شده از پنل؛ None یعنی پنل جواب نداد. None برمی‌گرداند اگر ساختن عکس ممکن نبود."""
    card = lapis_card_png(order, used_gb)
    if card:
        return card
    try:
        from PIL import Image, ImageDraw, ImageFont, features
        if not features.check("raqm"):
            return None
        def font(name, size):
            return ImageFont.truetype(os.path.join(ASSET_DIR, f"Vazirmatn-{name}.ttf"), size)
        img = phone_card_ground(Image.new("RGB", (CARD_W, 1500), CARD_GROUND))
        d = ImageDraw.Draw(img)
        width = lambda text, f: d.textbbox((0, 0), text, font=f)[2]
        center = lambda y, text, f, fill: d.text(((CARD_W - width(text, f)) // 2, y), text, font=f, fill=fill)
        L, R = 60, CARD_W - 60

        # header: smaller mark and title
        mark = Image.open(os.path.join(ASSET_DIR, "tifusi-mark.png")).convert("RGBA")
        mark = mark.resize((160, int(160 * mark.height / mark.width)), Image.LANCZOS)
        img.paste(mark, ((CARD_W - mark.width) // 2, 44), mark)
        y = 44 + mark.height + 10
        center(y, "Tifusi VPN", font("Bold", 40), "#f5f7fb")
        y += 56
        center(y, "وضعیت سرویس", font("Regular", 26), "#9aa3b8")
        y += 62

        now = time.time()
        active = order["status"] == "active" and order["expire_at"] > now
        # usage panel
        top = y
        total = order["volume_gb"]
        ph = 250 if total and used_gb is not None else 190 if not total and used_gb is not None else 130
        d.rounded_rectangle([L, top, R, top + ph], radius=30, fill=PC_PANEL, outline=PC_EDGE, width=2)
        f_lab = font("Regular", 29)
        _pc_icon(d, "volume", R - 62, top + 62, PC_ROW["volume"])
        lab = "مصرف"
        d.text((R - 110 - width(lab, f_lab), top + 40), lab, font=f_lab, fill="#9aa3b8")
        if not total:
            big = "نامحدود ∞"
            d.text((L + 34, top + 34), big, font=font("Bold", 44), fill="#3ddc84")
            used_line = f"{used_gb:g} گیگ مصرف شده" if used_gb is not None else ""
            if used_line:
                d.text((R - 40 - width(used_line, font("Regular", 28)), top + 116), used_line, font=font("Regular", 28), fill="#c9d1e3")
        elif used_gb is None:
            d.text((L + 34, top + 40), "در دسترس نیست", font=font("Bold", 34), fill="#9aa3b8")
        else:
            frac = max(0.0, min(1.0, used_gb / total))
            color = "#3ddc84" if frac < 0.6 else "#f97316" if frac < 0.85 else "#ff5a5f"
            left = max(0.0, round(total - used_gb, 2))
            num = f"{used_gb:g} / {total:g}"
            fn = font("Bold", 46)
            d.text((L + 34, top + 28), num, font=fn, fill="#f5f7fb")
            d.text((L + 34 + width(num, fn) + 12, top + 44), "GB", font=font("Bold", 28), fill="#9aa3b8")
            # the bar
            by = top + 128
            d.rounded_rectangle([L + 34, by, R - 34, by + 30], radius=15, fill="#232a40")
            if frac > 0:
                d.rounded_rectangle([L + 34, by, L + 34 + max(30, int((R - L - 68) * frac)), by + 30], radius=15, fill=color)
            pct = f"{round(frac * 100)}%"
            d.text((L + 34, by + 46), pct, font=font("Bold", 30), fill=color)
            rem = f"{left:g} گیگ باقی‌مانده"
            fr = font("Regular", 29)
            d.text((R - 34 - width(rem, fr), by + 46), rem, font=fr, fill="#c9d1e3")
        y = top + ph + 26

        # details panel
        rows = [("name", "نام سرویس", order["username"]), ("service", "سرویس", None),
                ("expire", "انقضا", datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d"))]
        row_h = 104
        top = y
        bottom = top + row_h * len(rows) + 16
        d.rounded_rectangle([L, top, R, bottom], radius=30, fill=PC_PANEL, outline=PC_EDGE, width=2)
        yy = top + 8
        for i, (kind, label, value) in enumerate(rows):
            cy = yy + row_h // 2
            _pc_icon(d, kind, R - 62, cy, PC_ROW[kind])
            d.text((R - 110 - width(label, f_lab), cy - 22), label, font=f_lab, fill="#9aa3b8")
            if kind == "service":
                f_c, x = font("Bold", 26), L + 30
                for name, c in PC_PROTO:
                    cw = width(name, f_c) + 34
                    d.rounded_rectangle([x, cy - 23, x + cw, cy + 23], radius=23, outline=c, width=3)
                    d.text((x + 17, cy - 19), name, font=f_c, fill=c)
                    x += cw + 10
            elif kind == "name":
                try:
                    fv = ImageFont.truetype(A_MONO_PATH, 36)
                except OSError:
                    fv = font("Bold", 34)
                d.text((L + 34, cy - 22), value, font=fv, fill="#f5f7fb")
            else:
                d.text((L + 34, cy - 26), value, font=font("Bold", 34), fill="#f5f7fb")
            if i < len(rows) - 1:
                d.line([L + 30, yy + row_h, R - 30, yy + row_h], fill=PC_HAIR, width=2)
            yy += row_h
        y = bottom + 34

        # status pill with days left
        days = max(0, int((order["expire_at"] - now) // 86400))
        pill = f"فعال · {days} روز مانده" if active else "منقضی شده"
        bg, ink = ("#3ddc84", "#0b3b20") if active and days > 3 else ("#f97316", "#3b1a05") if active else ("#ff5a5f", "#3b0a0b")
        f_p = font("Bold", 30)
        pw = width(pill, f_p) + 76
        px = (CARD_W - pw) // 2
        d.rounded_rectangle([px, y, px + pw, y + 58], radius=29, fill=bg)
        d.ellipse([px + pw - 36, y + 23, px + pw - 24, y + 35], fill=ink)
        d.text((px + 24, y + 8), pill, font=f_p, fill=ink)
        y += 58

        buf = io.BytesIO()
        img.crop((0, 0, CARD_W, y + 50)).save(buf, format="PNG", optimize=True)
        buf.seek(0)
        buf.name = "tifusi-status.png"
        return buf
    except Exception as e:
        log.warning("service status card failed: %s", e)
        return None


def delivery_card_png(order):
    """کارت تصویری تحویل: فقط نشان تیفوسی و بارکد لینک اشتراک. باقی چیزها (نام، حجم، انقضا،
    شناسه، نصب) روی کپشن و دکمه‌های واقعی زیر عکس‌اند، چون داخل تصویر هیچ‌چیز قابل لمس نیست.
    اگر فونت/نشان‌ها یا کتابخانه‌ها نبودند None برمی‌گردد تا تحویل به حالت متنی قبلی برگردد."""
    # Phone services (IKEv2/L2TP/PPTP) connect from the phone's own settings: no link, so no barcode;
    # their card shows the service's details under the Tifusi mark instead.
    phone = order["protocol"] in ("ikev2", "l2tp", "pptp")
    if not order["sub_url"] and not phone:
        return None
    if phone:
        card = lapis_card_png(order, fresh=True)
        if card:
            return card
    try:
        from PIL import Image, ImageDraw, ImageFont, features

        def font(name, size):
            return ImageFont.truetype(os.path.join(ASSET_DIR, f"Vazirmatn-{name}.ttf"), size)

        if features.check("raqm"):
            # Pillow built with libraqm joins and reorders Persian itself. Running
            # reshape+bidi before it reverses the line a second time — the card came
            # out with «اشتراک شما فعال شد» drawn as «دش لاعف امش کارتشا».
            def fa(text):
                return text
        else:
            import arabic_reshaper
            try:
                from bidi import get_display
            except ImportError:
                from bidi.algorithm import get_display

            def fa(text):
                return get_display(arabic_reshaper.reshape(text))

        img = Image.new("RGB", (CARD_W, 1100), CARD_GROUND)
        if phone:
            img = phone_card_ground(img)
        d = ImageDraw.Draw(img)

        def width(text, f):
            return d.textbbox((0, 0), text, font=f)[2]

        f_title, f_sub = font("Bold", 46), font("Regular", 25)

        mark = Image.open(os.path.join(ASSET_DIR, "tifusi-mark.png")).convert("RGBA")
        mark = mark.resize((200, int(200 * mark.height / mark.width)), Image.LANCZOS)
        img.paste(mark, ((CARD_W - mark.width) // 2, 60), mark)

        y = 60 + mark.height + 16
        d.text(((CARD_W - width("Tifusi VPN", f_title)) // 2, y), "Tifusi VPN", font=f_title, fill=CARD_TEXT)
        y += 62
        if phone:
            t, f_s = fa("سرویس شما فعال شد"), font("Bold", 34)
            tw = width(t, f_s)
            tx = (CARD_W - tw) // 2 + 26
            d.text((tx, y - 6), t, font=f_s, fill="#3ddc84")
            # a green tick disc before the words (on their right)
            cx, cy = tx + tw + 30, y + 20
            d.ellipse([cx - 20, cy - 20, cx + 20, cy + 20], fill="#3ddc84")
            d.line([cx - 9, cy + 1, cx - 2, cy + 8, cx + 10, cy - 7], fill="#0b3b20", width=5)
        else:
            t = fa("اشتراک شما فعال شد")
            d.text(((CARD_W - width(t, f_sub)) // 2, y), t, font=f_sub, fill=CARD_MUTED)

        y += 56
        if phone:
            y += 22  # room between «active» and the panel's colour strip
            y = phone_card_details(img, d, order, y, font, fa, width)
            buf = io.BytesIO()
            img.crop((0, 0, CARD_W, y + 50)).save(buf, format="PNG", optimize=True)
            buf.seek(0)
            buf.name = "tifusi.png"
            return buf

        import qrcode
        qr = qrcode.make(order["sub_url"], box_size=10, border=1).convert("RGB").resize((500, 500), Image.NEAREST)
        box = 540
        qx = (CARD_W - box) // 2
        d.rounded_rectangle([qx, y, qx + box, y + box], radius=26, fill="#ffffff")
        img.paste(qr, (qx + 20, y + 20))

        y += box + 30
        t = fa(f"بارکد اشتراک {SERVICES.get(order['protocol'], '')}".strip())
        d.text(((CARD_W - width(t, f_sub)) // 2, y), t, font=f_sub, fill=CARD_MUTED)

        buf = io.BytesIO()
        img.crop((0, 0, CARD_W, y + 60)).save(buf, format="PNG", optimize=True)
        buf.seek(0)
        buf.name = "tifusi.png"
        return buf
    except Exception as e:
        log.warning("delivery card render failed: %s", e)
        return None


def qr_png(data):
    """تصویر QR لینک اشتراک در حافظه (PNG). اگر کتابخانه‌ی qrcode نبود یا خطا داد None برمی‌گردد
    تا تحویل متنی سرویس هیچ‌وقت به‌خاطر QR متوقف نشود."""
    if not data:
        return None
    try:
        import qrcode
        buf = io.BytesIO()
        qrcode.make(data).save(buf)
        buf.seek(0)
        buf.name = "qr.png"
        return buf
    except Exception as e:
        log.warning("QR generation failed: %s", e)
        return None


async def send_order_qr(context, chat_id, order):
    """بارکد لینک اشتراک با خود لینک زیر آن؛ اگر بارکد ساخته یا فرستاده نشد False."""
    png = qr_png(order["sub_url"])
    if not png:
        return False
    try:
        await context.bot.send_photo(chat_id, png, caption=order["sub_url"])
        return True
    except Exception as e:
        log.warning("send QR failed for %s: %s", chat_id, e)
        return False


def apple_profile_url(order, links):
    """لینک نصب یک‌لمسی پروفایل آیفون برای همین سرویس (IKEv2 یا L2TP)؛ None اگر پنل نداد.
    install_url صفحه‌ای است که مشتری را از مرورگر تلگرام به Safari می‌برد (آیفون پروفایل را فقط
    در Safari نصب می‌کند)؛ پنل قدیمی‌تر فقط mobileconfig_url را می‌دهد."""
    if order["protocol"] not in IPSEC_SERVICES:
        return None
    cfgs = (links or {}).get(f"{order['protocol']}_configs") or []
    return (cfgs[0].get("install_url") or cfgs[0].get("mobileconfig_url")) if cfgs else None


# نوع اتصال همان‌طور که در منوی VPN خود گوشی نوشته شده، تا مشتری همان را انتخاب کند
MANUAL_TYPE = {"ikev2": "IKEv2/IPSec MSCHAPv2", "l2tp": "L2TP/IPSec PSK", "pptp": "PPTP"}


def ipsec_manual_lines(links, order, code=lambda v: f"<code>{html.escape(v)}</code>", text=html.escape):
    """اطلاعات ورود دستی IKEv2 یا L2TP (نوع، سرور، نام کاربری، رمز و برای L2TP سکرت) برای وارد کردن
    در تنظیمات VPN خود گوشی؛ لیست خالی اگر سرویس IPsec نیست.
    code/text: قالب مقدارها و متن ساده — HTML برای تحویل، Markdown برای «سرویس‌های من»."""
    proto = order["protocol"]
    if proto not in MANUAL_TYPE:
        return []
    cfgs = (links or {}).get(f"{proto}_configs") or []
    if cfgs:
        lines = [f"🧩 نوع: {code(MANUAL_TYPE[proto])}",
                 f"👤 نام کاربری: {code(cfgs[0]['username'])}",
                 f"🔑 رمز عبور: {code(cfgs[0]['password'])}"]
        for cfg in cfgs:
            if len(cfgs) > 1:
                lines.append(f"\n📍 {text(cfg.get('remark') or cfg['server'])}")
            lines.append(f"🌐 سرور: {code(cfg['server'])}")
            if proto == "l2tp" and cfg.get("psk"):
                lines.append(f"🔐 سکرت: {code(cfg['psk'])}")
        # اندرویدهای ۱۰ و قدیمی‌تر IKEv2 با نام کاربری ندارند و اندرویدهای جدید L2TP را حذف کرده‌اند؛
        # همین حساب روی L2TP هم کار می‌کند، پس با همان نام کاربری و رمز، L2TP «اگر نبود» می‌آید
        # تا مشتری لازم نباشد بداند گوشی‌اش چه دارد.
        l2tp = ((links or {}).get("l2tp_configs") or []) if proto == "ikev2" else []
        if l2tp:
            lines[0] = f"🧩 نوع: {code(MANUAL_TYPE['ikev2'])}"
            lines.insert(0, f"1️⃣ اگر در «نوع» گزینه‌ی {text(MANUAL_TYPE['ikev2'])} هست:")
            lines.append("")
            lines.append(f"2️⃣ اگر نبود (اندروید قدیمی)، نوع {code(MANUAL_TYPE['l2tp'])} را بزنید:")
            for cfg in l2tp[:1]:
                lines.append(f"🌐 سرور: {code(cfg['server'])}")
                if cfg.get("psk"):
                    lines.append(f"🔐 سکرت (کلید IPsec): {code(cfg['psk'])}")
            lines.append("👤🔑 نام کاربری و رمز: همان بالا")
        return lines
    if order["password"]:
        # پنل جواب نداد: دست‌کم نام کاربری و رمزی که با آن ساخته شد
        return [f"👤 نام کاربری: {code(order['username'])}",
                f"🔑 رمز عبور: {code(order['password'])}"]
    return []


# ---------- راهنمای اتصال با دکمه (بعد از خرید) ----------
# به‌جای ریختن همه‌ی روش‌ها زیر کارت سرویس، مشتری دکمه‌ی گوشی خودش را می‌زند و فقط همان روش را
# می‌بیند؛ دکمه‌های زیر راهنما همان پیام را عوض می‌کنند تا صفحه شلوغ نشود.
GUIDE_LABELS = {"ikev2": "🤖 اندروید جدید (IKEv2)", "l2tp": "🤖 اندروید قدیمی (L2TP)",
                "pptp": "🦖 گوشی خیلی قدیمی (PPTP)", "which": "❓ نمی‌دانم گوشی‌ام کدام است"}


def guide_kinds(order, links):
    """روش‌هایی که این سفارش واقعاً دارد: IKEv2 و/یا L2TP، به‌اضافه‌ی «کدام؟» وقتی هر دو هست."""
    # PPTP comes last: weak encryption, kept for phones where nothing else connects.
    have = [k for k in ("ikev2", "l2tp", "pptp") if (links or {}).get(f"{k}_configs")]
    if not have and order["protocol"] in ("ikev2", "l2tp", "pptp"):
        have = [order["protocol"]]
    return have + (["which"] if len(have) >= 2 else [])


def guide_markup(oid, kinds, current=None):
    rows = [[InlineKeyboardButton(GUIDE_LABELS[k], callback_data=f"how:{k}:{oid}")] for k in kinds if k != current]
    rows.append([InlineKeyboardButton("🔙 بازگشت به سرویس", callback_data=f"svc:{oid}")])
    return InlineKeyboardMarkup(rows)


def guide_cfg(order, links, kind):
    """The panel's login for one method; the order's own login when the panel did not answer."""
    cfgs = (links or {}).get(f"{kind}_configs") or []
    return cfgs[0] if cfgs else {"server": "-", "username": order["username"], "password": order["password"] or "-"}


def guide_html(order, links, kind):
    esc = html.escape
    code = lambda v: f"<code>{esc(str(v))}</code>"
    if kind == "which":
        return ("❓ <b>کدام را بزنم؟</b>\n\n"
                "تنظیمات گوشی ← <b>VPN</b> ← <b>افزودن</b> ← روی <b>«نوع»</b> بزنید:\n\n"
                f"• اگر <b>{esc(MANUAL_TYPE['ikev2'])}</b> را دیدید ← دکمه‌ی «اندروید جدید (IKEv2)»\n"
                f"• اگر نبود ← دکمه‌ی «اندروید قدیمی (L2TP)»\n\n"
                "• اگر هیچ‌کدام وصل نشد ← دکمه‌ی «گوشی خیلی قدیمی (PPTP)»\n\n"
                "💡 اگر IKEv2 با یوزر و پسورد وصل نشد، نوع <b>IKEv2/IPSec PSK</b> هم کار می‌کند: شناسه = نام کاربری، کلید = رمز خودتان (دکمه‌ی «🔐 با یوزر و پسورد وصل نشد؟» زیر «اتصال در اندروید»).\n"
                "💡 اگر گزینه‌ها خاکستری و قفل بود، اول برای گوشی قفل صفحه (پین یا الگو) بگذارید.")
    cfg = guide_cfg(order, links, kind)
    if kind == "ikev2":
        return (f"🤖 <b>اندروید ۱۱ به بعد — IKEv2</b>\n\n"
                f"تنظیمات ← VPN ← افزودن، و این‌ها را بزنید (روی هر مقدار بزنید کپی می‌شود):\n\n"
                f"🧩 نوع: {code(MANUAL_TYPE['ikev2'])}\n"
                f"🌐 آدرس سرور: {code(cfg['server'])}\n"
                f"🆔 شناسه‌ی IPSec: {code(cfg['username'])}\n"
                f"🔒 گواهی IPSec CA: «استفاده از گواهی‌های سیستم»\n"
                f"📜 مجوز سرور IPSec: «از سرور دریافت شود»\n"
                f"👤 نام کاربری: {code(cfg['username'])}\n"
                f"🔑 رمز عبور: {code(cfg['password'])}\n\n"
                f"ذخیره ← روی VPN بزنید ← اتصال ✅")
    if kind == "pptp":
        return (f"🦖 <b>گوشی خیلی قدیمی — PPTP</b>\n"
                f"(آخرین راه: رمزنگاری‌اش ضعیف است؛ فقط اگر IKEv2 و L2TP وصل نشد)\n\n"
                f"تنظیمات ← VPN ← افزودن، و این‌ها را بزنید (روی هر مقدار بزنید کپی می‌شود):\n\n"
                f"🧩 نوع: {code(MANUAL_TYPE['pptp'])}\n"
                f"🌐 آدرس سرور: {code(cfg['server'])}\n"
                f"🔒 رمزگذاری PPP (MPPE): روشن\n"
                f"👤 نام کاربری: {code(cfg['username'])}\n"
                f"🔑 رمز عبور: {code(cfg['password'])}\n\n"
                f"ذخیره ← روی VPN بزنید ← اتصال ✅")
    psk = cfg.get("psk")
    return (f"🤖 <b>اندروید قدیمی — L2TP</b>\n\n"
            f"تنظیمات ← VPN ← افزودن، و این‌ها را بزنید (روی هر مقدار بزنید کپی می‌شود):\n\n"
            f"🧩 نوع: {code(MANUAL_TYPE['l2tp'])}\n"
            f"🌐 آدرس سرور: {code(cfg['server'])}\n"
            + (f"🔐 کلید از پیش مشترک IPSec: {code(psk)}\n" if psk else "")
            + f"🆔 شناسه‌ی IPSec و رمز L2TP: خالی بماند\n"
            f"👤 نام کاربری: {code(cfg['username'])}\n"
            f"🔑 رمز عبور: {code(cfg['password'])}\n\n"
            f"ذخیره ← روی VPN بزنید ← اتصال ✅")


# ---------- دکمه‌ی «اتصال در اندروید»: سرور، نام کاربری، رمز و نوع، همه در یک پیام ----------
ANDROID_BTN = "🤖 اتصال در اندروید"
GUIDE_BTN = "📖 راهنمای اتصال"


def guide_button(order):
    """راهنمای قدم‌به‌قدم پنل (/sub/<secret>/guide) به‌صورت مینی‌اپ تلگرام، برای IKEv2 و L2TP.
    مینی‌اپ فقط آدرس https قبول می‌کند؛ بدون لینک اشتراک دکمه‌ای نمی‌سازیم."""
    url = (order["sub_url"] or "").rstrip("/")
    if order["protocol"] not in ("ikev2", "l2tp") or not url.startswith("https://"):
        return None
    return InlineKeyboardButton(GUIDE_BTN, web_app=WebAppInfo(url=url + "/guide"))


def android_html(order, links):
    """اطلاعات ورود در تنظیمات VPN اندروید برای هر روشی که این سرویس دارد؛ یک نام کاربری و رمز برای همه.
    ترتیب «اگر نبود» همان ترتیب گوشی‌هاست: IKEv2 برای اندروید ۱۱+، L2TP برای قدیمی‌ها، PPTP آخرین راه."""
    esc = html.escape
    code = lambda v: f"<code>{esc(str(v))}</code>"
    kinds = [k for k in ("ikev2", "l2tp", "pptp") if (links or {}).get(f"{k}_configs")]
    if not kinds:
        kinds = [order["protocol"]]
    cfgs = {k: guide_cfg(order, links, k) for k in kinds}
    first = cfgs[kinds[0]]
    servers = {c["server"] for c in cfgs.values()}
    one_server = len(servers) == 1
    # تلگرام رنگ متن ندارد: برچسب‌ها پررنگ، مقدارها <code> (رنگ و پس‌زمینه‌ی جدا و کپی با یک لمس)
    # و هر نوع یک دایره‌ی رنگی، تا چیزهای مهم از بقیه جدا شوند.
    lines = ["🤖 <b>اتصال در اندروید</b>", "",
             "<b>تنظیمات</b> ← <b>VPN</b> ← <b>افزودن</b>", "<i>(روی هر مقدار بزنید کپی می‌شود)</i>", ""]
    if one_server:
        lines.append(f"🌐 <b>آدرس سرور:</b> {code(first['server'])}")
    lines += [f"👤 <b>نام کاربری:</b> {code(first['username'])}", f"🔑 <b>رمز عبور:</b> {code(first['password'])}", ""]
    if len(kinds) > 1:
        lines.append("🧩 روی <b>«نوع»</b> بزنید:")
    nums = {"ikev2": "🟢", "l2tp": "🟡", "pptp": "🔴"}
    nums = [nums[k] for k in kinds]
    for i, k in enumerate(kinds):
        c = cfgs[k]
        if len(kinds) == 1:
            lines.append(f"🧩 <b>نوع:</b> {code(MANUAL_TYPE[k])}")
        elif i == 0:
            lines.append(f"{nums[i]} {code(MANUAL_TYPE[k])} <b>(اگر در لیست هست)</b>")
        else:
            lines.append(f"{nums[i]} <b>{'اگر وصل نشد' if k == 'pptp' else 'اگر نبود'}:</b> {code(MANUAL_TYPE[k])}")
        extra = []
        if not one_server:
            extra.append(f"سرور: {code(c['server'])}")
        if k == "ikev2":
            extra.append("<b>شناسه‌ی IPSec:</b> همان نام کاربری")
        if k == "l2tp" and c.get("psk"):
            extra.append(f"🔐 <b>کلید IPSec:</b> {code(c['psk'])}")
        if k == "pptp":
            extra.append("<b>رمزگذاری PPP (MPPE):</b> روشن")
        if extra:
            lines.append("      " + "  ·  ".join(extra))
    lines += ["", "<b>ذخیره</b> ← روی VPN بزنید ← <b>اتصال</b> ✅"]
    return "\n".join(lines)


PSK_BTN = "🔐 با یوزر و پسورد وصل نشد؟"


def android_psk(order, links):
    """IKEv2 without a certificate (PSK): identifier = the username, key = the user's own password.
    For phones and lines where the certificate of the usual method never gets through. The server
    accepts only the user's own name with their own password; the shared L2TP key does not work here."""
    esc = html.escape
    code = lambda v: f"<code>{esc(str(v))}</code>"
    c = guide_cfg(order, links, "ikev2")
    text = "\n".join([
        "🔐 <b>اتصال IKEv2 بدون یوزر و پسورد (PSK)</b>", "",
        "اگر با روش معمولی وصل نشد، یک VPN <b>جدید</b> بسازید:",
        "<b>تنظیمات</b> ← <b>VPN</b> ← <b>افزودن</b>", "<i>(روی هر مقدار بزنید کپی می‌شود)</i>", "",
        f"🧩 <b>نوع:</b> {code('IKEv2/IPSec PSK')}",
        f"🌐 <b>آدرس سرور:</b> {code(c['server'])}",
        f"🆔 <b>شناسه‌ی IPSec:</b> {code(c['username'])}",
        f"🔑 <b>کلید IPSec:</b> {code(c['password'])}", "",
        "⚠️ کلید همان <b>رمز خود شماست</b>، نه کلید L2TP.",
        "در این نوع، کادر نام کاربری و رمز جدا نیست.", "",
        "<b>ذخیره</b> ← روی VPN بزنید ← <b>اتصال</b> ✅",
    ])
    items = [("کپی سرور", c["server"]), ("کپی شناسه", c["username"]), ("کپی کلید", c["password"])]
    buttons = [b for b in (copy_text_button(label, str(v)) for label, v in items if v and v != "-") if b]
    return text, [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


def android_info(order, links):
    """Values for android_png: the first method's login and, per method, its own server and key."""
    kinds = [k for k in ("ikev2", "l2tp", "pptp") if (links or {}).get(f"{k}_configs")] or [order["protocol"]]
    cfgs = {k: guide_cfg(order, links, k) for k in kinds}
    first = cfgs[kinds[0]]
    return {"server": first["server"], "username": first["username"], "password": first["password"],
            "kinds": kinds, "psk": cfgs.get("l2tp", {}).get("psk"),
            "servers": {k: c["server"] for k, c in cfgs.items()}}


def android_copy_rows(order, links):
    """دکمه‌های «کپی» زیر پیام اندروید، دوتا دوتا: سرور، نام کاربری، رمز و کلید L2TP اگر هست.
    روی تلگرام یا کتابخانه‌ی قدیمی که دکمه‌ی کپی ندارد، خالی برمی‌گردد و متن بالا کافی است."""
    kinds = [k for k in ("ikev2", "l2tp", "pptp") if (links or {}).get(f"{k}_configs")] or [order["protocol"]]
    first = guide_cfg(order, links, kinds[0])
    l2tp = guide_cfg(order, links, "l2tp") if "l2tp" in kinds else {}
    items = [("کپی سرور", first["server"]), ("کپی یوزر", first["username"]),
             ("کپی رمز", first["password"]), ("کپی کلید L2TP", l2tp.get("psk"))]
    buttons = [b for b in (copy_text_button(label, str(v)) for label, v in items if v and v != "-") if b]
    return [buttons[i:i + 2] for i in range(0, len(buttons), 2)]


# ---------- عکس «اتصال در اندروید»: لوگوها و نوع‌ها؛ سرور، یوزر و رمز با دکمه‌های کپی زیر عکس ----------
MONO = A_MONO_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
A_GROUND, A_PANEL, A_FIELD, A_EDGE = "#0a0a0a", "#141414", "#1c1c1c", "#2c2c2c"
A_TEXT, A_MUTED, A_DIM = "#f5f5f5", "#9a9a9a", "#5e5e5e"
A_DROID = "#3ddc84"
# Traffic-light order: green first choice, yellow if it is missing, red last resort.
A_TINT = {"ikev2": "#3ddc84", "l2tp": "#f5c518", "pptp": "#ff5a5f"}
A_TYPE = {"ikev2": "IKEv2/IPSec MSCHAPv2", "l2tp": "L2TP/IPSec PSK", "pptp": "PPTP"}
A_W = 1080


def a_font(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(ASSET_DIR, f"Vazirmatn-{name}.ttf"), size)


def a_mono(size):
    from PIL import ImageFont
    # Mono so a password's l/1 and O/0 can be told apart; Vazirmatn if the system font is missing.
    try:
        return ImageFont.truetype(MONO, size)
    except OSError:
        return a_font("Bold", size)


def a_fit(d, text, make, size, width):
    """The largest font from make(size) downwards that keeps text within width."""
    f = make(size)
    while size > 22 and d.textlength(text, font=f) > width:
        size -= 2
        f = make(size)
    return f


def a_droid(d, cx, top, r):
    d.pieslice([cx - r, top, cx + r, top + 2 * r], 180, 360, fill=A_DROID)
    ey = top + int(r * 0.55)
    for dx in (-0.42, 0.42):
        ex = cx + int(r * dx)
        d.ellipse([ex - r * 0.1, ey - r * 0.1, ex + r * 0.1, ey + r * 0.1], fill=A_GROUND)
    for side in (-1, 1):
        x0, y0 = cx + side * int(r * 0.5), top + int(r * 0.12)
        d.line([x0, y0, x0 + side * int(r * 0.28), y0 - int(r * 0.42)], fill=A_DROID, width=max(3, r // 10))


def android_png(info):
    """info: server, username, password, kinds (in order), and per kind an optional server/psk:
    {"server":…, "username":…, "password":…, "kinds":["ikev2","l2tp","pptp"], "psk":…, "servers":{kind: server}}"""
    try:
        from PIL import Image, ImageDraw, ImageFont, features
        if not features.check("raqm"):
            return None
    except Exception:
        return None
    kinds = info["kinds"]
    servers = info.get("servers") or {}
    one_server = len(set(servers.values()) | {info["server"]}) == 1
    H = 900 + 190 * len(kinds)
    img = Image.new("RGB", (A_W, H), A_GROUND)
    d = ImageDraw.Draw(img)
    R = A_W - 70  # right edge of the content
    L = 70

    def rtl(x_right, y, text, f, fill):
        d.text((x_right - d.textlength(text, font=f), y), text, font=f, fill=fill)

    def center(y, text, f, fill):
        d.text(((A_W - d.textlength(text, font=f)) / 2, y), text, font=f, fill=fill)

    # header
    # Android and Tifusi side by side, each with its name under it
    base = 190  # the logos' common bottom line
    f_name = a_font("Bold", 34)
    for cx, name in ((A_W // 2 - 220, "Android"), (A_W // 2 + 220, "Tifusi")):
        if name == "Android":
            a_droid(d, cx, base - 88, 88)  # same height as the Tifusi mark
        else:
            try:
                mark = Image.open(os.path.join(ASSET_DIR, "tifusi-mark.png")).convert("RGBA")
                mark = mark.resize((int(mark.width * 1.45), int(mark.height * 1.45)), Image.LANCZOS)
                img.paste(mark, (cx - mark.width // 2, base - mark.height), mark)
            except OSError:
                pass
        d.text((cx - d.textlength(name, font=f_name) / 2, base + 14), name, font=f_name,
               fill=A_DROID if name == "Android" else A_TEXT)
    d.line([A_W // 2, base - 90, A_W // 2, base + 50], fill=A_EDGE, width=2)
    center(base + 88, "اتصال در اندروید", a_font("Bold", 46), A_TEXT)
    center(base + 156, "تنظیمات  ‹  VPN  ‹  افزودن", a_font("Regular", 32), A_MUTED)

    # server, username and password come from the copy buttons under the photo
    y = base + 220

    # type options
    y += 16
    rtl(R, y, "روی «نوع» بزنید:" if len(kinds) > 1 else "نوع:", a_font("Bold", 36), A_TEXT)
    y += 66
    cond = {0: "اگر در لیست هست", 1: "اگر نبود", 2: "اگر وصل نشد"}
    for i, k in enumerate(kinds):
        tint = A_TINT[k]
        box = [L, y, R, y + 164]
        d.rounded_rectangle(box, radius=26, fill=A_PANEL, outline=tint, width=3)
        # number disc on the right
        cx, cy = R - 58, y + 58
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=tint)
        n = "123"[i]
        fn = a_font("Bold", 34)
        d.text((cx - d.textlength(n, font=fn) / 2, cy - 26), n, font=fn, fill=A_GROUND)
        if len(kinds) > 1:
            rtl(R - 108, y + 30, ("pptp" in k and i > 0 and cond[2]) or cond[min(i, 1)], a_font("Regular", 30), A_MUTED)
        # the type name, exactly as the phone writes it
        ft = a_fit(d, A_TYPE[k], lambda s: ImageFont.truetype(MONO, s) if os.path.exists(MONO) else a_font("Bold", s), 40, R - L - 340)
        d.text((L + 30, y + 26), A_TYPE[k], font=ft, fill=tint)
        # second line: the one extra field this type needs
        f_d = a_font("Regular", 30)
        if k == "ikev2":
            label, value = "شناسه‌ی IPSec:", "همان نام کاربری"
        elif k == "l2tp":
            label, value = "کلید IPSec:", info.get("psk") or "-"
        else:
            label, value = "رمزگذاری MPPE:", "روشن"
        rtl(R - 108, y + 96, label, f_d, A_MUTED)
        lw = d.textlength(label, font=f_d)
        if k == "l2tp":
            fv = a_fit(d, value, a_mono, 36, R - 108 - lw - 30 - L - 30)
            d.text((R - 108 - lw - 24 - d.textlength(value, font=fv), y + 98), value, font=fv, fill=A_TEXT)
        else:
            rtl(R - 108 - lw - 16, y + 96, value, a_font("Bold", 30), A_TEXT)
        y += 190

    # footer
    y += 6
    center(y, "ذخیره  ‹  روی VPN بزنید  ‹  اتصال", a_font("Bold", 34), A_TEXT)
    y += 70
    # pointing down at the copy buttons under the photo
    hint = "هر مقدار را با دکمه‌های زیر کپی کنید"
    f_h = a_font("Bold", 30)
    pw = d.textlength(hint, font=f_h) + 100
    px = (A_W - pw) / 2
    d.rounded_rectangle([px, y, px + pw, y + 62], radius=31, fill=A_DROID)
    ax = px + 40
    d.polygon([(ax - 13, y + 24), (ax + 13, y + 24), (ax, y + 40)], fill="#0b3b20")
    d.text((px + 66, y + 10), hint, font=f_h, fill="#0b3b20")
    y += 62

    img = img.crop((0, 0, A_W, min(H, y + 50)))
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


# ---------- عکس راهنما: فرم «افزودن VPN» اندروید با مقدارهای خود مشتری ----------
G_GROUND, G_PHONE, G_EDGE, G_HAIR = "#0a0a0a", "#121212", "#2a2a2a", "#222222"
G_TEXT, G_MUTED, G_DIM = "#f5f5f5", "#8b8b8b", "#5c5c5c"
G_DROID = "#3ddc84"  # Android green
G_TINT = {"ikev2": "#2fd26f", "l2tp": "#ff4d4f", "pptp": "#e8eaed"}

G_W, G_H = 900, 1560


def _gfont(name, size):
    from PIL import ImageFont
    return ImageFont.truetype(os.path.join(ASSET_DIR, f"Vazirmatn-{name}.ttf"), size)


def _grtl(draw, x_right, y, text, f, fill):
    """Right-aligned text whose right edge sits at x_right."""
    w = draw.textlength(text, font=f)
    draw.text((x_right - w, y), text, font=f, fill=fill)


def _gdroid(draw, cx, top, s, color=G_DROID):
    """The Android robot's head: a half disc with eyes and two antennae."""
    r = s
    draw.pieslice([cx - r, top, cx + r, top + 2 * r], 180, 360, fill=color)
    ey = top + int(r * 0.55)
    for dx in (-0.42, 0.42):
        ex = cx + int(r * dx)
        draw.ellipse([ex - r * 0.1, ey - r * 0.1, ex + r * 0.1, ey + r * 0.1], fill=G_GROUND)
    for side in (-1, 1):
        x0 = cx + side * int(r * 0.5)
        y0 = top + int(r * 0.12)
        draw.line([x0, y0, x0 + side * int(r * 0.28), y0 - int(r * 0.42)], fill=color, width=max(3, s // 10))


def guide_png(kind, cfg):
    """Picture of Android's Add-VPN form filled with this customer's values; None without libraqm
    (Persian would come out unjoined), and the caller then sends the text guide alone."""
    try:
        from PIL import Image, ImageDraw, features
        if not features.check("raqm"):
            return None
    except Exception:
        return None
    if kind == "which":
        return _which_png()
    tint = G_TINT[kind]
    img = Image.new("RGB", (G_W, G_H), G_GROUND)
    d = ImageDraw.Draw(img)
    f_title, f_sub = _gfont("Bold", 40), _gfont("Regular", 27)
    f_lab, f_val, f_small = _gfont("Regular", 25), _gfont("Bold", 31), _gfont("Regular", 24)

    # header: robot + title
    _gdroid(d, G_W // 2, 52, 46)
    title = {"ikev2": "اندروید ۱۱ به بعد · IKEv2", "l2tp": "اندروید قدیمی · L2TP", "pptp": "گوشی خیلی قدیمی · PPTP"}[kind]
    tw = d.textlength(title, font=f_title)
    d.text(((G_W - tw) / 2, 112), title, font=f_title, fill=G_TEXT)
    sub = "تنظیمات  ‹  VPN  ‹  افزودن"
    sw = d.textlength(sub, font=f_sub)
    d.text(((G_W - sw) / 2, 170), sub, font=f_sub, fill=G_MUTED)

    # phone
    px0, py0, px1, py1 = 70, 236, G_W - 70, G_H - 96
    d.rounded_rectangle([px0, py0, px1, py1], radius=58, fill=G_PHONE, outline=G_EDGE, width=6)
    d.rounded_rectangle([G_W // 2 - 60, py0 + 20, G_W // 2 + 60, py0 + 32], radius=6, fill=G_EDGE)
    xr, xl = px1 - 52, px0 + 52
    _grtl(d, xr, py0 + 58, "ویرایش شبکه VPN", _gfont("Bold", 34), G_TEXT)

    rows = {
        "ikev2": [("نام", "Tifusi"), ("نوع", "IKEv2/IPSec MSCHAPv2", "pick"), ("آدرس سرور", cfg["server"]),
                  ("شناسه IPSec", cfg["username"]), ("گواهی IPSec CA", "استفاده از گواهی‌های سیستم"),
                  ("مجوز سرور IPSec", "از سرور دریافت شود"), ("نام کاربری", cfg["username"]), ("رمز عبور", cfg["password"])],
        "l2tp": [("نام", "Tifusi"), ("نوع", "L2TP/IPSec PSK", "pick"), ("آدرس سرور", cfg["server"]),
                 ("کلید از پیش مشترک IPSec", cfg.get("psk") or "-"), ("شناسه IPSec", "خالی بماند", "blank"),
                 ("رمز L2TP", "خالی بماند", "blank"), ("نام کاربری", cfg["username"]), ("رمز عبور", cfg["password"])],
        "pptp": [("نام", "Tifusi"), ("نوع", "PPTP", "pick"), ("آدرس سرور", cfg["server"]),
                 ("رمزگذاری PPP (MPPE)", "روشن", "check"), ("نام کاربری", cfg["username"]), ("رمز عبور", cfg["password"])],
    }[kind]

    y = py0 + 128
    gap = (py1 - 150 - y) / len(rows)
    for label, value, *flag in rows:
        flag = flag[0] if flag else ""
        _grtl(d, xr, y, label, f_lab, G_MUTED)
        vy = y + 36
        if flag == "pick":
            d.rounded_rectangle([xl, vy - 6, xr, vy + 46], radius=12, fill="#13261c" if kind == "ikev2" else "#2a1414" if kind == "l2tp" else "#1c1c1c", outline=tint, width=3)
            _grtl(d, xr - 18, vy, value, f_val, tint)
            d.polygon([(xl + 22, vy + 14), (xl + 44, vy + 14), (xl + 33, vy + 28)], fill=tint)
        elif flag == "blank":
            _grtl(d, xr, vy, value, f_val, G_DIM)
        elif flag == "check":
            d.rounded_rectangle([xr - 40, vy + 4, xr, vy + 44], radius=8, fill=tint)
            d.line([xr - 32, vy + 24, xr - 22, vy + 34, xr - 8, vy + 14], fill=G_GROUND, width=5)
            _grtl(d, xr - 54, vy, value, f_val, G_TEXT)
        else:
            _grtl(d, xr, vy, value, f_val, G_TEXT)
        d.line([xl, y + gap - 14, xr, y + gap - 14], fill=G_HAIR, width=2)
        y += gap

    # buttons at the bottom of the form
    by = py1 - 104
    d.rounded_rectangle([xl, by, G_W // 2 - 14, by + 64], radius=32, fill=tint)
    sv = "ذخیره"
    d.text(((xl + G_W // 2 - 14) / 2 - d.textlength(sv, font=_gfont("Bold", 30)) / 2, by + 12), sv, font=_gfont("Bold", 30), fill=G_GROUND)
    d.rounded_rectangle([G_W // 2 + 14, by, xr, by + 64], radius=32, outline=G_EDGE, width=3)
    cn = "لغو"
    d.text(((G_W // 2 + 14 + xr) / 2 - d.textlength(cn, font=f_val) / 2, by + 12), cn, font=f_val, fill=G_MUTED)

    foot = "روی مقدارهای پیام ربات بزنید کپی می‌شوند · Tifusi"
    fw = d.textlength(foot, font=f_small)
    d.text(((G_W - fw) / 2, G_H - 70), foot, font=f_small, fill=G_DIM)

    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()

def _which_png():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (G_W, 1180), G_GROUND)
    d = ImageDraw.Draw(img)
    _gdroid(d, G_W // 2, 52, 46)
    t = "کدام را بزنم؟"
    d.text(((G_W - d.textlength(t, font=_gfont("Bold", 44))) / 2, 110), t, font=_gfont("Bold", 44), fill=G_TEXT)
    s = "تنظیمات  ‹  VPN  ‹  افزودن  ‹  روی «نوع» بزنید"
    d.text(((G_W - d.textlength(s, font=_gfont("Regular", 26))) / 2, 172), s, font=_gfont("Regular", 26), fill=G_MUTED)
    px0, py0, px1, py1 = 70, 236, G_W - 70, 1100
    d.rounded_rectangle([px0, py0, px1, py1], radius=58, fill=G_PHONE, outline=G_EDGE, width=6)
    xr, xl = px1 - 52, px0 + 52
    _grtl(d, xr, py0 + 52, "نوع", _gfont("Regular", 28), G_MUTED)
    rows = [("IKEv2/IPSec MSCHAPv2", "دکمه‌ی «اندروید جدید»", G_TINT["ikev2"]),
            ("IKEv2/IPSec PSK", "به کار ما نمی‌آید", None),
            ("IKEv2/IPSec RSA", "به کار ما نمی‌آید", None),
            ("L2TP/IPSec PSK", "دکمه‌ی «اندروید قدیمی»", G_TINT["l2tp"]),
            ("PPTP", "اگر هیچ‌کدام وصل نشد", G_TINT["pptp"])]
    y = py0 + 112
    for name, hint, color in rows:
        if color:
            d.rounded_rectangle([xl, y, xr, y + 118], radius=16, outline=color, width=3)
        d.text((xl + 24, y + 16), name, font=_gfont("Bold", 33), fill=color or G_DIM)
        if not color:
            w = d.textlength(name, font=_gfont("Bold", 33))
            d.line([xl + 24, y + 38, xl + 24 + w, y + 38], fill=G_DIM, width=3)
        _grtl(d, xr - 24, y + 66, hint, _gfont("Regular", 26), G_TEXT if color else G_DIM)
        y += 140
    foot = "اول بالایی را امتحان کنید؛ نبود، پایینی"
    d.text(((G_W - d.textlength(foot, font=_gfont("Regular", 24))) / 2, 1120), foot, font=_gfont("Regular", 24), fill=G_DIM)
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)
    return out.getvalue()


def delivery_details_html(order, panel, links):
    """بعد از بارکد: اطلاعات ورود دستی IKEv2/L2TP (اندروید با خود تنظیمات گوشی وصل می‌شود)، پروفایل
    آیفون و برای Xray لینک اشتراک. رمز از خود پنل خوانده می‌شود نه از سفارش، تا همیشه همانی باشد
    که نود واقعاً چک می‌کند."""
    esc = html.escape
    parts = []
    manual = ipsec_manual_lines(links, order)
    if manual:
        parts.append("🔧 <b>اطلاعات اتصال</b> (برای اندروید و ویندوز):\n" + "\n".join(manual))
        parts.append("📖 آموزش وارد کردن: منوی «آموزش اتصال» ربات")
    apple_url = apple_profile_url(order, links)
    if apple_url:
        parts.append(f"🍎 نصب پروفایل آیفون:\n{esc(apple_url)}")
    if order["protocol"] not in IPSEC_SERVICES and order["sub_url"]:
        parts.append(f"🔗 لینک اشتراک:\n<code>{esc(order['sub_url'])}</code>")
    return "\n\n".join(parts)


async def deliver_service(context, chat_id, order, panel):
    """تحویل سرویس: کارتی با نشان و بارکد، نام و حجم و انقضا در کپشن و زیرش دکمه‌های واقعی
    (نصب پروفایل آیفون، کپی لینک اشتراک)، بعد پیام اطلاعات اتصال. اگر کارت ساخته نشد، همان
    تحویل متنی قبلی (خلاصه، بارکد، جزئیات) فرستاده می‌شود."""
    dt = datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d")
    summary = f"✅ {service_name(order['protocol'])} — {vol_text(order['volume_gb'])} — تا {dt}"
    notify_group(context.bot,
                 f"{'🛍 خرید جدید' if order['price'] else '🎁 اکانت تست'}\n👤 {who(order['user_id'])}\n"
                 f"🧩 {service_name(order['protocol'])} — {vol_text(order['volume_gb'])} — {order['days']} روز\n"
                 f"🔖 {order['username']} | 💰 {fmt(order['price'])} تومان", topic="sales")
    links = None
    if order["protocol"] in IPSEC_SERVICES:
        try:
            links = await asyncio.to_thread(panel_client(panel).links, order["username"])
        except PanelError as e:
            log.warning("fetching IPsec details for %s failed: %s", order["username"], e)

    details = delivery_details_html(order, panel, links)
    apple_url = apple_profile_url(order, links)
    card = await asyncio.to_thread(delivery_card_png, order)
    if card:
        # داخل تصویر فقط نشان و بارکد است: تلگرام هیچ نقطه‌ای از یک عکس را قابل لمس نمی‌کند،
        # پس نام و حجم و انقضا در کپشن و بقیه روی دکمه‌های واقعی زیر عکس می‌نشینند.
        caption = (f"✅ <b>{html.escape(order['username'])}</b> — {html.escape(service_name(order['protocol']))}\n"
                   f"📦 حجم: {html.escape(vol_text(order['volume_gb']))}\n"
                   f"📅 انقضا: {dt}")
        rows = []
        guide = order["protocol"] in ("ikev2", "l2tp", "pptp")
        if guide:
            # The picture carries everything: «active», name, service, volume, expiry and what to tap.
            caption = None
            gb = guide_button(order)
            if gb:
                rows.append([gb])
            rows.append([InlineKeyboardButton(ANDROID_BTN, callback_data=f"andr:{order['id']}")])
        if apple_url:
            # U+F8FF روی آیفون و مک همان ارم اپل است — دقیقاً همان دستگاه‌هایی که این دکمه برایشان است.
            rows.append([InlineKeyboardButton(" نصب پروفایل آیفون و مک", url=apple_url)])
        # لینک اشتراک فعلاً فقط برای Xray (سرویس‌های گوشی با تنظیمات خود گوشی وصل می‌شوند)
        copy_btn = copy_text_button("🔗 کپی لینک اشتراک", order["sub_url"]) if order["sub_url"] and not guide else None
        if copy_btn:
            rows.append([copy_btn])
        try:
            await context.bot.send_photo(chat_id, card, caption=caption, parse_mode="HTML",
                                         reply_markup=InlineKeyboardMarkup(rows) if rows else None)
            # IKEv2/L2TP: the guide buttons above carry the connection details, one method at a time.
            if details and not guide:
                await context.bot.send_message(chat_id, details, parse_mode="HTML",
                                               disable_web_page_preview=True)
            return
        except Exception as e:
            log.warning("send delivery card failed for %s: %s", chat_id, e)

    await context.bot.send_message(chat_id, summary)
    if order["sub_url"] and not await send_order_qr(context, chat_id, order):
        await context.bot.send_message(chat_id, order["sub_url"])
    if details:
        await context.bot.send_message(chat_id, details, parse_mode="HTML", disable_web_page_preview=True)


# ---------- تمدید ----------
def do_renew(order, plan):
    """تمدید روی همان پنل — همان کاربر به‌روز می‌شود تا لینک اشتراک، شناسه و QR عوض نشوند؛
    پروتکل‌های کاربر با هاست‌های فعلی آن سرویس روی پنل هماهنگ می‌شوند و اگر کاربر روی پنل حذف
    شده بود، با همان یوزرنیم و گروه سرویس دوباره ساخته می‌شود."""
    if order["status"] != "active":
        raise PanelError("این سرویس فعال نیست و قابل تمدید نیست؛ لطفاً سرویس جدید بخرید")
    panel = db.get_panel(order["panel_id"])
    if not panel:
        raise PanelError("پنل این سرویس حذف شده است")
    client = panel_client(panel)
    base = max(now(), order["expire_at"])
    expire_at = base + plan["days"] * 86400
    service = order["protocol"]
    protocols = service_access_protocols(panel, service) if service in SERVICES else None
    device_limit = plan_device_limit(plan)
    res = client.renew_user(order["username"], plan["volume_gb"], expire_at, protocols=protocols, device_limit=device_limit)
    if res is None:
        # گروه فعلی سرویس روی پنل؛ اگر ادمین آن را برداشته، همان گروهی که سفارش با آن ساخته شده بود
        grp = db.get_service_map(panel["id"]).get(service)
        gid = int((grp["inbound_id"] if grp else order["inbound_id"]) or 0)
        res = client.add_user([gid] if gid else [], order["username"], plan["volume_gb"], expire_at,
                              protocols=protocols, device_limit=device_limit,
                              ipsec_password=order["password"] or None)
    db.update_order(order["id"], expire_at=expire_at, volume_gb=plan["volume_gb"], days=plan["days"],
                    price=plan["price"], plan_id=plan.get("id", order["plan_id"]) or order["plan_id"],
                    status="active", reminded=0, sub_url=res["subscription_url"], app_code=res["app_code"])
    return db.get_order(order["id"]), panel


# ---------- سرویس‌های من ----------
SERVICES_PAGE = 10  # name buttons per page of «My services»


async def show_services(query, uid, page=0, search=None):
    """One page of name buttons, ten at a time, with next/previous and a quick search by name.
    search: part of a service name (letters, digits, _), from the quick-search prompt."""
    if not search:
        db.set_state(uid, "none")
    everything = db.get_user_orders(uid)
    if not everything:
        await safe_edit(query, "🛍 شما هنوز سرویسی ندارید.", reply_markup=back_kb())
        return
    orders = [o for o in everything if search.lower() in o["username"].lower()] if search else everything
    pages = max(1, -(-len(orders) // SERVICES_PAGE))
    page = max(0, min(page, pages - 1))
    if search:
        text = (f"🔎 نتیجه‌ی جستجوی «{search}»: {len(orders)} سرویس" if orders
                else f"❌ سرویسی با «{search}» پیدا نشد.")
    else:
        text = "🛍 سرویس‌های شما:"
    if pages > 1:
        text += f"\n📄 صفحه {page + 1} از {pages}"
    rows = []
    for o in orders[page * SERVICES_PAGE:(page + 1) * SERVICES_PAGE]:
        status = "" if o["status"] == "active" else " ⏳"
        rows.append([btn(f"✨ {o['username']} ✨{status}", f"svc:{o['id']}")])
    tail = f":{search}" if search else ""
    nav = []
    if page < pages - 1:
        nav.append(btn("بعدی", f"svcp:{page + 1}{tail}"))
    if page > 0:
        nav.append(btn("قبلی", f"svcp:{page - 1}{tail}"))
    if search:
        nav.append(btn("🛍 همه‌ی سرویس‌ها", "menu:services"))
    elif len(everything) > SERVICES_PAGE:
        nav.append(btn("🔎 جستجو سریع", "svcq"))
    if nav:
        rows.append(nav)
    rows.append([btn("🔙 بازگشت به منوی اصلی", "menu:back")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def show_service_detail(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid:
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    panel = db.get_panel(o["panel_id"])
    pname = panel["name"] if panel else "حذف‌شده"

    # لینک و شناسه از پنل خوانده می‌شوند نه از سفارش: اگر آدرس عمومی پنل عوض شده
    # باشد (مثلاً پورت داشبورد تغییر کرده)، مقدار ذخیره‌شده‌ی قدیمی دیگر باز نمی‌شود.
    fresh = None
    if panel:
        try:
            fresh = await asyncio.to_thread(panel_client(panel).links, o["username"])
        except PanelError:
            fresh = None
        if fresh and (fresh["subscription_url"] != o["sub_url"] or fresh["app_code"] != o["app_code"]):
            db.update_order(oid, sub_url=fresh["subscription_url"], app_code=fresh["app_code"])
            o = db.get_order(oid)

    dt = datetime.datetime.fromtimestamp(o["expire_at"]).strftime("%Y-%m-%d — %H:%M")

    # مصرف از همان پنلی که سرویس روی آن ساخته شده
    usage_line = "📊 وضعیت مصرف: در دسترس نیست (پنل پاسخ نمی‌دهد)"
    phone = o["protocol"] in ("ikev2", "l2tp", "pptp")
    used = None
    # سرویس گوشی مصرف را در عکس نشان می‌دهد، حتی برای نامحدود
    if panel and (o["volume_gb"] or phone):
        try:
            used_bytes = await asyncio.to_thread(panel_client(panel).usage, o["username"])
            if used_bytes is not None:
                used = gb(used_bytes)
        except Exception:
            pass
    if not o["volume_gb"]:
        usage_line = "📦 حجم: نامحدود ♾ (بدون محدودیت مصرف)"
    elif used is not None:
        total = o["volume_gb"]
        left = max(0, round(total - used, 2))
        usage_line = f"📊 وضعیت مصرف:\n📦 {total} گیگ | 🔻 {used} گیگ | ✅ {left} گیگ باقی"

    creds = f"👤 یوزرنیم: `{o['username']}`"
    if not phone:
        creds += f"\n🔗 لینک اشتراک: `{o['sub_url'] or '-'}`"
    # رمز و سکرت از خود پنل، تا همیشه همانی باشد که نود واقعاً چک می‌کند
    guide = o["protocol"] in ("ikev2", "l2tp", "pptp")
    manual = [] if guide else ipsec_manual_lines(fresh, o, code=lambda v: f"`{v}`", text=md)
    if manual:
        creds += "\n\n🔧 اطلاعات اتصال (اندروید و ویندوز):\n" + "\n".join(manual)
    elif guide:
        creds += "\n\n👇 برای اتصال، دکمه‌ی گوشی خود را بزنید."
    apple_url = apple_profile_url(o, fresh) if o["protocol"] in IPSEC_SERVICES else None
    text = (f"{md(service_name(o['protocol']))} — #{o['id']}\n"
            f"🖥 پنل: {md(pname)}\n\n{creds}\n\n{usage_line}\n"
            f"⏳ {remaining_text(o['expire_at'])} | 🕓 {dt}")
    rows = []
    if o["status"] == "active":
        if guide:
            gb = guide_button(o)
            if gb:
                rows.append([gb])
            rows.append([btn(ANDROID_BTN, f"andr:{o['id']}")])
        if apple_url:
            rows.append([InlineKeyboardButton(" نصب پروفایل آیفون و مک", url=apple_url)])
        rows.append([btn("♻️ تمدید سرویس", f"renew:{o['id']}")])
        refresh = btn("🔄 بروزرسانی اطلاعات", f"svc:{o['id']}")
        rows.append([btn("📷 QR code", f"qr:{o['id']}"), refresh] if o["sub_url"] and not phone else [refresh])
        rows.append([btn("❌ بازگشت وجه / حذف سرویس", f"delreq:{o['id']}")])
    rows.append([btn("🏠 بازگشت به لیست سرویس‌ها", "menu:services")])
    markup = InlineKeyboardMarkup(rows)
    if phone:
        png = await asyncio.to_thread(service_status_png, o, used)
        if png and await show_status_photo(query, png, o, markup):
            return
    await safe_edit(query, text, reply_markup=markup, parse_mode="Markdown")


STATUS_MARK = "🛍"  # caption start that marks a «My services» picture (safe_edit replaces it with text)


async def show_status_photo(query, png, order, markup):
    """The service picture: switched in place when the message is already a photo (refresh, or back
    from the Android picture), otherwise sent fresh and the text message it replaces deleted.
    False when Telegram refused, so the caller falls back to text."""
    from telegram import InputMediaPhoto
    caption = f"{STATUS_MARK} سرویس #{order['id']} · <code>{html.escape(order['username'])}</code>"
    msg = query.message
    try:
        if msg and msg.photo and not (msg.caption or "").startswith("✅"):
            await query.edit_message_media(InputMediaPhoto(png, caption=caption, parse_mode="HTML"), reply_markup=markup)
        else:
            await msg.reply_photo(png, caption=caption, parse_mode="HTML", reply_markup=markup)
            if msg and not msg.photo:
                try:
                    await msg.delete()
                except Exception:
                    pass
        return True
    except Exception as e:
        if "not modified" in str(e).lower():
            return True
        log.warning("status picture for order %s failed: %s", order["id"], e)
        return False


# ---------- حساب کاربری ----------
def account_text(uid):
    u = db.get_user(uid)
    orders_all = db.get_user_orders(uid, active_only=False)
    active = len([o for o in orders_all if o["status"] == "active"])
    reg = datetime.datetime.fromtimestamp(u["created_at"]).strftime("%Y/%m/%d — %H:%M") if u["created_at"] else "—"
    return (f"🤖 اطلاعات حساب کاربری شما:\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🪪 آیدی عددی: {uid}\n"
            f"👤 نام: {u['full_name'] or '-'}\n"
            f"📱 یوزرنیم: @{u['username'] or '-'}\n"
            f"⌚️ زمان ثبت‌نام: {reg}\n"
            f"💰 موجودی: {fmt(u['balance'])} تومان\n"
            f"🛍 سرویس‌های فعال: {active}\n"
            f"🧾 کل سفارش‌ها: {len(orders_all)}\n"
            f"🤝 زیرمجموعه‌های شما: {db.referral_count(uid)} نفر")


async def show_account_msg(msg, uid):
    kb = InlineKeyboardMarkup([[btn("💰 افزایش موجودی", "wallet:charge"),
                                btn("🏠 بازگشت به منوی اصلی", "menu:back")]])
    await msg.reply_text(account_text(uid), reply_markup=kb)


# ---------- فلوی شارژ کیف پول (مرحله تایید) ----------
def card_charge_text(amount):
    card = db.setting("card_number", "—")
    name = db.setting("card_name", "—")
    return (f"💵 برای افزایش موجودی، مبلغ {fmt(amount)} تومان را به شماره‌حساب زیر واریز کنید 👇\n\n"
            f"====================\n"
            f"{card}\n"
            f"به نام: {name}\n"
            f"====================\n\n"
            f"❌ این تراکنش به مدت یک ساعت اعتبار دارد.\n"
            f"‼️ مبلغ باید دقیقاً همان مبلغ ذکرشده واریز شود.\n"
            f"‼️ امکان برداشت وجه از کیف پول نیست.\n"
            f"‼️ مسئولیت واریز اشتباهی با شماست.\n\n"
            f"⬇️ بعد از پرداخت، روی «✅ ادامه مراحل» بزنید و تصویر رسید را ارسال کنید.")


# ---------- اکانت تست ----------
async def send_test_account(msg, context, uid):
    """هر کاربر فقط یک بار — حجم و مدت از تنظیمات عمومی قابل تغییر است.
    به‌طور پیش‌فرض خاموش است (تنظیم test_enabled) چون از اکانت تست سوءاستفاده می‌شود؛
    وقتی خاموش است هیچ کاربری روی پنل ساخته و هیچ چیزی ثبت نمی‌شود.
    اکانت روی اولین سرویس در دسترس به ترتیب TEST_SERVICE_ORDER ساخته می‌شود."""
    if db.setting("test_enabled", "0") != "1":
        await msg.reply_text("🔑 اکانت تست در حال حاضر فعال نیست.\n🔐 برای استفاده از سرویس، از «خرید اشتراک» اقدام کنید.")
        return
    # سقف اکانت تست هر کاربر (پیش‌فرض ۱) از صفحه‌ی مدیریت کاربر عوض می‌شود
    u = db.get_user(uid)
    limit = int((u["test_limit"] if u and u["test_limit"] is not None else 1))
    if db.one("SELECT COUNT(*) c FROM orders WHERE user_id=? AND price=0", (uid,))["c"] >= limit:
        await msg.reply_text("❌ سهمیه‌ی اکانت تست شما تمام شده است.\n🛍 سرویس‌های قبلی‌ات را از «سرویس‌های من» ببین.")
        return
    service = next((s for s in TEST_SERVICE_ORDER if pick_panel(s)), None)
    if not service:
        await msg.reply_text("❌ فعلاً سرویسی برای ساخت اکانت تست در دسترس نیست. کمی بعد دوباره امتحان کنید.")
        return
    vol = int(db.setting("test_volume_gb", "1") or 1)
    days = int(db.setting("test_days", "1") or 1)
    plan = {"id": 0, "volume_gb": vol, "days": days, "price": 0}
    username = f"t{uid}"
    await msg.reply_text("⏳ در حال ساخت اکانت تست...")
    try:
        order, panel = await asyncio.to_thread(create_service_on_panel, uid, plan, service, username)
    except Exception as e:
        await msg.reply_text(f"❌ خطا در ساخت اکانت تست: {e}")
        return
    await deliver_service(context, uid, order, panel)
    await notify_admin(context.bot, f"🔑 اکانت تست ساخته شد\n👤 کاربر: {uid}\n"
                                    f"🧩 سرویس: {SERVICES[service]}\n🖥 پنل: {panel['name']}")


# ---------- منوی تمدید ----------
async def show_renew_menu(msg, uid):
    renewable = [o for o in db.get_user_orders(uid) if o["status"] == "active"]
    if not renewable:
        await msg.reply_text("❌ سرویس فعالی برای تمدید ندارید.\nاول از «🔐 خرید اشتراک» سرویس بخر.")
        return
    rows = [[btn(f"♻️ {o['username']} — {vol_text(o['volume_gb'])}", f"renew:{o['id']}")] for o in renewable]
    await msg.reply_text(f"♻️ تمدید سرویس\n\nکدام سرویس را تمدید می‌کنی؟",
                         reply_markup=InlineKeyboardMarkup(rows))


# ---------- پرداخت ----------
def pay_kb():
    return InlineKeyboardMarkup([
        [btn("🏦 پرداخت از کیف پول", "pay:wallet")],
        [btn("💳 کارت به کارت", "pay:card"), btn("❌ بستن لیست", "menu:buy")],
    ])


def password_prompt_text(service):
    return (f"🔑 رمز عبور {SERVICES[service]}\n\n"
            f"یک رمز دلخواه ارسال کنید، یا «🎲 رمز تصادفی» را بزنید.\n\n"
            f"⚠️ {IPSEC_PASSWORD_RULES}")


def password_prompt_kb(service):
    return InlineKeyboardMarkup([[btn("🎲 رمز تصادفی", "bpw:random")],
                                 [btn("🔙 بازگشت", f"proto:{service}")]])


def invoice_text(sd, plan):
    """پیش‌فاکتور خرید (Markdown)؛ برای IKEv2/L2TP رمز انتخاب‌شده هم نشان داده می‌شود."""
    service = sd["protocol"]
    text = (f"🧾 پیش‌فاکتور\n"
            f"📦 {md(plan_label(plan))}\n"
            f"🧩 سرویس: {SERVICES[service]}\n👤 یوزرنیم: `{sd['username']}`\n")
    if sd.get("ipsec_password"):
        text += f"🔑 رمز عبور: `{sd['ipsec_password']}`\n"
    text += f"💰 مبلغ: {fmt(plan['price'])} تومان\n\n"
    if not sd.get("ipsec_password"):
        text += "🔑 رمز لازم نیست؛ بعد از ساخت سرویس، شناسه، لینک اشتراک و QR برایتان ارسال می‌شود.\n"
    text += "⚠️ سرویس فقط بعد از پرداخت و تایید، ساخته و فعال می‌شود.\n\nروش پرداخت:"
    return text


def card_info_text(amount):
    card = db.setting("card_number", "—")
    name = db.setting("card_name", "—")
    return (f"💳 مبلغ {fmt(amount)} تومان را به کارت زیر واریز کنید و سپس **عکس رسید** را ارسال کنید:\n\n"
            f"🏦 شماره کارت: {card}\n👤 صاحب حساب: {name}\n\n"
            f"⏳ بعد از تایید ادمین، سفارش انجام می‌شود.")


# خرید نیمه‌کاره: وقتی موجودی کم است، اطلاعات خرید نگه داشته می‌شود تا بعد از شارژ کیف پول
# کاربر با یک دکمه ادامه بدهد (مرحله‌ی شارژ، جلسه‌ی خرید را پاک می‌کند)
PENDING_BUY_TTL = 24 * 3600


def save_pending_buy(uid, data):
    keep = {k: data.get(k) for k in ("plan_id", "protocol", "username", "panel_id", "ipsec_password")}
    db.set_setting(f"pending_buy:{uid}", json.dumps({**keep, "saved_at": now()}))


def load_pending_buy(uid):
    try:
        data = json.loads(db.setting(f"pending_buy:{uid}") or "null")
    except ValueError:
        return None
    if not data or now() - data.get("saved_at", 0) > PENDING_BUY_TTL:
        return None
    return data


def clear_pending_buy(uid):
    if db.setting(f"pending_buy:{uid}"):
        db.set_setting(f"pending_buy:{uid}", "")


async def offer_pending_buy(bot, uid):
    """بعد از شارژ کیف پول: اگر خرید نیمه‌کاره‌ای هست، پیشنهاد ادامه‌اش را بفرست."""
    data = load_pending_buy(uid)
    plan = user_plan(data["plan_id"], uid) if data else None
    if not plan or not plan["active"]:
        clear_pending_buy(uid)
        return
    bal = db.get_balance(uid)
    text = (f"🛒 خرید نیمه‌کاره‌ی شما آماده است\n\n"
            f"📦 {plan_label(plan)}\n🧩 سرویس: {SERVICES.get(data['protocol'], data['protocol'])}\n"
            f"👤 یوزرنیم: {data['username']}\n💰 مبلغ: {fmt(plan['price'])} تومان\n"
            f"💎 موجودی شما: {fmt(bal)} تومان")
    if bal >= plan["price"]:
        kb = [[btn("✅ تکمیل خرید", "resume:buy")], [btn("❌ لغو این خرید", "resume:cancel")]]
    else:
        text += f"\n\n⚠️ هنوز {fmt(plan['price'] - bal)} تومان کم دارید."
        kb = [[btn("➕ شارژ کیف پول", "wallet:charge")], [btn("❌ لغو این خرید", "resume:cancel")]]
    try:
        await bot.send_message(uid, text, reply_markup=InlineKeyboardMarkup(kb))
    except Exception as e:
        log.warning("offer_pending_buy %s failed: %s", uid, e)


async def finalize_wallet_purchase(query, context, uid, data):
    plan = user_plan(data["plan_id"], uid)
    if not plan:
        await safe_edit(query, "❌ پلن یافت نشد.", reply_markup=back_kb())
        return
    bal_before = db.get_balance(uid)
    if not db.try_spend(uid, plan["price"]):
        save_pending_buy(uid, data)
        await safe_edit(query,
            f"❌ موجودی کیف پول کافی نیست.\n\n"
            f"💸 مبلغ پلن: {fmt(plan['price'])} تومان\n"
            f"💎 موجودی شما: {fmt(bal_before)} تومان\n"
            f"➕ کمبود: {fmt(plan['price'] - bal_before)} تومان\n\n"
            f"✅ خریدتان ذخیره شد؛ بعد از شارژ کیف پول، با یک دکمه ادامه می‌دهید و لازم نیست از اول شروع کنید.",
            reply_markup=InlineKeyboardMarkup([[btn("➕ شارژ کیف پول", "wallet:charge")],
                                               [btn("🔙 بازگشت", "menu:back")]]))
        return
    clear_pending_buy(uid)
    # جلسه‌ی خرید همین‌جا بسته می‌شود تا زدن دوباره‌ی دکمه‌ی پرداخت سرویس دوم نسازد
    db.set_state(uid, "none")
    await safe_edit(query, "♻️ در حال ساخت سرویس... لطفاً چند ثانیه صبر کنید.")
    try:
        order, panel = await asyncio.to_thread(
            create_service_on_panel, uid, plan, data["protocol"], data["username"], data.get("panel_id"),
            data.get("ipsec_password"))
    except Exception as e:
        db.add_balance(uid, plan["price"])  # بازگشت وجه
        await context.bot.send_message(uid, f"❌ خطا در ساخت سرویس: {e}\n💰 مبلغ به کیف پول برگشت.")
        return
    await deliver_service(context, uid, order, panel)
    await context.bot.send_message(uid,
        f"🧾 رسید خرید\n\n"
        f"💰 موجودی قبل از خرید: {fmt(bal_before)} تومان\n"
        f"💸 مبلغ خرید: {fmt(plan['price'])} تومان\n"
        f"💎 موجودی فعلی: {fmt(db.get_balance(uid))} تومان")
    await notify_admin(context.bot,
        f"🛍 خرید جدید (کیف پول)\n👤 {uid}\n📦 {plan_label(plan)}\n"
        f"🖥 پنل: {panel['name']}")


# ---------- تمدید ----------
async def renew_menu(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid or o["status"] != "active":
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    plans = db.get_plans(active_only=True, service=o["protocol"])
    text = (f"♻️ تمدید / ارتقای سرویس «{o['username']}»\n"
            f"━━━━━━━━━━━━━━━\n"
            f"پلن فعلی: {vol_text(o['volume_gb'])} — {o['days']} روز\n\n"
            f"پلن جدید را انتخاب کن (می‌توانی ارتقا بدهی 👆):")
    rows = []
    for p in plans:
        cur = " ◀️ پلن فعلی" if p["id"] == o["plan_id"] else ""
        rows.append([btn(f"🛍️ {plan_label(p)}{cur}", f"rpl:{oid}:{p['id']}")])
    rows.append([btn("🔙 بازگشت", f"svc:{oid}")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def renew_pay_menu(query, uid, oid, pid):
    o = db.get_order(oid)
    plan = user_plan(pid, uid)
    if not o or not plan or o["user_id"] != uid or not plan_fits(plan, o["protocol"]):
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    kb = InlineKeyboardMarkup([
        [btn("🏦 پرداخت از کیف پول", f"rnw:w:{oid}:{pid}")],
        [btn("💳 کارت به کارت", f"rnw:c:{oid}:{pid}"), btn("🔙 بازگشت", f"renew:{oid}")],
    ])
    await safe_edit(query,
        f"♻️ تمدید سرویس «{o['username']}»\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 پلن جدید: {plan_label(plan)}\n"
        f"💰 مبلغ: {fmt(plan['price'])} تومان\n\n"
        f"✅ یوزرنیم، شناسه، لینک اشتراک و QR ثابت می‌مانند.\nروش پرداخت را انتخاب کن:",
        reply_markup=kb)


async def do_renew_and_deliver(query, context, uid, oid, plan_id=None):
    o = db.get_order(oid)
    p = user_plan(plan_id or o["plan_id"], o["user_id"])
    plan = dict(p) if p else {"id": o["plan_id"], "volume_gb": o["volume_gb"], "days": o["days"], "price": o["price"], "user_limit": None}
    # فقط شکستِ خودِ تمدید خطا برمی‌گرداند (و باعث بازگشت وجه می‌شود)؛ اگر تمدید انجام شد ولی پیام نرسید،
    # نباید پول برگردد چون سرویس تمدید شده است.
    new_o, panel = await asyncio.to_thread(do_renew, o, plan)
    notify_group(context.bot,
                 f"♻️ تمدید سرویس\n👤 {who(new_o['user_id'])}\n🔖 {new_o['username']} — "
                 f"{vol_text(new_o['volume_gb'])} — {new_o['days']} روز | 💰 {fmt(plan['price'])} تومان", topic="sales")
    dt = datetime.datetime.fromtimestamp(new_o["expire_at"]).strftime("%Y-%m-%d %H:%M")
    try:
        await context.bot.send_message(uid,
            f"✅ سرویس `{new_o['username']}` تمدید شد!\n\n"
            f"📦 پلن جدید: {vol_text(new_o['volume_gb'])} — {new_o['days']} روز\n"
            f"👤 یوزرنیم: `{new_o['username']}`\n"
            f"🔗 لینک اشتراک: `{new_o['sub_url'] or '-'}`\n"
            f"⏳ اعتبار جدید: تا {dt}",
            parse_mode="Markdown")
    except Exception as e:
        log.warning("renew message to %s failed: %s", uid, e)


# ---------- درخواست حذف ----------
async def delreq_confirm(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid:
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    if o["status"] != "active":
        await safe_edit(query, "❌ این سرویس قبلاً درخواست حذف دارد یا فعال نیست.", reply_markup=back_kb())
        return
    kb = InlineKeyboardMarkup([
        [btn("✅ بله، حذف شود", f"delreq:yes:{oid}")],
        [btn("❌ انصراف", f"svc:{oid}")],
    ])
    await safe_edit(query,
        f"🗑 درخواست حذف سرویس {o['username']}\n\n"
        f"پس از تایید ادمین، سرویس از پنل حذف و مبلغ باقی‌مانده به کیف پول شما برمی‌گردد.\nمطمئنید؟",
        reply_markup=kb)


def receipt_admin_kb(rid):
    return InlineKeyboardMarkup([
        [btn("✅ تایید پرداخت", f"rc:ok:{rid}")],
        [btn("❌ رد پرداخت", f"rc:no:{rid}"), btn("⭕️ شارژ دستی", f"rc:manual:{rid}")],
        [btn("⭕️ بلاک کردن کاربر", f"rc:block:{rid}")],
    ])


def receipt_caption(r, title):
    u = db.get_user(r["user_id"])
    uname = f"@{u['username']}" if u and u["username"] else str(r["user_id"])
    return (f"⭕️ {title} — رسید #{r['id']}\n\n"
            f"👤 شناسه کاربر: {r['user_id']}\n"
            f"⚜️ نام کاربری: {uname}\n"
            f"💸 مبلغ پرداختی: {fmt(r['amount'])} تومان\n"
            f"💎 موجودی فعلی کاربر: {fmt(u['balance']) if u else 0} تومان\n"
            f"🛒 کد پیگیری: R{r['id']}")


# =================== پنل مدیریت ===================
async def admin_stats(query):
    t = db.totals()
    day = db.stats_since(now() - 86400)
    week = db.stats_since(now() - 7 * 86400)
    month = db.stats_since(now() - 30 * 86400)
    one = lambda sql: db.one(sql)["c"]
    blocked = one("SELECT COUNT(*) c FROM users WHERE is_blocked=1")
    wallets = one("SELECT COALESCE(SUM(balance),0) c FROM users")
    vol_sold = one("SELECT COALESCE(SUM(volume_gb),0) c FROM orders")
    refs = one("SELECT COUNT(*) c FROM users WHERE referred_by IS NOT NULL")
    tests = one("SELECT COUNT(*) c FROM orders WHERE price=0")
    rc_ok = one("SELECT COUNT(*) c FROM receipts WHERE status='approved'")
    rc_no = one("SELECT COUNT(*) c FROM receipts WHERE status='rejected'")
    tk_closed = one("SELECT COUNT(*) c FROM tickets WHERE status='closed'")
    panels = db.get_panels()
    by = lambda st: len([p for p in panels if p["status"] == st])
    period = lambda name, x: f"{name}: 👤 {x['new_users']}  ·  🛍 {x['new_orders']}  ·  💰 <b>{fmt(x['revenue'])}</b>"
    text = card("📊 آمار ربات",
        ["👥 <b>کاربران</b>",
         f"کل کاربران: <b>{t['users']}</b>",
         f"عضو با دعوت: <b>{refs}</b>  ·  مسدود: <b>{blocked}</b>",
         f"موجودی کیف پول‌ها: <b>{fmt(wallets)}</b> تومان"],
        ["🛍 <b>فروش</b>",
         f"سرویس فعال: <b>{t['active']}</b> از <b>{t['orders']}</b> سفارش",
         f"اکانت تست: <b>{tests}</b>  ·  حجم فروخته‌شده: <b>{fmt(vol_sold)}</b> گیگ",
         f"درآمد کل: <b>{fmt(t['revenue'])}</b> تومان"],
        ["📅 <b>بازه‌ها</b>  (کاربر جدید · سفارش · درآمد)",
         period("۲۴ ساعت", day), period("۷ روز", week), period("۳۰ روز", month)],
        ["🖥 <b>پنل‌ها و پشتیبانی</b>",
         f"پنل: 🟢 {by('active')}  ·  🔴 {by('offline')}  ·  ⚪ {by('inactive')}",
         f"رسید: ⏳ {t['pending_receipts']}  ·  ✅ {rc_ok}  ·  ❌ {rc_no}",
         f"تیکت: 📬 باز {t['tickets_open']}  ·  📪 بسته {tk_closed}"])
    await page(query, text, [back_row()])


async def admin_delete_requests(query):
    """درخواست‌های حذفی که هنوز بررسی نشده‌اند. تا پیش از این، دکمه‌های تایید/رد فقط
    روی همان پیام اعلان ادمین بودند؛ با پاک شدن آن چت، سفارش برای همیشه در حالت
    «درخواست حذف» می‌ماند — نه تمدید می‌شود و نه دوباره می‌شود درخواست داد."""
    orders = db.pending_delete_requests()
    if not orders:
        await page(query, card("🗑 درخواست‌های حذف", ["✅ درخواست بررسی‌نشده‌ای وجود ندارد."]), [back_row("admin:g:users")])
        return
    rows = []
    blocks = []
    for o in orders:
        blocks.append([f"<b>#{o['id']}</b>  ·  {h(o['username'])}",
                       f"🧩 {h(service_name(o['protocol']))}  ·  👤 <code>{o['user_id']}</code>"])
        rows.append([btn(f"❌ رد #{o['id']}", f"dq:no:{o['id']}"), btn(f"✅ حذف #{o['id']}", f"dq:ok:{o['id']}")])
    rows.append(back_row("admin:g:users"))
    await page(query, card(f"🗑 درخواست‌های حذف ({len(orders)})", *blocks), rows)


async def admin_receipts(query):
    receipts = db.pending_receipts()
    if not receipts:
        await page(query, card("💵 رسیدهای تایید نشده", ["✅ رسید در انتظاری وجود ندارد."]), [back_row()])
        return
    names = {"wallet_charge": "➕ شارژ کیف پول", "purchase": "🛍 خرید سرویس", "renew": "♻️ تمدید"}
    rows = []
    lines = []
    for r in receipts:
        kind = names.get(r["rtype"], r["rtype"])
        lines.append(f"<b>#{r['id']}</b>  ·  {kind}  ·  <b>{fmt(r['amount'])}</b> تومان  ·  👤 <code>{r['user_id']}</code>")
        rows.append([btn(f"#{r['id']}  ·  {kind}  ·  {fmt(r['amount'])}", f"rc:{r['id']}")])
    rows.append(back_row())
    await page(query, card(f"💵 رسیدهای تایید نشده ({len(receipts)})", lines, note="برای بررسی روی رسید بزنید."), rows)


async def admin_receipt_detail(query, rid):
    r = db.get_receipt(rid)
    if not r:
        await safe_edit(query, "❌ رسید یافت نشد.")
        return
    kb = receipt_admin_kb(rid)
    caption = receipt_caption(r, f"نوع: {r['rtype']} | وضعیت: {r['status']}")
    try:
        await query.message.delete()
    except Exception:
        pass
    await query.message.reply_photo(r["photo_id"], caption=caption, reply_markup=kb)


async def rc_approve(query, context, rid):
    r = db.get_receipt(rid)
    if not r or r["status"] != "pending":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer("⚠️ این تراکنش قبلاً توسط یک ادمین دیگر بررسی و بسته شده است.", show_alert=True)
        return
    db.set_receipt_status(rid, "approved")
    await close_receipt_for_others(context.bot, rid, query.message.chat_id,
                                   "✅ این تراکنش توسط یک ادمین دیگر تایید شد و بسته شد.")
    meta = json.loads(r["meta"] or "{}")
    try:
        await query.message.delete()
    except Exception:
        pass
    notify_group(context.bot, f"✅ رسید R{rid} تأیید شد\n👤 {who(r['user_id'])} | 💸 {fmt(r['amount'])} تومان", topic="pay")
    if r["rtype"] == "wallet_charge":
        db.add_balance(r["user_id"], r["amount"])
        await context.bot.send_message(r["user_id"],
            f"💎 کاربر گرامی مبلغ {fmt(r['amount'])} تومان به کیف پول شما واریز گردید. با تشکر از پرداخت شما 🙏\n\n"
            f"🛒 کد پیگیری شما: R{r['id']}\n"
            f"💰 موجودی فعلی: {fmt(db.get_balance(r['user_id']))} تومان")
        await offer_pending_buy(context.bot, r["user_id"])
        await query.message.reply_text(f"✅ رسید #{rid} تایید شد — کیف پول کاربر شارژ شد.",
            reply_markup=InlineKeyboardMarkup([[btn("⚙️ مدیریت کاربر", f"au:panel:{r['user_id']}")]]))
    elif r["rtype"] == "purchase":
        plan = db.get_plan(meta.get("plan_id"))
        if not plan:
            await query.message.reply_text("❌ پلن حذف شده؛ وجه را دستی برگردانید.")
            return
        # سفارش با همان مبلغی ثبت می‌شود که کاربر واقعاً پرداخت کرد (با تخفیف شخصی‌اش)
        plan = dict(plan)
        plan["price"] = int(r["amount"])
        try:
            order, panel = await asyncio.to_thread(
                create_service_on_panel, r["user_id"], plan, meta["protocol"], meta["username"], meta.get("panel_id"),
                meta.get("ipsec_password"))
        except Exception as e:
            db.add_balance(r["user_id"], r["amount"])  # بازگشت خودکار وجه
            await context.bot.send_message(r["user_id"],
                f"❌ خطا در ساخت سرویس: {e}\n💰 مبلغ {fmt(r['amount'])} تومان به کیف پول شما برگشت.")
            await query.message.reply_text(f"⚠️ ساخت سرویس ناموفق ({e})\n💰 وجه به‌صورت خودکار به کیف پول کاربر برگشت.")
            return
        await deliver_service(context, r["user_id"], order, panel)
        await query.message.reply_text(f"✅ رسید #{rid} تایید شد — سرویس ساخته و برای کاربر ارسال شد.")
    elif r["rtype"] == "renew":
        o = db.get_order(meta.get("order_id"))
        if not o or o["status"] != "active":
            # سرویس در این فاصله حذف/بایگانی شده: تمدید نمی‌شود و مبلغ به کیف پول برمی‌گردد
            db.add_balance(r["user_id"], r["amount"])
            try:
                await context.bot.send_message(r["user_id"],
                    f"❌ سرویسی که برای تمدیدش پرداخت کردید دیگر فعال نیست.\n💰 مبلغ {fmt(r['amount'])} تومان به کیف پول شما برگشت.")
            except Exception:
                pass
            await query.message.reply_text(f"⚠️ سفارش رسید #{rid} فعال نیست؛ تمدید انجام نشد و وجه به کیف پول کاربر برگشت.")
            return
        try:
            await do_renew_and_deliver(query, context, r["user_id"], o["id"], meta.get("plan_id"))
        except Exception as e:
            db.add_balance(r["user_id"], r["amount"])  # بازگشت خودکار وجه
            await context.bot.send_message(r["user_id"],
                f"❌ خطا در تمدید سرویس: {e}\n💰 مبلغ {fmt(r['amount'])} تومان به کیف پول شما برگشت.")
            await query.message.reply_text(f"⚠️ تمدید ناموفق ({e})\n💰 وجه به‌صورت خودکار به کیف پول کاربر برگشت.")
            return
        await query.message.reply_text(f"✅ رسید #{rid} تایید شد — سرویس تمدید شد.")


async def rc_reject(query, context, rid):
    r = db.get_receipt(rid)
    if not r or r["status"] != "pending":
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer("⚠️ این تراکنش قبلاً توسط یک ادمین دیگر بررسی و بسته شده است.", show_alert=True)
        return
    db.set_receipt_status(rid, "rejected")
    notify_group(context.bot, f"❌ رسید R{rid} رد شد\n👤 {who(r['user_id'])} | 💸 {fmt(r['amount'])} تومان", topic="pay")
    await close_receipt_for_others(context.bot, rid, query.message.chat_id,
                                   "❌ این تراکنش توسط یک ادمین دیگر رد شد و بسته شد.")
    try:
        await query.message.delete()
    except Exception:
        pass
    await context.bot.send_message(r["user_id"],
        f"❌ رسید شما (مبلغ {fmt(r['amount'])} تومان) تایید نشد.\n"
        f"در صورت نیاز با پشتیبانی در تماس باشید: {db.setting('support_id', '-')}")
    await query.message.reply_text(f"❌ رسید #{rid} رد شد.")


# ---------- مدیریت ادمین‌ها ----------
async def admin_admins(query):
    ads = get_admins()
    lines = [f"👑 ادمین اصلی: <code>{ADMIN_ID}</code>"] + [f"👤 ادمین: <code>{h(a)}</code>" for a in ads]
    rows = [[btn("➕ افزودن ادمین", "adm:add")]]
    rows += [[btn(f"🗑 حذف {a}", f"adm:del:{a}")] for a in ads]
    rows.append(back_row("admin:g:users"))
    await page(query, card("👑 مدیریت ادمین‌ها", lines,
                           note="ادمین‌ها به همه‌ی بخش‌ها دسترسی دارند: تایید پرداخت، تنظیمات و بقیه."), rows)


# ---------- مدیریت کاربر ----------
USERS_PER_PAGE = 10
# فیلترهای لیست کاربران: کلید ← (عنوان، شرط SQL)
USER_FILTERS = {
    "": ("📋 لیست کل کاربران", "1=1"),
    "bal": ("💰 کاربرانی که موجودی دارند", "balance > 0"),
    "ref": ("👥 کاربرانی که زیرمجموعه دارند", "id IN (SELECT referred_by FROM users WHERE referred_by IS NOT NULL)"),
    "neg": ("➖ کاربرانی که موجودی منفی دارند", "balance < 0"),
}


def _short(v, n=11):
    v = str(v or "")
    return v if len(v) <= n else v[:n] + "…"


async def admin_users_list(query, pg=0, flt=""):
    title, where = USER_FILTERS.get(flt, USER_FILTERS[""])
    total = db.one(f"SELECT COUNT(*) c FROM users WHERE {where}")["c"]
    pages = max((total + USERS_PER_PAGE - 1) // USERS_PER_PAGE, 1)
    pg = min(max(pg, 0), pages - 1)
    users = db.q(f"SELECT * FROM users WHERE {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                 (USERS_PER_PAGE, pg * USERS_PER_PAGE))
    sfx = f":{flt}" if flt else ""
    # ستون‌ها از چپ به راست چیده می‌شوند؛ «شناسه» آخر می‌آید تا سمت راست دیده شود
    rows = [[btn("عملیات", "au:noop"), btn("نام کاربری", "au:noop"), btn("شناسه", "au:noop")]]
    for u in users:
        name = u["username"] or u["full_name"] or "—"
        lock = "⛔ " if u["is_blocked"] else ""
        rows.append([btn("⚙️ مدیریت", f"au:panel:{u['id']}"), btn(lock + _short(name), f"au:panel:{u['id']}"),
                     btn(str(u["id"]), f"au:panel:{u['id']}")])
    nav = []
    if pg > 0:
        nav.append(btn("قبلی", f"au:list:{pg - 1}{sfx}"))
    if pg < pages - 1:
        nav.append(btn("بعدی", f"au:list:{pg + 1}{sfx}"))
    if nav:
        rows.append(nav)
    rows.append([btn("بازگشت به منوی قبل", "admin:g:users")])
    lines = [f"👤 تعداد: <b>{total}</b>" + (f"  ·  📄 صفحه {pg + 1} از {pages}" if pages > 1 else "")]
    if flt == "bal":
        lines.append(f"💰 جمع موجودی‌ها: <b>{fmt(db.one(f'SELECT COALESCE(SUM(balance),0) c FROM users WHERE {where}')['c'])}</b> تومان")
    await page(query, card(title, lines, note="برای مدیریت روی کاربر بزنید." if total else "کاربری در این لیست نیست."), rows)


async def admin_user_panel(query, uid_target, notice=None):
    u = db.get_user(uid_target)
    if not u:
        await page(query, card("👤 مدیریت کاربر", ["❌ کاربر یافت نشد."]), [back_row("au:list:0")])
        return
    t = u["id"]
    one = lambda sql, *a: db.one(sql, a)["c"] or 0
    services = db.get_user_orders(t, active_only=False)
    active = len([o for o in services if o["status"] == "active"])
    tests = one("SELECT COUNT(*) c FROM orders WHERE user_id=? AND price=0", t)
    test_limit = u["test_limit"] if u["test_limit"] is not None else 1
    ref = u["referred_by"]
    uname = f"@{h(u['username'])}" if u["username"] else NOT_SET
    hour, month = now() - 3600, now() - 30 * 86400
    paid_sql = "FROM orders WHERE user_id=? AND price>0 AND status!='archived'"
    info = [
        f"⭕️ وضعیت کاربر: <b>{'⛔ مسدود' if u['is_blocked'] else '✅ فعال'}</b>",
        f"⭕️ نام: {val(u['full_name'])}",
        f"⭕️ نام کاربری: {uname}",
        f"⭕️ آیدی عددی: <code>{t}</code>",
        f"⭕️ زمان عضویت: <b>{jdate(u['created_at'])}</b>",
        f"⭕️ آخرین استفاده از ربات: <b>{jdate(u['last_seen'])}</b>",
        f"⭕️ اکانت تست: <b>{tests}</b> از <b>{test_limit}</b>",
        f"⭕️ سرویس‌ها: <b>{active}</b> فعال از <b>{len(services)}</b>",
        f"⭕️ تعداد زیرمجموعه: <b>{db.referral_count(t)}</b>",
        f"⭕️ معرف کاربر: " + (f"<code>{ref}</code>" if ref else "<b>ندارد</b>"),
    ]
    money = [
        f"🔰 موجودی کاربر: <b>{fmt(u['balance'])}</b> تومان",
        f"🔰 تعداد خرید کل: <b>{one('SELECT COUNT(*) c ' + paid_sql, t)}</b>",
        f"🔰 مبلغ کل پرداختی: <b>{fmt(one('SELECT SUM(amount) c FROM receipts WHERE user_id=? AND status=?', t, 'approved'))}</b> تومان",
        f"🔰 جمع کل خرید: <b>{fmt(one('SELECT SUM(price) c ' + paid_sql, t))}</b> تومان",
        f"🔰 درصد تخفیف: <b>{user_discount(t)}٪</b>",
        f"🔰 فروش یک ساعت گذشته: <b>{one('SELECT COUNT(*) c ' + paid_sql + ' AND created_at>?', t, hour)}</b> عدد"
        f" · <b>{fmt(one('SELECT SUM(price) c ' + paid_sql + ' AND created_at>?', t, hour))}</b> تومان",
        f"🔰 فروش یک ماه گذشته: <b>{one('SELECT COUNT(*) c ' + paid_sql + ' AND created_at>?', t, month)}</b> عدد"
        f" · <b>{fmt(one('SELECT SUM(price) c ' + paid_sql + ' AND created_at>?', t, month))}</b> تومان",
    ]
    text = "\n\n".join(([f"<b>{notice}</b>"] if notice else []) + [
        "<b>👀 اطلاعات کاربر</b>", "<blockquote>" + "\n".join(info) + "</blockquote>",
        "<b>💎 گزارشات مالی</b>", "<blockquote>" + "\n".join(money) + "</blockquote>",
    ])
    await page(query, text, [
        [btn("♻️ بروزرسانی اطلاعات", f"au:panel:{t}")],
        [btn("👇 کم کردن موجودی", f"au:deduct:{t}"), btn("👆 افزایش موجودی", f"au:charge:{t}")],
        [btn("🔓 رفع مسدودی کاربر", f"au:unblock:{t}"), btn("🔒 مسدود کردن کاربر", f"au:block:{t}")],
        [btn("✍️ ارسال پیام به کاربر", f"au:msg:{t}"), btn("🎁 درصد تخفیف", f"au:disc:{t}")],
        [btn("🛍 مشاهده سفارشات کاربر", f"au:svcs:{t}")],
        [btn("👥 زیرمجموعه های کاربر", f"au:refs:{t}")],
        [btn("🔄 حذف زیرمجموعه‌ها", f"au:delrefs:{t}"), btn("🔄 خارج کردن از زیر", f"au:unref:{t}")],
        [btn("➕ محدودیت اکانت تست", f"au:tlim:{t}"), btn("💰 مشاهده پرداختی", f"au:pays:{t}")],
        [btn("💡 روشن کردن اکانت", f"au:on:{t}"), btn("💡 خاموش کردن اکانت", f"au:off:{t}")],
        [btn("🔀 انتقال حساب کاربری", f"au:xfer:{t}")],
        [btn("❌ حذف سرویس های کاربر", f"au:delsvc:{t}")],
        [btn("0️⃣ صفر کردن موجودی", f"au:zero:{t}")],
        back_row("au:list:0"),
    ])


# کارهایی که برگشت ندارند یک قدم تأیید می‌گیرند: (عنوان، توضیح)
AU_CONFIRM = {
    "zero": ("0️⃣ صفر کردن موجودی", "کل موجودی کیف پول این کاربر صفر می‌شود."),
    "delsvc": ("❌ حذف سرویس های کاربر", "همه‌ی سرویس‌های فعال این کاربر از پنل حذف می‌شوند و پولی برنمی‌گردد."),
    "delrefs": ("🔄 حذف زیرمجموعه‌ها", "همه‌ی زیرمجموعه‌های این کاربر از زیر او خارج می‌شوند."),
    "off": ("💡 خاموش کردن اکانت", "همه‌ی سرویس‌های فعال این کاربر روی پنل خاموش می‌شوند تا وقتی دوباره روشن کنید."),
}


def _active_orders_with_panel(target):
    out = []
    for o in db.get_user_orders(target, active_only=False):
        if o["status"] == "active":
            out.append((o, db.get_panel(o["panel_id"]) if o["panel_id"] else None))
    return out


async def admin_user_action(query, context, uid, action, target):
    """دکمه‌های صفحه‌ی مدیریت کاربر (au:<action>:<target>)."""
    u = db.get_user(target)
    if not u:
        await page(query, card("👤 مدیریت کاربر", ["❌ کاربر یافت نشد."]), [back_row("au:list:0")])
        return
    name = h(u["full_name"] or target)
    notice = None
    cancel = [[btn("🔙 انصراف", f"au:panel:{target}")]]

    if action in AU_CONFIRM:
        title, desc = AU_CONFIRM[action]
        await page(query, card(title, [f"👤 {name}", f"⚠️ {desc}"], note="مطمئن هستید؟"),
                   [[btn("✅ بله، انجام بده", f"au:{action}!:{target}")], *cancel])
        return

    if action in ("block", "unblock"):
        db.x("UPDATE users SET is_blocked=? WHERE id=?", (1 if action == "block" else 0, target))
        notice = "⛔ کاربر مسدود شد." if action == "block" else "✅ مسدودی کاربر برداشته شد."
    elif action == "zero!":
        db.x("UPDATE users SET balance=0 WHERE id=?", (target,))
        notice = "✅ موجودی صفر شد."
    elif action == "unref":
        db.x("UPDATE users SET referred_by=NULL WHERE id=?", (target,))
        notice = "✅ کاربر از زیرمجموعه‌ی معرفش خارج شد."
    elif action == "delrefs!":
        db.x("UPDATE users SET referred_by=NULL WHERE referred_by=?", (target,))
        notice = "✅ زیرمجموعه‌ها حذف شدند."
    elif action in ("on", "off!", "delsvc!"):
        await safe_edit(query, "⏳ در حال اعمال روی پنل...")
        ok = fail = 0
        for o, panel in _active_orders_with_panel(target):
            if action == "on" and o["expire_at"] and o["expire_at"] < now():
                continue  # سرویس منقضی با «روشن کردن» دوباره فعال نمی‌شود
            try:
                if not panel:
                    raise RuntimeError("no panel")
                cl = panel_client(panel)
                if action == "delsvc!":
                    await asyncio.to_thread(cl.del_user, o["username"])
                    db.update_order(o["id"], status="deleted")
                else:
                    await asyncio.to_thread(cl.set_status, o["username"], "active" if action == "on" else "disabled")
                ok += 1
            except Exception as e:
                log.warning("au %s order %s: %s", action, o["id"], e)
                fail += 1
        verb = {"on": "روشن شد", "off!": "خاموش شد", "delsvc!": "حذف شد"}[action]
        await page(query, card("💡 نتیجه", [f"✅ {ok} سرویس {verb}."] + ([f"❌ {fail} سرویس ناموفق (پنل در دسترس نبود)."] if fail else [])),
                   [back_row(f"au:panel:{target}")])
        return
    elif action in ("msg", "disc", "tlim", "xfer"):
        prompts = {
            "msg": ("✍️ ارسال پیام به کاربر", "متن پیام را بفرستید؛ همان‌طور برای کاربر ارسال می‌شود."),
            "disc": ("🎁 درصد تخفیف", f"فعلی: {user_discount(target)}٪ — یک عدد از ۰ تا ۱۰۰ بفرستید (۰ یعنی بدون تخفیف)."),
            "tlim": ("➕ محدودیت اکانت تست", f"فعلی: {u['test_limit'] if u['test_limit'] is not None else 1} — تعداد اکانت تستی که این کاربر می‌تواند بگیرد را بفرستید (۰ تا ۲۰)."),
            "xfer": ("🔀 انتقال حساب کاربری", "آیدی عددی حساب مقصد را بفرستید. موجودی و همه‌ی سرویس‌های این کاربر به آن حساب منتقل می‌شوند (مقصد باید یک بار ربات را استارت کرده باشد)."),
        }
        title, note = prompts[action]
        db.set_state(uid, f"au_{action}", {"target": target})
        await page(query, card(title, [f"👤 {name}"], note=note), cancel)
        return
    elif action == "refs":
        refs = db.q("SELECT * FROM users WHERE referred_by=? ORDER BY created_at DESC LIMIT 30", (target,))
        rows = [[btn(f"👤 {(r['full_name'] or r['username'] or str(r['id']))[:24]}", f"au:panel:{r['id']}")] for r in refs]
        await page(query, card(f"👥 زیرمجموعه‌های {name} ({db.referral_count(target)})",
                               [] if refs else ["این کاربر زیرمجموعه‌ای ندارد."],
                               note="۳۰ نفر آخر؛ برای مدیریت روی هر نفر بزنید." if refs else None),
                   rows + [back_row(f"au:panel:{target}")])
        return
    elif action == "pays":
        rs = db.q("SELECT * FROM receipts WHERE user_id=? ORDER BY id DESC LIMIT 20", (target,))
        icon = {"approved": "✅", "rejected": "❌", "pending": "⏳"}
        kind = {"wallet_charge": "شارژ کیف پول", "purchase": "خرید", "renew": "تمدید"}
        lines = [f"{icon.get(r['status'], '•')} <b>R{r['id']}</b> · {fmt(r['amount'])} تومان · {kind.get(r['rtype'], h(r['rtype']))}"
                 f" · {jdate(r['created_at'], False)}" for r in rs]
        await page(query, card("💰 پرداختی‌های کاربر", lines or ["این کاربر پرداختی ندارد."],
                               note="۲۰ رسید آخر." if rs else None), [back_row(f"au:panel:{target}")])
        return
    await admin_user_panel(query, target, notice)


# ---------- تنظیمات ----------
SETTING_KEYS = [
    ("backup_chat_id", "💾 کانال بکاپ"),
    ("card_number", "💳 شماره کارت"),
    ("card_name", "👤 صاحب حساب"),
    ("support_id", "☎️ پشتیبانی"),
    ("test_volume_gb", "📦 حجم تست"),
    ("test_days", "⏳ مدت تست"),
    ("faq_text", "❓ سوالات متداول"),
    ("channel_id", "📢 کانال گزارش"),
    ("group_id", "👥 گروه گزارش"),
    ("backup_time", "🕓 ساعت بکاپ روزانه (وقت ایران)"),
    ("report_time", "🕓 ساعت گزارش روزانه (وقت ایران)"),
]
# Iran has had no daylight saving since 2022: a fixed +03:30.
IRAN_OFFSET = datetime.timedelta(hours=3, minutes=30)
DAILY_TIMES = {"backup_time": "06:30", "report_time": "02:30"}  # the old 03:00 and 23:00 UTC


def parse_hhmm(text):
    """«6:30»، «۰۶:۳۰» یا «18» ← «06:30»؛ None اگر ساعت معتبر نبود."""
    t = (text or "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    m = re.fullmatch(r"(\d{1,2})(?:[:.٫](\d{2}))?", t)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    return f"{h:02d}:{mi:02d}" if h < 24 and mi < 60 else None


def daily_time(key):
    return parse_hhmm(db.setting(key, DAILY_TIMES[key])) or DAILY_TIMES[key]


def iran_to_utc(hhmm):
    h, m = map(int, hhmm.split(":"))
    return (datetime.datetime(2000, 1, 1, h, m) - IRAN_OFFSET).time().replace(tzinfo=datetime.timezone.utc)


def schedule_daily_jobs(jq):
    """Daily report and backup at the times set in the bot (Iran time); re-run after a change, no restart."""
    if not jq:
        return
    for name in ("daily_report", "daily_backup"):
        for job in jq.get_jobs_by_name(name):
            job.schedule_removal()
    jq.run_daily(daily_report_job, time=iran_to_utc(daily_time("report_time")), name="daily_report")
    jq.run_daily(daily_backup_job, time=iran_to_utc(daily_time("backup_time")), name="daily_backup")
# چیدمان دکمه‌ها در صفحه تنظیمات (یک ردیف کامل یا دو دکمه کنار هم)
SETTING_LAYOUT = [
    ("test_volume_gb", "test_days"),
    ("card_number", "card_name"),
    ("support_id", "faq_text"),
    ("backup_chat_id",),
]


async def admin_settings(query):
    # اکانت تست پیش‌فرض خاموش است؛ کلید روشن/خاموش کنار حجم و مدت تست نمایش داده می‌شود
    test_on = db.setting("test_enabled", "0") == "1"
    st = db.setting
    vol, days = st("test_volume_gb"), st("test_days")
    faq = "<b>✅ نوشته شده</b>" if st("faq_text") else NOT_SET
    text = card("⚙️ تنظیمات عمومی",
        ["🎁 <b>اکانت تست</b>",
         f"وضعیت: <b>{'🟢 روشن' if test_on else '🔴 خاموش'}</b>",
         f"📦 حجم: {val(f'{vol} گیگ' if vol else '')}  ·  ⏳ مدت: {val(f'{days} روز' if days else '')}"],
        ["💳 <b>پرداخت کارت به کارت</b>",
         f"شماره کارت: " + (f"<code>{h(st('card_number'))}</code>" if st("card_number") else NOT_SET),
         f"صاحب حساب: {val(st('card_name'))}"],
        ["🧰 <b>پشتیبانی و بکاپ</b>",
         f"☎️ پشتیبانی: {val(st('support_id'))}",
         f"❓ سوالات متداول: {faq}",
         f"💾 کانال بکاپ: {val(st('backup_chat_id'))}"],
        note="برای تغییر هر مورد، دکمه‌ی آن را بزنید.")
    await page(query, text, [
        [btn(f"🎁 اکانت تست: {'روشن ✅' if test_on else 'خاموش ❌'}", "tgl:test_enabled")],
        [btn("⏳ مدت تست", "set:test_days"), btn("📦 حجم تست", "set:test_volume_gb")],
        [btn("👤 صاحب حساب", "set:card_name"), btn("💳 شماره کارت", "set:card_number")],
        [btn("❓ سوالات متداول", "set:faq_text"), btn("☎️ پشتیبانی", "set:support_id")],
        [btn("💾 کانال بکاپ", "set:backup_chat_id")],
        back_row(),
    ])


async def admin_channel(query):
    text = card("📢 کانال و گروه گزارش",
                [f"📢 کانال: {val(db.setting('channel_id'))}", f"👥 گروه: {val(db.setting('group_id'))}",
                 f"🕓 گزارش روزانه: ساعت {daily_time('report_time')} به وقت ایران"],
                note="آیدی را با @ یا عدد -100 وارد کنید. ربات باید در کانال/گروه ادمین باشد. "
                     "گروه، گزارش لحظه‌ای (خرید، تمدید، رسید، تیکت، عضو جدید، وضعیت پنل) را هم می‌گیرد.")
    await page(query, text, [
        [btn("👥 آیدی گروه", "set:group_id"), btn("📢 آیدی کانال", "set:channel_id")],
        [btn("🕓 ساعت گزارش روزانه", "set:report_time")],
        back_row("admin:g:shop"),
    ])


# ---------- تیکت‌ها ----------
async def admin_tickets(query):
    tickets = db.open_tickets()
    if not tickets:
        await page(query, card("🎫 تیکت‌ها", ["✅ تیکت بازی وجود ندارد."]), [back_row()])
        return
    lines = []
    rows = []
    for t in tickets:
        preview = (t["message"] or "📷 عکس").replace("\n", " ")
        preview = preview[:38] + ("…" if len(preview) > 38 else "")
        lines.append(f"<b>#{t['id']}</b>  ·  👤 <code>{t['user_id']}</code>\n💬 {h(preview)}")
        rows.append([btn(f"🎫 تیکت #{t['id']}  ·  کاربر {t['user_id']}", f"tk:{t['id']}")])
    rows.append(back_row())
    await page(query, card(f"🎫 تیکت‌های باز ({len(tickets)})", *[[x] for x in lines]), rows)


async def admin_ticket_detail(query, tid):
    t = db.get_ticket(tid)
    if not t:
        await safe_edit(query, "❌ تیکت یافت نشد.")
        return
    text = (f"🎫 تیکت #{t['id']}\n👤 کاربر: {t['user_id']}\n📌 وضعیت: {t['status']}\n\n"
            f"💬 پیام:\n{t['message']}")
    kb = InlineKeyboardMarkup([
        [btn("✍️ پاسخ", f"tk:reply:{tid}"), btn("🔒 بستن", f"tk:close:{tid}")],
        [btn("🔙 بازگشت", "admin:tickets")],
    ])
    if t["photo_id"]:
        try:
            await query.message.delete()
        except Exception:
            pass
        await query.message.reply_photo(t["photo_id"], caption=text, reply_markup=kb)
    else:
        await safe_edit(query, text, reply_markup=kb)


# ---------- گزارش ----------
def report_text(title, ts, rich=False):
    s = db.stats_since(ts)
    t = db.totals()
    if rich:
        return card(f"📈 {title}",
                    [f"👤 کاربر جدید: <b>{s['new_users']}</b>",
                     f"🛍 سفارش جدید: <b>{s['new_orders']}</b>",
                     f"💰 درآمد: <b>{fmt(s['revenue'])}</b> تومان"],
                    ["📊 <b>کل ربات</b>",
                     f"👤 کاربران: <b>{t['users']}</b>  ·  🛍 سفارش‌ها: <b>{t['orders']}</b>",
                     f"✅ سرویس فعال: <b>{t['active']}</b>",
                     f"💰 درآمد کل: <b>{fmt(t['revenue'])}</b> تومان"])
    return (f"📅 {title}\n"
            f"👤 کاربران جدید: {s['new_users']}\n"
            f"🛍 سفارشات جدید: {s['new_orders']}\n"
            f"💰 درآمد: {fmt(s['revenue'])} تومان\n\n"
            f"📊 آمار کلی:\n"
            f"👤 کل کاربران: {t['users']}\n"
            f"🛍 کل سفارشات: {t['orders']}\n"
            f"✅ سرویس‌های فعال: {t['active']}\n"
            f"💰 درآمد کل: {fmt(t['revenue'])} تومان")


async def admin_report_menu(query):
    t = db.totals()
    text = card("💎 مالی",
                [f"💰 درآمد کل: <b>{fmt(t['revenue'])}</b> تومان",
                 f"✅ سرویس فعال: <b>{t['active']}</b>  ·  ⏳ رسید در انتظار: <b>{t['pending_receipts']}</b>"],
                note="بازه‌ی گزارش را انتخاب کنید.")
    await page(query, text, [
        [btn("📅 امروز", "report:day")],
        [btn("🗓 ماهانه", "report:month"), btn("📆 هفتگی", "report:week")],
        [btn("💵 رسیدهای تایید نشده", "admin:receipts")],
        back_row(),
    ])


# ---------- مدیریت پلن‌ها ----------
async def admin_plans(query):
    plans = db.get_plans()
    rows = [[btn("➕ افزودن پلن جدید", "pl:add")]]
    for service in [*SERVICES, ""]:
        group = [p for p in plans if plan_service(p) == service]
        if not group:
            continue
        rows.append([btn(f"〰️ {SERVICES.get(service, 'پلن‌های قدیمی')} 〰️", "pl:noop")])
        for p in group:
            st = "🟢" if p["active"] else "🔴"
            rows.append([btn(f"{st} {plan_label(p)} | {fmt(p['price'])}", f"pl:{p['id']}")])
    rows.append(back_row("admin:g:price"))
    active = len([p for p in plans if p["active"]])
    await page(query, card("📦 مدیریت پلن‌ها",
                           [f"🟢 فعال: <b>{active}</b>  ·  🔴 غیرفعال: <b>{len(plans) - active}</b>"],
                           note="هر سرویس پلن‌ها و قیمت‌های خودش را دارد. برای ویرایش روی پلن بزنید."), rows)


def plan_service_kb(prefix, back):
    rows = [[btn(name, f"{prefix}:{key}")] for key, name in SERVICES.items()]
    rows.append([btn("🔙 بازگشت", back)])
    return InlineKeyboardMarkup(rows)


async def admin_plan_detail(query, pid):
    p = db.get_plan(pid)
    if not p:
        await page(query, card("📦 پلن", ["❌ پلن یافت نشد."]), [back_row("admin:plans")])
        return
    try:
        ul = int(p["user_limit"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        ul = 0
    text = card(f"📦 {h(plan_label(p))}",
                [f"🧩 سرویس: <b>{h(plan_service_name(p))}</b>",
                 f"📊 حجم: <b>{h(vol_text(p['volume_gb']))}</b>  ·  ⏳ مدت: <b>{p['days']}</b> روز",
                 f"👥 دستگاه همزمان: <b>{ul if ul else 'بدون محدودیت'}</b>",
                 f"💰 قیمت: <b>{fmt(p['price'])}</b> تومان"],
                [f"وضعیت: <b>{'🟢 فعال' if p['active'] else '🔴 غیرفعال'}</b>"])
    await page(query, text, [
        [btn("🧩 سرویس", f"pl:svc:{pid}"), btn("✏️ عنوان", f"ple:{pid}:title")],
        [btn("⏳ مدت (روز)", f"ple:{pid}:days"), btn("📊 حجم (گیگ)", f"ple:{pid}:volume_gb")],
        [btn("👥 تعداد کاربر", f"ple:{pid}:user_limit"), btn("💰 قیمت", f"ple:{pid}:price")],
        [btn("🗑 حذف پلن", f"pl:del:{pid}"), btn("⏯ فعال / غیرفعال", f"pl:toggle:{pid}")],
        back_row("admin:plans"),
    ])


# ---------- مدیریت پنل‌ها ----------
def panel_status_icon(p):
    return {"offline": "🔴 Offline", "inactive": "⚪ غیرفعال"}.get(p["status"], "🟢")


def protocols_text(panel):
    protos = panel_protocols(panel)
    if not protos:
        return "  — هیچ پروتکلی روی این پنل هاست ندارد"
    return "\n".join(f"  • {p} ({n} هاست)" for p, n in protos.items())


def service_map_text(panel):
    """نمایش سرویس‌ها روی یک پنل: فروخته می‌شود / فروخته نمی‌شود / روی پنل هاست ندارد."""
    rows = db.get_service_rows(panel["id"])
    lines = []
    for key, name in SERVICES.items():
        on_panel = service_protocols_on(panel, key)
        r = rows.get(key)
        if not on_panel:
            lines.append(f"  ⚫ {name} ← روی پنل هاست ندارد")
        elif r and r["enabled"]:
            lines.append(f"  ✅ {name} ← گروه «{r['remark'] or '-'}»")
        elif r:
            lines.append(f"  🚫 {name} ← روی این پنل فروخته نمی‌شود")
        else:
            lines.append(f"  ✅ {name} ← سرورهای عمومی")
    return "\n".join(lines)


def map_step_view(sd):
    """یک مرحله از انتخاب گروه برای سرویس‌هایی که روی همین پنل هاست دارند.
    هم در جادوی افزودن پنل (ap_map) و هم در انتخاب مجدد برای پنل موجود (pm_map) استفاده می‌شود."""
    keys = sd["services"]
    step = sd.get("step", 0)
    key = keys[step]
    text = (f"🧩 انتخاب گروه سرویس‌ها ({step + 1}/{len(keys)})\n\n"
            f"گروه پنل تعیین می‌کند کاربر به کدام سرورها دسترسی دارد؛ سروری که در هیچ گروهی نیست برای همه است.\n\n")
    for k in keys[:step]:
        g = sd["map"].get(k)
        text += f"{'✅' if g else '🚫'} {SERVICES[k]} ← {('«' + g['name'] + '»') if g else 'فروخته نمی‌شود'}\n"
    text += f"\n👉 سرویس «{SERVICES[key]}» روی کدام گروه فروخته شود؟"
    cur = sd.get("current", {}).get(key)
    if sd.get("panel_id") and cur:
        text += f"\n(انتخاب فعلی: {cur})"
    gbtns = [btn(f"👥 {g['name']}", f"apm:{key}:{g['id']}") for g in sd["groups"]]
    rows = [gbtns[i:i + 2] for i in range(0, len(gbtns), 2)]
    rows.append([btn("🚫 روی این پنل فروخته نشود", f"apm:{key}:x")])
    rows.append([btn("🔙 انصراف", f"pb:{sd['panel_id']}" if sd.get("panel_id") else "admin:panels")])
    return text, InlineKeyboardMarkup(rows)


def mappable_services(protocols):
    return [svc for svc in SERVICES if any(protocols.get(p) for p in SERVICE_PROTOCOLS[svc])]


async def admin_panels(query):
    panels = db.get_panels()
    blocks, rows = [], []
    for p in panels:
        cnt = db.count_panel_active_orders(p["id"])
        sold = [SERVICES[k] for k in db.get_service_map(p["id"]) if service_protocols_on(p, k)]
        icon = {"offline": "🔴", "inactive": "⚪"}.get(p["status"], "🟢")
        blocks.append([f"{icon} <b>{h(p['name'])}</b>  ·  📍 {h(p['location'] or '—')}",
                       f"👥 {cnt}/{p['max_users']}  {bar(cnt, p['max_users'])}",
                       f"🧩 {h('، '.join(sold)) if sold else NOT_SET}"])
        rows.append([btn(f"{icon} {p['name']}  ·  {cnt}/{p['max_users']}", f"pb:{p['id']}")])
    if not panels:
        blocks.append(["هنوز پنلی ثبت نشده. از «➕ افزودن پنل» شروع کنید."])
    rows.append([btn("➕ افزودن پنل", "pb:add")])
    rows.append(back_row())
    await page(query, card(f"✏️ پنل‌های متصل ({len(panels)})", *blocks), rows)


async def admin_panel_detail(query, pid):
    p = db.get_panel(pid)
    if not p:
        await page(query, card("🖥 پنل", ["❌ پنل یافت نشد."]), [back_row("admin:panels")])
        return
    cnt = db.count_panel_active_orders(pid)
    icons = {"active": "🟢 فعال", "inactive": "⚪ غیرفعال", "offline": "🔴 آفلاین"}
    checked = datetime.datetime.fromtimestamp(p["checked_at"]).strftime("%Y-%m-%d %H:%M") if p["checked_at"] else "هرگز"
    text = card(f"🖥 {h(p['name'])}",
                [f"📌 وضعیت: <b>{icons.get(p['status'], h(p['status']))}</b>",
                 f"🌐 آدرس: <code>{h(p['url'])}</code>",
                 f"👤 یوزر: <code>{h(p['username'])}</code>  ·  📍 {val(p['location'])}",
                 f"🕓 آخرین بررسی: <b>{checked}</b>"],
                [f"👥 کاربران فعال: <b>{cnt}</b> از <b>{p['max_users']}</b>", bar(cnt, p["max_users"], 14)],
                ["📡 <b>پروتکل‌های روی پنل</b>", h(protocols_text(p))],
                ["🧩 <b>سرویس‌ها</b>", h(service_map_text(p))],
                note=("⚠️ گواهی SSL پنل معتبر نیست (self-signed)؛ اتصال رمزنگاری شده ولی هویت پنل تایید نمی‌شود."
                      if p["tls_insecure"] else None))
    await page(query, text, [
        [btn("🔄 بررسی اتصال و پروتکل‌ها", f"pb:test:{pid}")],
        [btn("✏️ ویرایش", f"pb:edit:{pid}"), btn("⏯ فعال / غیرفعال", f"pb:toggle:{pid}")],
        [btn("🧩 گروه سرویس‌ها", f"pbm:{pid}")],
        [btn("🗑 حذف پنل", f"pb:del:{pid}"), btn("🔙 بازگشت", "admin:panels")],
    ])


async def admin_panel_test(query, pid):
    """بررسی اتصال + خواندن دوباره‌ی پروتکل‌ها از پنل؛ تغییرات بلافاصله در فروش ربات اعمال می‌شود."""
    p = db.get_panel(pid)
    if not p:
        return
    back = InlineKeyboardMarkup([[btn("🔙 بازگشت به پنل", f"pb:{pid}")]])
    await safe_edit(query, f"🔄 در حال بررسی پنل {p['name']}...")
    try:
        t0 = time.time()
        before, after = await asyncio.to_thread(refresh_panel, p)
        ms = int((time.time() - t0) * 1000)
    except Exception as e:
        if p["status"] == "active":
            db.update_panel(pid, status="offline")
        await query.message.reply_text(f"❌ پنل {p['name']} — Offline\nخطا: {e}", reply_markup=back)
        return
    if p["status"] == "offline":
        db.update_panel(pid, status="active")
    p = db.get_panel(pid)
    diff = protocols_diff_text(before, after)
    changes = f"🔔 تغییرات:\n{diff}" if diff else "✔️ پروتکل‌ها تغییری نکرده‌اند."
    await query.message.reply_text(
        f"✅ پنل {p['name']} — Online ({ms}ms)\n\n"
        f"📡 پروتکل‌های روی پنل:\n{protocols_text(p)}\n\n"
        f"{changes}\n\n"
        f"🧩 سرویس‌ها:\n{service_map_text(p)}",
        reply_markup=back)


async def admin_panel_edit(query, pid):
    await page(query, card("✏️ ویرایش پنل", note="کدام مورد را تغییر می‌دهید؟"), [
        [btn("🌐 آدرس", f"pbe:{pid}:url"), btn("🏷 نام", f"pbe:{pid}:name")],
        [btn("🔑 پسورد", f"pbe:{pid}:password"), btn("👤 یوزرنیم", f"pbe:{pid}:username")],
        [btn("👥 سقف کاربر", f"pbe:{pid}:max_users"), btn("📍 موقعیت", f"pbe:{pid}:location")],
        [btn("🧩 گروه سرویس‌ها", f"pbm:{pid}")],
        back_row(f"pb:{pid}"),
    ])


async def finish_panel_wizard(message, uid, draft):
    mapping = {svc: draft["map"].get(svc) for svc in draft.get("services", [])}
    pid = db.add_panel(draft)
    db.set_service_map(pid, mapping)
    db.set_state(uid, "none")
    p = db.get_panel(pid)
    note = ("از این پس کاربران جدید به‌صورت خودکار روی خلوت‌ترین پنل ساخته می‌شوند." if db.get_service_map(pid) else
            "⚠️ هیچ سرویسی برای فروش روی این پنل انتخاب نشد؛ از «🧩 انتخاب گروه سرویس‌ها» فعالش کنید.")
    await message.reply_text(
        f"✅ پنل «{draft['name']}» با موفقیت ثبت شد!\n\n"
        f"🌐 {draft['url']}\n📍 {draft['location']}\n👥 سقف: {draft['max_users']} کاربر\n\n"
        f"📡 پروتکل‌ها:\n{protocols_text(p)}\n\n🧩 سرویس‌ها:\n{service_map_text(p)}\n\n{note}\n\n"
        f"💡 هر وقت روی پنل پروتکل جدیدی اضافه کردید، «🔄 بررسی اتصال» را بزنید (هر ۵ دقیقه هم خودکار بررسی می‌شود).",
        reply_markup=main_menu_kb(uid))


async def admin_panels_cap(query):
    panels = db.get_panels()
    if not panels:
        await page(query, card("🛠 قابلیت‌های پنل", ["هنوز پنلی ثبت نشده."]), [back_row()])
        return
    icons = {"active": "🟢", "inactive": "⚪", "offline": "🔴"}
    blocks = []
    for p in panels:
        cnt = db.count_panel_active_orders(p["id"])
        sold = [SERVICES[k] for k in SERVICES if k in db.get_service_map(p["id"]) and service_protocols_on(p, k)]
        protos = ", ".join(panel_protocols(p))
        blocks.append([f"{icons.get(p['status'], '⚪')} <b>{h(p['name'])}</b>",
                       f"👥 {cnt}/{p['max_users']}  {bar(cnt, p['max_users'])}",
                       f"📡 پروتکل‌ها: {val(protos)}",
                       f"🧩 فروش: {val('، '.join(sold))}"])
    await page(query, card("🛠 قابلیت‌ها و ظرفیت پنل‌ها", *blocks), [[btn("✏️ مدیریت پنل‌ها", "admin:panels")], back_row()])


# ---------- بکاپ ----------
async def send_backup(bot, chat_id, note="💾 بکاپ دیتابیس ربات", thread_id=None):
    """کپی سازگار دیتابیس (کاربران، کیف پول‌ها، سفارش‌ها، پنل‌ها، پلن‌ها، تنظیمات) به‌صورت فایل برای ادمین."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        await asyncio.to_thread(db.backup_to, tmp)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        t = db.totals()
        with open(tmp, "rb") as f:
            await bot.send_document(chat_id, f, filename=f"bot-backup_{stamp}.db", message_thread_id=thread_id,
                caption=(f"{note}\n🕓 {stamp}\n👤 کاربران: {t['users']} | 🧾 سفارش‌ها: {t['orders']} | "
                         f"✅ فعال: {t['active']}\n\n♻️ برای بازگردانی: پنل مدیریت ← 💾 بکاپ ← بازگردانی"))
        return True
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass


async def admin_backup_menu(query):
    auto = db.setting("backup_auto", "1") == "1"
    text = card("💾 بکاپ ربات",
                ["📦 شامل همه‌چیز: کاربران، کیف پول‌ها، سفارش‌ها، رسیدها، پنل‌ها، پلن‌ها و تنظیمات"],
                [f"🕓 بکاپ خودکار روزانه (ساعت {daily_time('backup_time')} به وقت ایران): <b>{'🟢 روشن' if auto else '🔴 خاموش'}</b>",
                 f"📢 کانال بکاپ: {val(db.setting('backup_chat_id'))}"],
                note="کانال بکاپ را از «⚙️ تنظیمات عمومی» تنظیم کنید.")
    await page(query, text, [
        [btn("📥 دریافت بکاپ الان", "bk:now")],
        [btn(f"🔁 خودکار: {'روشن ✅' if auto else 'خاموش ❌'}", "bk:auto"), btn("♻️ بازگردانی", "bk:restore")],
        [btn("🕓 ساعت بکاپ روزانه", "set:backup_time")],
        back_row("admin:g:update"),
    ])


# ---------- پیام همگانی ----------
async def run_broadcast(bot, admin_id, payload):
    """ارسال پیام به همه‌ی کاربرانِ غیرمسدود با سرعت امن تلگرام (~۲۰ پیام در ثانیه) در پس‌زمینه."""
    ids = db.all_user_ids()
    sent = failed = 0
    for i, uid in enumerate(ids):
        for attempt in range(3):
            try:
                if payload.get("photo_id"):
                    await bot.send_photo(uid, payload["photo_id"], caption=payload.get("text") or None)
                else:
                    await bot.send_message(uid, payload["text"])
                sent += 1
                break
            except RetryAfter as e:
                await asyncio.sleep(float(getattr(e, "retry_after", 5)) + 1)
            except (Forbidden, BadRequest):
                failed += 1  # ربات بلاک شده یا کاربر حذف شده
                break
            except Exception as e:
                if attempt == 2:
                    failed += 1
                    log.warning("broadcast to %s failed: %s", uid, e)
                await asyncio.sleep(1)
        await asyncio.sleep(0.05)
        if (i + 1) % 500 == 0:
            try:
                await bot.send_message(admin_id, f"📢 در حال ارسال... {i + 1}/{len(ids)}")
            except Exception:
                pass
    try:
        await bot.send_message(admin_id, f"✅ پیام همگانی تمام شد.\n📨 موفق: {sent}\n❌ ناموفق (ربات بلاک/حذف شده): {failed}")
    except Exception:
        pass


# =================== مسیریاب Callback ===================
async def admin_dispatch(query, uid, parts):
    """کارهای پنل مدیریت؛ parts مثل ['admin', 'stats'] — هم از دکمه‌ی شیشه‌ای و هم از کیبورد پایین."""
    what = parts[1]
    db.set_state(uid, "none")  # رفتن به هر صفحه‌ی مدیریت، ورودی نیمه‌کاره (مثلاً «مقدار جدید») را لغو می‌کند
    if what == "menu":
        await safe_edit(query, "🧑‍💼 پنل مدیریت: از منوی پایین صفحه انتخاب کنید.")
    elif what == "addpanel":
        db.set_state(uid, "ap_name", {})
        await safe_edit(query, "➕ افزودن Tifusi Panel\n\n۱) نام پنل را وارد کنید (مثلاً «سرور آلمان ۱»):",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:panels")]]))
    elif what == "g" and len(parts) > 2 and parts[2] in ADMIN_GROUPS:
        await safe_edit(query, card(ADMIN_GROUPS[parts[2]][0], note="یکی از گزینه‌ها را انتخاب کنید."),
                        reply_markup=admin_group_kb(parts[2]), parse_mode="HTML")
    elif what == "soon":
        await page(query, card("🔜 به‌زودی", ["این بخش در نسخه‌ی بعدی ربات اضافه می‌شود."]), [back_row()])
    elif what == "stats":
        await admin_stats(query)
    elif what == "receipts":
        await admin_receipts(query)
    elif what == "delreqs":
        await admin_delete_requests(query)
    elif what == "users":
        db.set_state(uid, "au_search")
        await safe_edit(query, "👤 آیدی عددی یا یوزرنیم کاربر را ارسال کنید:",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:menu")]]))
    elif what == "plans_view":
        await show_tariff(query)
    elif what == "settings":
        await admin_settings(query)
    elif what == "tickets":
        await admin_tickets(query)
    elif what == "panels_cap":
        await admin_panels_cap(query)
    elif what == "update":
        await page(query, card("🆕 نسخه‌ی ربات",
                               [f"🏷 نسخه: <b>{BOT_VERSION}</b>", f"📅 تاریخ: <b>{BOT_VERSION_DATE}</b>"],
                               ["برای آپدیت، روی سرور ربات بزنید:", "<code>tifusi bot</code>",
                                "و گزینه‌ی «Update bot» را انتخاب کنید."],
                               note="تنظیمات و دیتابیس حفظ می‌شوند؛ برای اطمینان قبلش از «💾 بکاپ» یک نسخه بگیرید."),
                   [[btn("💾 بکاپ", "admin:backup")], back_row("admin:g:update")])
    elif what == "backup":
        await admin_backup_menu(query)
    elif what == "broadcast":
        db.set_state(uid, "broadcast_msg")
        await safe_edit(query,
            f"📣 پیام همگانی\n\nمتن پیام (یا یک عکس با کپشن) را بفرستید.\n"
            f"👥 گیرندگان: {len(db.all_user_ids())} کاربر غیرمسدود",
            reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:menu")]]))
    elif what == "channel":
        await admin_channel(query)
    elif what == "report":
        await admin_report_menu(query)
    elif what == "panels":
        await admin_panels(query)
    elif what == "plans":
        await admin_plans(query)
    elif what == "admins":
        if uid != ADMIN_ID:
            await safe_edit(query, "⛔ فقط ادمین اصلی می‌تواند ادمین اضافه یا حذف کند.",
                            reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        else:
            await admin_admins(query)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    u = db.ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
    data = query.data or ""
    if u["is_blocked"] and not is_admin(uid):
        try:
            await query.answer("⛔ حساب شما مسدود شده است.", show_alert=True)
        except Exception:
            pass
        return
    parts = data.split(":")
    cmd = parts[0]
    try:
        await query.answer()
    except Exception:
        pass

    try:
        # ---------- منوهای کاربر ----------
        if cmd == "menu":
            what = parts[1]
            if what == "back":
                db.set_state(uid, "none")
                await safe_edit(query, "🏠 منوی اصلی:", reply_markup=None)
            elif what == "buy":
                await show_buy_services(query, uid)
            elif what == "services":
                await show_services(query, uid)
            return

        if cmd == "proto":
            service = parts[1] if len(parts) > 1 else ""
            if service not in SERVICES or not pick_panel(service):
                # دکمه‌ی قدیمی یا سرویسی که الان ظرفیت/هاست ندارد
                await safe_edit(query, "❌ این سرویس الان در دسترس نیست. دوباره از «خرید اشتراک» شروع کنید.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:buy")]]))
                return
            await show_plans(query, uid, service)
            return

        if cmd == "plan":
            state, sd = db.get_state(uid)
            plan = user_plan(int(parts[1]), uid) if len(parts) > 1 and parts[1].isdigit() else None
            service = sd.get("protocol")
            if (state != "buy_plan" or service not in SERVICES or not plan or not plan["active"]
                    or not plan_fits(plan, service)):
                await safe_edit(query, "❌ جلسه خرید منقضی شده. دوباره از «خرید اشتراک» شروع کنید.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔐 خرید اشتراک", "menu:buy")]]))
                return
            sd["plan_id"] = plan["id"]
            db.set_state(uid, "buy_username", sd)
            await safe_edit(query,
                f"👤 انتخاب نام کاربری\n\n🧩 {SERVICES[service]}\n📦 {plan_label(plan)}\n\n"
                "یک نام کاربری دلخواه ارسال کنید\n\n"
                "⚠️ فقط حروف انگلیسی، عدد و _ ؛ با حرف شروع شود؛ ۳ تا ۲۰ کاراکتر\n\n"
                "✅ نام‌های صحیح: ali12 | mahdi | ws1_ksdf\n"
                "❌ نام‌های نادرست: al | tele@ | محسن | _mahdi",
                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", f"proto:{service}")]]))
            return

        if cmd == "bpw":
            state, sd = db.get_state(uid)
            plan = user_plan(sd.get("plan_id"), uid)
            if state != "buy_password" or not plan or sd.get("protocol") not in SERVICES or not sd.get("username"):
                await safe_edit(query, "❌ جلسه خرید منقضی شده. دوباره از «خرید اشتراک» شروع کنید.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔐 خرید اشتراک", "menu:buy")]]))
                return
            sd["ipsec_password"] = random_ipsec_password()
            db.set_state(uid, "buy_pay", sd)
            await safe_edit(query, invoice_text(sd, plan), reply_markup=pay_kb(), parse_mode="Markdown")
            return

        if cmd == "pay":
            state, sd = db.get_state(uid)
            plan = user_plan(sd.get("plan_id"), uid)
            if not plan or not sd.get("username") or sd.get("protocol") not in SERVICES:
                await safe_edit(query, "❌ جلسه خرید منقضی شده. دوباره شروع کنید.", reply_markup=back_kb())
                db.set_state(uid, "none")
                return
            if parts[1] == "wallet":
                await finalize_wallet_purchase(query, context, uid, sd)
            else:
                db.set_state(uid, "buy_card_wait_receipt", sd)
                await safe_edit(query, card_info_text(plan["price"]),
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "menu:buy")]]))
            return

        if cmd == "svc":
            await show_service_detail(query, uid, int(parts[1]))
            return

        if cmd == "svcp":
            await show_services(query, uid, int(parts[1]), parts[2] if len(parts) > 2 and parts[2] else None)
            return

        if cmd == "svcq":
            db.set_state(uid, "svc_search")
            await safe_edit(query, "🔎 جستجو سریع\n\nنام سرویس (یا بخشی از آن) را بفرستید:",
                            reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:services")]]))
            return

        if cmd == "andr":
            o = db.get_order(int(parts[1]))
            if not o or (o["user_id"] != uid and not is_admin(uid)) or o["protocol"] not in ("ikev2", "l2tp", "pptp"):
                return
            links = None
            panel = db.get_panel(o["panel_id"])
            if panel:
                try:
                    links = await asyncio.to_thread(panel_client(panel).links, o["username"])
                except PanelError as e:
                    log.warning("android details for %s failed: %s", o["username"], e)
            text = android_html(o, links)
            psk_row = ([[InlineKeyboardButton(PSK_BTN, callback_data=f"andpsk:{o['id']}")]]
                       if "ikev2" in android_info(o, links)["kinds"] else [])
            markup = InlineKeyboardMarkup(android_copy_rows(o, links) + psk_row
                                          + [[InlineKeyboardButton("🔙 بازگشت به سرویس", callback_data=f"svc:{o['id']}")]])
            msg = query.message
            png = await asyncio.to_thread(android_png, android_info(o, links))
            if png and msg:
                # The picture carries the values; the copy buttons under it copy them in one tap.
                cap = None  # the picture says it: «Android connect», and copy with the buttons below
                try:
                    if msg.photo and (msg.caption or "").startswith(STATUS_MARK):
                        # On the «My services» picture: switch it in place; «back» switches it back.
                        from telegram import InputMediaPhoto
                        await query.edit_message_media(InputMediaPhoto(png, caption=cap), reply_markup=markup)
                    else:
                        await msg.reply_photo(png, caption=cap, reply_markup=markup)
                    return
                except Exception as e:
                    log.warning("android picture for order %s failed: %s", o["id"], e)
            # No picture: the text version, as a new message under the card or in place on «My services».
            if msg and msg.photo and not (msg.caption or "").startswith(STATUS_MARK):
                await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)
            else:
                await safe_edit(query, text, reply_markup=markup, parse_mode="HTML")
            return

        if cmd == "andpsk":
            o = db.get_order(int(parts[1]))
            if not o or (o["user_id"] != uid and not is_admin(uid)) or o["protocol"] not in ("ikev2", "l2tp", "pptp"):
                return
            links = None
            panel = db.get_panel(o["panel_id"])
            if panel:
                try:
                    links = await asyncio.to_thread(panel_client(panel).links, o["username"])
                except PanelError as e:
                    log.warning("PSK details for %s failed: %s", o["username"], e)
            text, rows = android_psk(o, links)
            markup = InlineKeyboardMarkup(rows + [[InlineKeyboardButton("🔙 بازگشت", callback_data=f"andr:{o['id']}")]])
            msg = query.message
            if msg and msg.photo:
                await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)
            else:
                await safe_edit(query, text, reply_markup=markup, parse_mode="HTML")
            return

        if cmd == "how":
            kind, o = parts[1], db.get_order(int(parts[2]))
            # The admin may open any customer's guide to see exactly what they see.
            if not o or (o["user_id"] != uid and not is_admin(uid)) or kind not in GUIDE_LABELS:
                return
            links = None
            panel = db.get_panel(o["panel_id"])
            if panel:
                try:
                    links = await asyncio.to_thread(panel_client(panel).links, o["username"])
                except PanelError as e:
                    log.warning("guide links for %s failed: %s", o["username"], e)
            text = guide_html(o, links, kind)
            markup = guide_markup(o["id"], guide_kinds(o, links), current=kind)
            png = await asyncio.to_thread(guide_png, kind, guide_cfg(o, links, kind))
            msg = query.message
            # The service card's caption starts with ✅; any other photo here is a guide picture.
            in_guide = bool(msg and msg.photo and not (msg.caption or "").startswith("✅"))
            try:
                if in_guide and png:
                    # Switch the same message, picture and caption together, so the chat stays tidy.
                    from telegram import InputMediaPhoto
                    await query.edit_message_media(InputMediaPhoto(png, caption=text, parse_mode="HTML"), reply_markup=markup)
                elif png:
                    await msg.reply_photo(png, caption=text, parse_mode="HTML", reply_markup=markup)
                elif in_guide:
                    await query.edit_message_caption(caption=text, parse_mode="HTML", reply_markup=markup)
                elif msg and msg.photo:
                    await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)
                else:
                    await safe_edit(query, text, reply_markup=markup, parse_mode="HTML")
            except Exception as e:
                log.warning("guide %s for order %s failed: %s", kind, o["id"], e)
                await msg.reply_text(text, parse_mode="HTML", reply_markup=markup)
            return

        if cmd == "qr":
            o = db.get_order(int(parts[1]))
            if o and o["user_id"] == uid and o["status"] == "active":
                if not await send_order_qr(context, uid, o):
                    await query.message.reply_text("❌ ساخت QR code ممکن نشد؛ لینک اشتراک را از متن سرویس کپی کنید.")
            return

        if cmd == "renew":
            await renew_menu(query, uid, int(parts[1]))
            return

        if cmd == "rpl":
            await renew_pay_menu(query, uid, int(parts[1]), int(parts[2]))
            return

        if cmd == "rnw":
            oid = int(parts[2])
            pid = int(parts[3]) if len(parts) > 3 else None
            o = db.get_order(oid)
            if not o or o["user_id"] != uid or o["status"] != "active":
                return
            # قیمت همیشه از یک پلن واقعی، فعال و مال همین سرویس می‌آید. قبلاً دکمه‌ی دست‌ساز بدون
            # شماره‌ی پلن قیمت را از خود سفارش برمی‌داشت، و اکانت تست (قیمت صفر) بی‌نهایت مجانی تمدید می‌شد.
            p = user_plan(pid, uid) if pid else None
            if not p or not p["active"] or not plan_fits(p, o["protocol"]):
                return
            price = p["price"]
            plan_id = pid
            if parts[1] == "w":
                bal_before = db.get_balance(uid)
                if not db.try_spend(uid, price):
                    await safe_edit(query, "❌ موجودی کیف پول کافی نیست.",
                        reply_markup=InlineKeyboardMarkup([[btn("💰 افزایش موجودی", "wallet:charge")],
                                                           [btn("🔙 بازگشت", f"svc:{oid}")]]))
                    return
                await safe_edit(query, "♻️ در حال تمدید...")
                try:
                    await do_renew_and_deliver(query, context, uid, oid, plan_id)
                except Exception as e:
                    db.add_balance(uid, price)
                    await context.bot.send_message(uid, f"❌ خطا در تمدید: {e}\n💰 مبلغ به کیف پول برگشت.")
                    return
                await context.bot.send_message(uid,
                    f"🧾 رسید تمدید\n\n"
                    f"💰 موجودی قبل از تمدید: {fmt(bal_before)} تومان\n"
                    f"💸 مبلغ تمدید: {fmt(price)} تومان\n"
                    f"💎 موجودی فعلی: {fmt(db.get_balance(uid))} تومان")
            else:
                db.set_state(uid, "renew_card_wait_receipt", {"order_id": oid, "price": price, "plan_id": plan_id})
                await safe_edit(query, card_info_text(price),
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", f"svc:{oid}")]]))
            return

        if cmd == "delreq":
            oid = int(parts[-1])
            if parts[1] == "yes":
                o = db.get_order(oid)
                if o and o["user_id"] == uid and o["status"] == "active":
                    db.update_order(oid, status="delreq_pending")
                    await safe_edit(query, "✅ درخواست حذف ثبت شد و برای ادمین ارسال شد.", reply_markup=back_kb())
                    notify_group(context.bot, f"🗑 درخواست حذف سرویس #{oid} — {o['username']}\n👤 {who(uid)}", topic="tickets")
                    await notify_admin(context.bot,
                        f"🗑 درخواست حذف سرویس\n👤 کاربر: {uid}\n🛍 سرویس #{oid} — {o['username']}",
                        reply_markup=InlineKeyboardMarkup([
                            [btn("✅ تایید حذف + بازگشت وجه", f"dq:ok:{oid}"),
                             btn("❌ رد درخواست", f"dq:no:{oid}")]]))
            else:
                await delreq_confirm(query, uid, oid)
            return

        if cmd == "sup":
            db.set_state(uid, "support_message")
            await safe_edit(query, "☎️ پیام یا عکس خود را ارسال کنید تا تیکت ثبت شود:",
                            reply_markup=InlineKeyboardMarkup([[btn("🏠 بازگشت به منوی اصلی", "menu:back")]]))
            return

        if cmd == "acc":
            await safe_edit(query, account_text(uid), reply_markup=InlineKeyboardMarkup([
                [btn("💰 افزایش موجودی", "wallet:charge"), btn("🔙 بازگشت", "menu:back")],
            ]))
            return

        if cmd == "ch":
            if parts[1] == "go":
                state, sd = db.get_state(uid)
                db.set_state(uid, "charge_wait_receipt", sd)
                await safe_edit(query, "📤 حالا تصویر رسید واریز را ارسال کنید:",
                                reply_markup=InlineKeyboardMarkup([[btn("❌ انصراف", "menu:back")]]))
            else:
                db.set_state(uid, "none")
                await safe_edit(query, "❌ لیست بسته شد.", reply_markup=back_kb())
            return

        if cmd == "wallet":
            db.set_state(uid, "charge_amount")
            await safe_edit(query,
                "💵 مبلغ را به تومان وارد کنید:\n\n✅ حداقل مبلغ 20,000 تومان — حداکثر 50,000,000 تومان",
                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:back")]]))
            return

        if cmd == "tut":
            key = parts[1] if len(parts) > 1 else ""
            if key not in TRAININGS:
                # «tut:menu» یا دکمه‌ی آموزشی از نسخه‌ی قبلی ربات
                await show_tutorial_menu(query)
                return
            t = TRAININGS[key]
            oses = [(k, label) for k, label in TUT_OS if k in t]
            if len(parts) == 2 and len(oses) > 1:
                buttons = [pbtn(label, f"tut:{key}:{k}") for k, label in oses] + [pbtn("🔙 بازگشت", "tut:menu")]
                await safe_edit(query, f"{t['title']}\n\nسیستم‌عامل را انتخاب کنید:",
                                reply_markup=InlineKeyboardMarkup([buttons[i:i + 2] for i in range(0, len(buttons), 2)]))
            else:
                os_key = parts[2] if len(parts) > 2 and parts[2] in dict(oses) else oses[0][0]
                back = f"tut:{key}" if len(oses) > 1 else "tut:menu"
                await safe_edit(query, t["title"] + "\n\n" + t[os_key],
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", back)]]))
            return

        if cmd == "resume":
            data = load_pending_buy(uid)
            if parts[1] != "buy" or not data:
                clear_pending_buy(uid)
                await safe_edit(query, "❌ خرید نیمه‌کاره لغو شد." if data else
                                "⌛ این خرید دیگر معتبر نیست؛ دوباره از «🔐 خرید اشتراک» شروع کنید.",
                                reply_markup=back_kb())
                return
            plan = user_plan(data.get("plan_id"), uid)
            if not plan or not plan["active"] or data.get("protocol") not in SERVICES:
                clear_pending_buy(uid)
                await safe_edit(query, "❌ این پلن دیگر فعال نیست؛ دوباره از «🔐 خرید اشتراک» انتخاب کنید.",
                                reply_markup=back_kb())
                return
            await finalize_wallet_purchase(query, context, uid, data)
            return

        # ---------- ادمین ----------
        if not is_admin(uid):
            return

        if cmd == "admin":
            await admin_dispatch(query, uid, parts)
            return

        if cmd == "bk":
            if parts[1] == "now":
                await safe_edit(query, "⏳ در حال آماده‌سازی بکاپ...")
                try:
                    await send_backup(context.bot, uid)
                except Exception as e:
                    await query.message.reply_text(f"❌ ساخت بکاپ ناموفق بود: {e}")
            elif parts[1] == "auto":
                db.set_setting("backup_auto", "0" if db.setting("backup_auto", "1") == "1" else "1")
                await admin_backup_menu(query)
            elif parts[1] == "restore":
                if uid != ADMIN_ID:
                    await safe_edit(query, "⛔ فقط ادمین اصلی می‌تواند بکاپ را بازگردانی کند.",
                                    reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:backup")]]))
                    return
                db.set_state(uid, "restore_file")
                await safe_edit(query,
                    "♻️ بازگردانی بکاپ\n\nفایل بکاپ (‎.db) را همین‌جا بفرستید.\n\n"
                    "⚠️ همه‌ی اطلاعات فعلی ربات با محتوای فایل جایگزین می‌شود. نسخه‌ی فعلی قبلش کنار دیتابیس ذخیره می‌شود.",
                    reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:backup")]]))
            elif parts[1] == "yes":
                state, sd = db.get_state(uid)
                path = sd.get("path")
                if uid != ADMIN_ID or state != "restore_confirm" or not path or not os.path.exists(path):
                    await safe_edit(query, "❌ جلسه‌ی بازگردانی منقضی شده؛ دوباره فایل را بفرستید.")
                    return
                try:
                    await asyncio.to_thread(db.restore_from, path)
                except Exception as e:
                    await safe_edit(query, f"❌ بازگردانی ناموفق بود: {e}")
                    return
                finally:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                with _clients_lock:
                    _clients.clear()
                db.set_state(uid, "none")
                t = db.totals()
                await safe_edit(query, f"✅ بکاپ بازگردانی شد.\n👤 کاربران: {t['users']} | 🧾 سفارش‌ها: {t['orders']} | ✅ فعال: {t['active']}")
            return

        if cmd == "bc":
            state, sd = db.get_state(uid)
            if parts[1] == "go" and state == "broadcast_confirm" and (sd.get("text") or sd.get("photo_id")):
                db.set_state(uid, "none")
                await safe_edit(query, "📣 ارسال شروع شد؛ نتیجه را همین‌جا گزارش می‌دهم.")
                context.application.create_task(run_broadcast(context.bot, uid, sd))
            else:
                db.set_state(uid, "none")
                await safe_edit(query, "❌ پیام همگانی لغو شد.", reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:menu")]]))
            return

        if cmd == "adm":
            if uid != ADMIN_ID:
                return
            if parts[1] == "add":
                db.set_state(uid, "adm_add")
                await safe_edit(query,
                    f"➕ افزودن ادمین\n\nآیدی عددی ادمین جدید را ارسال کنید:",
                    reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:admins")]]))
            elif parts[1] == "del":
                ads = get_admins()
                if int(parts[2]) in ads:
                    ads.remove(int(parts[2]))
                    db.set_setting("admins", json.dumps(ads))
                await admin_admins(query)
            return

        if cmd == "report":
            spans = {"day": ("گزارش امروز", 86400), "week": ("گزارش هفتگی", 7 * 86400),
                     "month": ("گزارش ماهانه", 30 * 86400)}
            title, span = spans[parts[1]]
            await page(query, report_text(title, now() - span, rich=True), [back_row("admin:report")])
            return

        if cmd == "rc":
            if parts[1] == "ok":
                await rc_approve(query, context, int(parts[2]))
            elif parts[1] == "no":
                await rc_reject(query, context, int(parts[2]))
            elif parts[1] == "block":
                r = db.get_receipt(int(parts[2]))
                if r:
                    db.x("UPDATE users SET is_blocked=1 WHERE id=?", (r["user_id"],))
                    try:
                        await context.bot.send_message(r["user_id"], "⛔ حساب شما توسط مدیریت مسدود شد.")
                    except Exception:
                        pass
                await safe_edit(query, f"⭕ کاربر {r['user_id'] if r else ''} بلاک شد.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:receipts")]]))
            elif parts[1] == "manual":
                r = db.get_receipt(int(parts[2]))
                if r:
                    db.set_state(uid, "au_amount", {"target": r["user_id"]})
                    await safe_edit(query, f"💰 مبلغ شارژ دستی برای کاربر {r['user_id']} را به تومان وارد کنید:")
            else:
                await admin_receipt_detail(query, int(parts[1]))
            return

        if cmd == "au":
            if parts[1] in ("charge", "deduct"):
                target = int(parts[2])
                u = db.get_user(target)
                if not u:
                    return
                db.set_state(uid, "au_amount", {"target": target, "mode": parts[1]})
                title = "➕ افزایش موجودی" if parts[1] == "charge" else "➖ کسر موجودی"
                await page(query, card(title, [f"👤 {h(u['full_name'] or target)}",
                                               f"💰 موجودی فعلی: <b>{fmt(u['balance'])}</b> تومان"],
                                       note="مبلغ را به تومان بفرستید (مثلاً 50000)."),
                           [[btn("🔙 انصراف", f"au:panel:{target}")]])
            elif parts[1] == "list":
                await admin_users_list(query, int(parts[2]) if len(parts) > 2 else 0, parts[3] if len(parts) > 3 else "")
            elif parts[1] in ("chargeall", "findorder"):
                db.set_state(uid, f"au_{parts[1]}", {})
                title, note = (("👥 شارژ همگانی", "مبلغ را به تومان بفرستید؛ به کیف پول همه‌ی کاربرانِ مسدودنشده اضافه می‌شود و به هر کدام پیام می‌رود.")
                               if parts[1] == "chargeall" else
                               ("🛍 جستجو سفارش", "یوزرنیم سرویس (یا بخشی از آن) یا شماره‌ی سفارش را بفرستید."))
                await page(query, card(title, note=note), [[btn("🔙 انصراف", "admin:g:users")]])
            elif parts[1] == "chargeall!" and len(parts) > 2:
                # فقط یک بار: دکمه‌ی تأیید بعد از اجرا (یا با زدن دوباره) دیگر کاری نمی‌کند
                if db.get_state(uid)[0] != "au_chargeall":
                    return
                db.set_state(uid, "none")
                amount = int(parts[2])
                ids = db.all_user_ids()
                with db.lock:
                    db.conn.execute("UPDATE users SET balance = balance + ? WHERE COALESCE(is_blocked,0)=0", (amount,))
                    db.conn.commit()
                db.set_state(uid, "none")
                await safe_edit(query, f"⏳ {fmt(amount)} تومان به {len(ids)} کاربر اضافه شد؛ در حال ارسال پیام...")
                sent = 0
                for t in ids:
                    try:
                        await context.bot.send_message(t, f"🎁 هدیه: {fmt(amount)} تومان به کیف پول شما اضافه شد.")
                        sent += 1
                    except Exception:
                        pass
                    await asyncio.sleep(0.05)
                await page(query, card("👥 شارژ همگانی", [f"✅ {fmt(amount)} تومان به {len(ids)} کاربر اضافه شد.",
                                                         f"📩 پیام به {sent} نفر رسید."]), [back_row("admin:g:users")])
            elif parts[1] == "panel":
                await admin_user_panel(query, int(parts[2]))
            elif parts[1] == "svcs":
                target = int(parts[2])
                services = db.get_user_orders(target, active_only=False)
                lines = [f"{'🟢' if o['status'] == 'active' else '⚪'} <b>#{o['id']}</b>  ·  {h(o['username'])}  ·  "
                         f"{h(order_name(o))}" for o in services]
                await page(query, card(f"🛍 سفارشات کاربر ({len(services)})", lines or ["این کاربر سفارشی ندارد."]),
                           [back_row(f"au:panel:{target}")])
            elif parts[1] != "noop" and len(parts) > 2 and parts[2].lstrip("-").isdigit():
                await admin_user_action(query, context, uid, parts[1], int(parts[2]))
            return

        if cmd == "set":
            key = parts[1]
            db.set_state(uid, "set_value", {"key": key})
            label = dict(SETTING_KEYS).get(key, key)
            await page(query, card(f"✏️ {label}", [f"مقدار فعلی: {val(db.setting(key))}"],
                                   note="مقدار جدید را بفرستید."),
                       [[btn("🔙 انصراف", "admin:channel" if key in ("channel_id", "group_id", "report_time")
                             else "admin:backup" if key == "backup_time" else "admin:settings")]])
            return

        if cmd == "tk":
            if parts[1] == "reply":
                db.set_state(uid, "ticket_reply", {"ticket_id": int(parts[2])})
                await safe_edit(query, "✍️ پاسخ خود را بنویسید (مستقیم به کاربر ارسال و تیکت بسته می‌شود):")
            elif parts[1] == "close":
                db.set_ticket(int(parts[2]), "closed")
                await safe_edit(query, f"🔒 تیکت #{parts[2]} بسته شد.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:tickets")]]))
            else:
                await admin_ticket_detail(query, int(parts[1]))
            return

        if cmd == "tgl" and parts[1] == "test_enabled":
            db.set_setting("test_enabled", "0" if db.setting("test_enabled", "0") == "1" else "1")
            await admin_settings(query)
            return

        if cmd == "dq":
            oid = int(parts[2])
            o = db.get_order(oid)
            if not o:
                return
            if not db.claim_order(oid, "delreq_pending", "deleting" if parts[1] == "ok" else "active"):
                await safe_edit(query, f"⚠️ درخواست حذف سرویس #{oid} قبلاً توسط ادمین دیگری بررسی شده است.")
                return
            if parts[1] == "ok":
                panel = db.get_panel(o["panel_id"])
                if panel:
                    try:
                        await asyncio.to_thread(panel_client(panel).del_user, o["username"])
                    except Exception as e:
                        db.claim_order(oid, "deleting", "delreq_pending")
                        # کاربر هنوز روی پنل فعال است؛ بازگشت وجه انجام نمی‌شود تا ادمین دوباره تلاش کند
                        await safe_edit(query, f"❌ حذف سرویس #{oid} از پنل ناموفق بود: {e}\n"
                                               f"درخواست باز ماند؛ بعد از رفع مشکل پنل دوباره تایید کنید.",
                                        reply_markup=InlineKeyboardMarkup([[btn("🔁 تلاش دوباره", f"dq:ok:{oid}"),
                                                                            btn("❌ رد درخواست", f"dq:no:{oid}")]]))
                        return
                # بازگشت وجه متناسب با روزهای باقی‌مانده
                refund = 0
                if o["expire_at"] > now() and o["days"]:
                    refund = min(int(o["price"]), int(o["price"] * (o["expire_at"] - now()) / (o["days"] * 86400)))
                db.update_order(oid, status="deleted")
                if refund:
                    db.add_balance(o["user_id"], refund)
                await context.bot.send_message(o["user_id"],
                    f"🗑 سرویس {o['username']} حذف شد.\n💰 مبلغ {fmt(refund)} تومان به کیف پول شما برگشت.")
                await safe_edit(query, f"✅ سرویس #{oid} حذف شد و {fmt(refund)} تومان برگشت." +
                                ("" if panel else "\n⚠️ پنل این سرویس در ربات وجود ندارد؛ اگر کاربر روی سرور مانده دستی حذفش کنید."))
            else:
                await context.bot.send_message(o["user_id"], "❌ درخواست حذف سرویس شما توسط ادمین رد شد.")
                await safe_edit(query, f"❌ درخواست حذف سرویس #{oid} رد شد.")
            return
    except Exception as e:
        log.exception("callback error")
        try:
            await query.message.reply_text(f"❌ خطا: {e}")
        except Exception:
            pass


# ---------- Callbackهای مدیریت پنل/پلن (ادمین) ----------
async def on_callback_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    if not is_admin(uid):
        try:
            await query.answer("⛔", show_alert=True)
        except Exception:
            pass
        return
    data = query.data or ""
    parts = data.split(":")
    cmd = parts[0]
    try:
        await query.answer()
    except Exception:
        pass

    try:
        if cmd == "pb":
            if parts[1] == "add":
                # فقط Tifusi Panel پشتیبانی می‌شود؛ انتخاب نوع پنل لازم نیست
                db.set_state(uid, "ap_name", {})
                await safe_edit(query, "➕ افزودن Tifusi Panel\n\n۱) نام پنل را وارد کنید (مثلاً «سرور آلمان ۱»):",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 انصراف", "admin:panels")]]))
            elif parts[1] == "test":
                await admin_panel_test(query, int(parts[2]))
            elif parts[1] == "toggle":
                pid = int(parts[2])
                p = db.get_panel(pid)
                newst = "inactive" if p["status"] == "active" else "active"
                db.update_panel(pid, status=newst)
                await admin_panel_detail(query, pid)
            elif parts[1] == "edit":
                await admin_panel_edit(query, int(parts[2]))
            elif parts[1] == "del":
                kb = InlineKeyboardMarkup([
                    [btn("✅ بله، حذف شود", f"pb:delyes:{parts[2]}"), btn("❌ انصراف", f"pb:{parts[2]}")]])
                await safe_edit(query,
                    "🗑 پنل حذف شود؟\n⚠️ سرویس‌های قبلی کاربران دست‌نخورده می‌مانند ولی دیگر قابل مدیریت از ربات نیستند.",
                    reply_markup=kb)
            elif parts[1] == "delyes":
                db.delete_panel(int(parts[2]))
                await safe_edit(query, "✅ پنل حذف شد.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:panels")]]))
            else:
                await admin_panel_detail(query, int(parts[1]))
            return

        if cmd == "pbe":
            pid, field = int(parts[1]), parts[2]
            db.set_state(uid, "ae_value", {"panel_id": pid, "field": field})
            await safe_edit(query, f"✏️ مقدار جدید «{field}» را ارسال کنید:")
            return

        if cmd == "pbm":
            # انتخاب مجدد گروه سرویس‌ها برای پنل موجود — گروه‌ها تازه از خود پنل خوانده می‌شوند
            pid = int(parts[1])
            p = db.get_panel(pid)
            if not p:
                await safe_edit(query, "❌ این پنل حذف شده است.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:panels")]]))
                return
            await safe_edit(query, f"🔄 در حال دریافت پروتکل‌ها و گروه‌های پنل {p['name']}...")
            try:
                await asyncio.to_thread(refresh_panel, p)
                groups = await asyncio.to_thread(panel_client(p).list_groups)
            except Exception as e:
                await safe_edit(query, f"❌ اتصال ناموفق: {e}",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", f"pb:{pid}")]]))
                return
            p = db.get_panel(pid)
            services = mappable_services(panel_protocols(p))
            if not services:
                await safe_edit(query, "⚠️ روی این پنل هنوز هیچ هاستی تعریف نشده؛ اول در پنل هاست بسازید.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", f"pb:{pid}")]]))
                return
            rows = db.get_service_rows(pid)
            current = {k: (("«" + (r["remark"] or "-") + "»") if r["enabled"] else "فروخته نمی‌شود") for k, r in rows.items()}
            sd = {"panel_id": pid, "groups": groups, "services": services, "map": {}, "step": 0, "current": current}
            db.set_state(uid, "pm_map", sd)
            text, kb = map_step_view(sd)
            await safe_edit(query, text, reply_markup=kb)
            return

        if cmd == "apm":
            state, sd = db.get_state(uid)
            keys = sd.get("services", [])
            step = sd.get("step", 0)
            if state not in ("ap_map", "pm_map") or step >= len(keys) or len(parts) < 3 or parts[1] != keys[step]:
                return  # دکمه‌ی قدیمی یا دوبار زده‌شده
            if parts[2] == "x":
                sd["map"][parts[1]] = None
            else:
                g = next((g for g in sd["groups"] if str(g["id"]) == parts[2]), None)
                if not g:
                    return
                sd["map"][parts[1]] = g
            sd["step"] = step + 1
            if sd["step"] < len(keys):
                db.set_state(uid, state, sd)
                text, kb = map_step_view(sd)
                await safe_edit(query, text, reply_markup=kb)
            elif state == "ap_map":
                db.set_state(uid, "ap_location", sd)
                await safe_edit(query, "✅ گروه سرویس‌ها انتخاب شد.\n\n📍 موقعیت پنل را وارد کنید (مثلاً 🇩🇪 آلمان):")
            else:
                db.set_service_map(sd["panel_id"], sd["map"])
                db.set_state(uid, "none")
                await admin_panel_detail(query, sd["panel_id"])
            return

        if cmd == "pl":
            if parts[1] == "noop":
                return
            if parts[1] == "add" and len(parts) == 2:
                await safe_edit(query, "➕ افزودن پلن\n\nاین پلن برای کدام سرویس است؟",
                                reply_markup=plan_service_kb("pl:add", "admin:plans"))
            elif parts[1] == "add" and parts[2] in SERVICES:
                db.set_state(uid, "plan_add_title", {"service": parts[2]})
                await safe_edit(query, f"➕ افزودن پلن {SERVICES[parts[2]]}\n\n"
                                       "1) عنوان پلن را بنویسید (مثلاً: 20 گیگ یک کاربره یک ماهه یا نامحدود دو کاربره یک ماهه):")
            elif parts[1] == "svc" and len(parts) == 3:
                pid = int(parts[2])
                await safe_edit(query, f"🧩 سرویس پلن #{pid} را انتخاب کنید:",
                                reply_markup=plan_service_kb(f"pl:setsvc:{pid}", f"pl:{pid}"))
            elif parts[1] == "setsvc" and parts[3] in SERVICES:
                pid = int(parts[2])
                db.update_plan(pid, service=parts[3])
                await admin_plan_detail(query, pid)
            elif parts[1] == "toggle":
                pid = int(parts[2])
                p = db.get_plan(pid)
                db.update_plan(pid, active=0 if p["active"] else 1)
                await admin_plan_detail(query, pid)
            elif parts[1] == "del":
                db.delete_plan(int(parts[2]))
                await safe_edit(query, "✅ پلن حذف شد.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:plans")]]))
            else:
                await admin_plan_detail(query, int(parts[1]))
            return

        if cmd == "ple":
            pid, field = int(parts[1]), parts[2]
            db.set_state(uid, "plan_edit_value", {"plan_id": pid, "field": field})
            await safe_edit(query, f"✏️ مقدار جدید «{field}» را وارد کنید:")
            return
    except Exception as e:
        log.exception("admin callback error")
        try:
            await query.message.reply_text(f"❌ خطا: {e}")
        except Exception:
            pass


# =================== مسیریاب پیام‌ها (Stateها در دیتابیس) ===================
async def handle_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state, sd):
    msg = update.message
    uid = update.effective_user.id
    text = (msg.text or "").strip()

    # ---------- خرید ----------
    if state == "buy_username":
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{2,19}", text):
            await msg.reply_text("❌ نام کاربری نامعتبر است.\nباید با حرف انگلیسی شروع شود، ۳ تا ۲۰ کاراکتر، فقط حروف انگلیسی، عدد و _ :")
            return True
        plan = user_plan(sd.get("plan_id"), uid)
        service = sd.get("protocol")
        panel = pick_panel(service) if plan and service in SERVICES else None
        if not panel:
            db.set_state(uid, "none")
            await msg.reply_text("❌ این سرویس الان ظرفیت ندارد یا جلسه خرید منقضی شده. دوباره از «🔐 خرید اشتراک» شروع کنید.",
                                 reply_markup=main_menu_kb(uid))
            return True
        # چک تکراری نبودن یوزرنیم روی همان پنلی که سرویس روی آن ساخته می‌شود
        try:
            if await asyncio.to_thread(panel_client(panel).find_user, text):
                await msg.reply_text("❌ این یوزرنیم قبلاً روی سرور استفاده شده. لطفاً یوزرنیم دیگری انتخاب کنید:")
                return True
        except PanelError as e:
            await msg.reply_text(f"❌ ارتباط با سرور برقرار نشد ({e}). چند لحظه بعد دوباره یوزرنیم را بفرستید:")
            return True
        sd["username"] = text
        sd["panel_id"] = panel["id"]
        if service in IPSEC_SERVICES:
            db.set_state(uid, "buy_password", sd)
            await msg.reply_text(password_prompt_text(service), reply_markup=password_prompt_kb(service))
            return True
        db.set_state(uid, "buy_pay", sd)
        await msg.reply_text(invoice_text(sd, plan), reply_markup=pay_kb(), parse_mode="Markdown")
        return True

    if state == "buy_password":
        # کیبورد فارسی ارقام ۰-۹ فارسی می‌فرستد
        text = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        if not IPSEC_PASSWORD_RE.fullmatch(text):
            await msg.reply_text(f"❌ رمز نامعتبر است.\n{IPSEC_PASSWORD_RULES}\n\nدوباره ارسال کنید:",
                                 reply_markup=password_prompt_kb(sd.get("protocol")) if sd.get("protocol") in SERVICES else None)
            return True
        plan = user_plan(sd.get("plan_id"), uid)
        if not plan or sd.get("protocol") not in SERVICES or not sd.get("username"):
            db.set_state(uid, "none")
            await msg.reply_text("❌ جلسه خرید منقضی شده. دوباره از «🔐 خرید اشتراک» شروع کنید.",
                                 reply_markup=main_menu_kb(uid))
            return True
        sd["ipsec_password"] = text
        db.set_state(uid, "buy_pay", sd)
        await msg.reply_text(invoice_text(sd, plan), reply_markup=pay_kb(), parse_mode="Markdown")
        return True

    # ---------- شارژ کیف پول ----------
    if state == "charge_amount":
        try:
            amount = int(text.replace(",", "").replace("٬", ""))
        except ValueError:
            await msg.reply_text("❌ فقط عدد وارد کنید (به تومان):")
            return True
        if not (20000 <= amount <= 50000000):
            await msg.reply_text("❌ مبلغ باید بین ۲۰٬۰۰۰ تا ۵۰٬۰۰۰٬۰۰۰ تومان باشد:")
            return True
        db.set_state(uid, "charge_confirm", {"amount": amount})
        await msg.reply_text(card_charge_text(amount), reply_markup=InlineKeyboardMarkup([
            [btn("✅ ادامه مراحل", "ch:go")],
            [btn("❌ بستن لیست", "ch:cancel")],
        ]))
        return True

    # ---------- پشتیبانی ----------
    if state == "svc_search":
        q = re.sub(r"[^A-Za-z0-9_]", "", text)[:20]
        if not q:
            await msg.reply_text("❌ نام سرویس فقط حروف انگلیسی، عدد و _ دارد. دوباره بفرستید:")
            return True
        db.set_state(uid, "none")
        await show_services(FakeQuery(msg), uid, 0, q)
        return True

    if state == "support_message":
        tid = db.create_ticket(uid, text)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ تیکت #{tid} ثبت شد. به‌زودی پاسخ می‌گیرید.", reply_markup=main_menu_kb(uid))
        notify_group(context.bot, f"🎫 تیکت جدید #{tid}\n👤 {who(uid)}", topic="tickets")
        await notify_admin(context.bot, f"🎫 تیکت جدید #{tid} از کاربر {uid}:\n\n{text}",
            reply_markup=InlineKeyboardMarkup([[btn("✍️ پاسخ", f"tk:reply:{tid}"), btn("🔒 بستن", f"tk:close:{tid}")]]))
        return True

    # ---------- ادمین اصلی: افزودن ادمین ----------
    if state == "adm_add" and uid == ADMIN_ID:
        try:
            new_admin = int(text)
        except ValueError:
            await msg.reply_text("❌ فقط آیدی عددی وارد کنید:")
            return True
        ads = get_admins()
        if new_admin != ADMIN_ID and new_admin not in ads:
            ads.append(new_admin)
            db.set_setting("admins", json.dumps(ads))
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ ادمین {new_admin} با دسترسی کامل اضافه شد.")
        return True

    # ---------- ادمین: جستجوی کاربر ----------
    if state == "au_search" and is_admin(uid):
        u = db.find_user(text)
        db.set_state(uid, "none")
        if not u:
            await msg.reply_text("❌ کاربر یافت نشد.")
            return True
        await admin_user_panel(FakeQuery(msg), u["id"])
        return True

    if state == "au_amount" and is_admin(uid):
        digits = text.replace(",", "").replace("،", "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        if not digits.isdigit() or int(digits) <= 0:
            await msg.reply_text("❌ فقط یک عدد بزرگ‌تر از صفر بفرستید (مثلاً 50000):")
            return True
        amount = int(digits)
        target = sd["target"]
        if sd.get("mode") == "deduct":
            if not db.try_spend(target, amount):
                await msg.reply_text(f"❌ موجودی کاربر کمتر از {fmt(amount)} تومان است؛ مبلغ کمتری بفرستید:")
                return True
            db.set_state(uid, "none")
            await msg.reply_text(f"✅ {fmt(amount)} تومان از کیف پول کاربر کم شد.")
        else:
            db.add_balance(target, amount)
            db.set_state(uid, "none")
            await msg.reply_text(f"✅ {fmt(amount)} تومان به کیف پول کاربر اضافه شد.")
            try:
                await context.bot.send_message(target, f"💰 کیف پول شما {fmt(amount)} تومان شارژ شد (شارژ دستی).")
            except Exception:
                pass
            await offer_pending_buy(context.bot, target)
        await admin_user_panel(FakeQuery(msg), target)
        return True

    if state == "au_chargeall" and is_admin(uid):
        num = text.replace(",", "").replace("،", "").strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        if not num.isdigit() or int(num) <= 0:
            await msg.reply_text("❌ فقط یک عدد بزرگ‌تر از صفر بفرستید (مثلاً 10000):")
            return True
        n = len(db.all_user_ids())
        await msg.reply_text(f"⚠️ {fmt(int(num))} تومان به کیف پول {n} کاربر اضافه شود؟ (جمع: {fmt(int(num) * n)} تومان)",
                             reply_markup=InlineKeyboardMarkup([[btn("✅ بله، شارژ کن", f"au:chargeall!:{int(num)}")],
                                                                [btn("🔙 انصراف", "admin:g:users")]]))
        return True

    if state == "au_findorder" and is_admin(uid):
        q = text.strip().lstrip("#")
        found = db.q("SELECT * FROM orders WHERE id=? OR username LIKE ? ORDER BY id DESC LIMIT 15",
                     (int(q) if q.isdigit() else -1, f"%{q}%"))
        db.set_state(uid, "none")
        if not found:
            await msg.reply_text("❌ سفارشی پیدا نشد.", reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:g:users")]]))
            return True
        st = {"active": "🟢", "deleted": "🗑", "archived": "📦"}
        rows = [[btn(f"{st.get(o['status'], '⚪')} #{o['id']} · {o['username']} · 👤 {o['user_id']}", f"au:panel:{o['user_id']}")]
                for o in found]
        await msg.reply_text(card(f"🛍 نتیجه‌ی جستجو ({len(found)})", note="روی هر سفارش بزنید تا صفحه‌ی صاحبش باز شود."),
                             reply_markup=InlineKeyboardMarkup(rows + [[btn("🔙 بازگشت", "admin:g:users")]]), parse_mode="HTML")
        return True

    if state in ("au_msg", "au_disc", "au_tlim", "au_xfer") and is_admin(uid):
        target = sd["target"]
        num = text.strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))
        if state == "au_msg":
            try:
                await context.bot.send_message(target, f"📩 پیام از پشتیبانی:\n\n{text}")
                await msg.reply_text("✅ پیام برای کاربر ارسال شد.")
            except Exception as e:
                await msg.reply_text(f"❌ ارسال نشد (احتمالاً کاربر ربات را بلاک کرده): {e}")
        elif state == "au_disc":
            if not num.isdigit() or int(num) > 100:
                await msg.reply_text("❌ یک عدد از ۰ تا ۱۰۰ بفرستید:")
                return True
            db.x("UPDATE users SET discount_pct=? WHERE id=?", (int(num), target))
            await msg.reply_text(f"✅ تخفیف این کاربر {int(num)}٪ شد؛ روی خرید و تمدیدهای بعدی‌اش اعمال می‌شود.")
        elif state == "au_tlim":
            if not num.isdigit() or int(num) > 20:
                await msg.reply_text("❌ یک عدد از ۰ تا ۲۰ بفرستید:")
                return True
            db.x("UPDATE users SET test_limit=? WHERE id=?", (int(num), target))
            await msg.reply_text(f"✅ سقف اکانت تست این کاربر {int(num)} شد.")
        else:
            dest = db.get_user(int(num)) if num.isdigit() else None
            if not dest or dest["id"] == target:
                await msg.reply_text("❌ حساب مقصد پیدا نشد (باید یک بار ربات را استارت کرده باشد). آیدی عددی دیگری بفرستید:")
                return True
            src = db.get_user(target)
            with db.lock:
                db.conn.execute("UPDATE orders SET user_id=? WHERE user_id=?", (dest["id"], target))
                db.conn.execute("UPDATE users SET balance=balance+? WHERE id=?", (int(src["balance"] or 0), dest["id"]))
                db.conn.execute("UPDATE users SET balance=0 WHERE id=?", (target,))
                db.conn.commit()
            await msg.reply_text(f"✅ موجودی ({fmt(src['balance'] or 0)} تومان) و همه‌ی سرویس‌ها به حساب {dest['id']} منتقل شد.")
            db.set_state(uid, "none")
            await admin_user_panel(FakeQuery(msg), dest["id"])
            return True
        db.set_state(uid, "none")
        await admin_user_panel(FakeQuery(msg), target)
        return True

    # ---------- ادمین: تنظیمات ----------
    if state == "set_value" and is_admin(uid):
        if sd["key"] in ("test_volume_gb", "test_days") and not (text.isdigit() and int(text) > 0):
            await msg.reply_text("❌ یک عدد بزرگ‌تر از صفر وارد کنید:")
            return True
        if sd["key"] in DAILY_TIMES:
            hhmm = parse_hhmm(text)
            if not hhmm:
                await msg.reply_text("❌ ساعت را به شکل ۰۶:۳۰ یا ۲۳:۰۰ (وقت ایران) بفرستید:")
                return True
            db.set_setting(sd["key"], hhmm)
            schedule_daily_jobs(context.job_queue)
            db.set_state(uid, "none")
            await msg.reply_text(f"✅ «{dict(SETTING_KEYS)[sd['key']]}» شد {hhmm}. از همین امروز اعمال می‌شود.")
            return True
        db.set_setting(sd["key"], text)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ «{dict(SETTING_KEYS).get(sd['key'], sd['key'])}» ذخیره شد.")
        return True

    # ---------- ادمین: پاسخ تیکت ----------
    if state == "ticket_reply" and is_admin(uid):
        t = db.get_ticket(sd["ticket_id"])
        db.set_ticket(sd["ticket_id"], "closed", reply=text)
        db.set_state(uid, "none")
        if t:
            try:
                await context.bot.send_message(t["user_id"],
                    f"☎️ پاسخ پشتیبانی به تیکت #{t['id']}:\n\n{text}")
            except Exception:
                pass
        await msg.reply_text("✅ پاسخ ارسال و تیکت بسته شد.")
        return True

    # ---------- ادمین: پلن ----------
    if state == "plan_add_title" and is_admin(uid):
        sd["title"] = text
        db.set_state(uid, "plan_add_price", sd)
        await msg.reply_text("۲) قیمت را به تومان وارد کنید (مثلاً 140000):")
        return True

    if state == "plan_add_price" and is_admin(uid):
        if not text.isdigit():
            await msg.reply_text("❌ عدد وارد کنید:")
            return True
        sd["price"] = int(text)
        db.set_state(uid, "plan_add_days", sd)
        await msg.reply_text("۳) مدت را به روز وارد کنید (مثلاً 30):")
        return True

    if state == "plan_add_days" and is_admin(uid):
        if not text.isdigit():
            await msg.reply_text("❌ عدد وارد کنید:")
            return True
        sd["days"] = int(text)
        db.set_state(uid, "plan_add_users", sd)
        await msg.reply_text("۴) این پلن چند کاربره باشد؟ (عدد 0 تا 5)\n\n"
                             "یعنی حداکثر چند دستگاه بتوانند همزمان با این اکانت وصل شوند؛ دستگاه اضافه تا خالی شدن جا منتظر می‌ماند.\n"
                             "۰ یعنی بدون محدودیت.")
        return True

    if state == "plan_add_users" and is_admin(uid):
        if not text.isdigit() or not (0 <= int(text) <= 5):
            await msg.reply_text("❌ عددی بین 0 تا 5 وارد کنید:")
            return True
        vol = parse_volume_from_title(sd.get("title", ""))
        service = sd.get("service") if sd.get("service") in SERVICES else ""
        db.add_plan(vol, sd["days"], sd["price"], sd.get("title", ""), int(text), service)
        db.set_state(uid, "none")
        ul_txt = f"{text} کاربره" if int(text) else "بدون محدودیت"
        await msg.reply_text(f"✅ پلن {SERVICES.get(service, '')} «{sd.get('title')}» — {fmt(sd['price'])} تومان — "
                             f"{sd['days']} روز — 👥 {ul_txt} اضافه شد.")
        return True

    if state == "plan_edit_value" and is_admin(uid):
        if sd["field"] == "title":
            db.update_plan(sd["plan_id"], title=text)
            db.set_state(uid, "none")
            await msg.reply_text("✅ عنوان پلن به‌روزرسانی شد.")
            return True
        if not text.isdigit():
            await msg.reply_text("❌ عدد وارد کنید:")
            return True
        if sd["field"] == "user_limit" and not (0 <= int(text) <= 5):
            await msg.reply_text("❌ تعداد کاربر باید بین 0 تا 5 باشد (۰ = بدون محدودیت):")
            return True
        db.update_plan(sd["plan_id"], **{sd["field"]: int(text)})
        db.set_state(uid, "none")
        await msg.reply_text("✅ پلن به‌روزرسانی شد.")
        return True

    # ---------- ادمین: جادوی افزودن پنل ----------
    if state == "ap_name" and is_admin(uid):
        sd["name"] = text
        db.set_state(uid, "ap_url", sd)
        await msg.reply_text("۲) آدرس پنل را وارد کنید (مثلاً https://panel1.example.com:8000):")
        return True

    if state == "ap_url" and is_admin(uid):
        if not text.startswith("http"):
            await msg.reply_text("❌ آدرس باید با http یا https شروع شود:")
            return True
        sd["url"] = text.rstrip("/")
        db.set_state(uid, "ap_user", sd)
        await msg.reply_text("۳) یوزرنیم لاگین پنل:")
        return True

    if state == "ap_user" and is_admin(uid):
        sd["username"] = text
        db.set_state(uid, "ap_pass", sd)
        await msg.reply_text("۴) پسورد لاگین پنل:")
        return True

    if state == "ap_pass" and is_admin(uid):
        sd["password"] = text
        wait = await msg.reply_text("🔄 در حال تست اتصال و خواندن پروتکل‌ها و گروه‌های پنل...")
        try:
            client = TifusiPanelAPI(sd["url"], sd["username"], sd["password"])
            await asyncio.to_thread(client.login)
            protocols = await asyncio.to_thread(client.list_protocols)
            groups = await asyncio.to_thread(client.list_groups)
        except Exception as e:
            await wait.edit_text(f"❌ اتصال ناموفق: {e}\n\nاز اول شروع کنید: 🖥 مدیریت پنل‌ها ← ➕ افزودن پنل")
            db.set_state(uid, "none")
            return True
        services = mappable_services(protocols)
        found = "، ".join(f"{p} ({n})" for p, n in protocols.items()) or "هیچ هاستی تعریف نشده"
        sd.update({"groups": groups, "services": services, "map": {}, "step": 0,
                   "protocols": protocols, "tls_insecure": client.insecure})
        warn = "\n⚠️ گواهی SSL پنل معتبر نیست (self-signed)." if client.insecure else ""
        if not services:
            db.set_state(uid, "ap_location", sd)
            await wait.edit_text(f"✅ اتصال موفق!{warn}\n📡 پروتکل‌ها: {found}\n\n"
                                 "⚠️ روی این پنل هنوز هاستی نیست؛ پنل ثبت می‌شود و بعد از ساخت هاست، «🔄 بررسی اتصال» را بزنید.\n\n"
                                 "📍 موقعیت پنل را وارد کنید (مثلاً 🇩🇪 آلمان):")
            return True
        db.set_state(uid, "ap_map", sd)
        view_text, kb = map_step_view(sd)
        await wait.edit_text(f"✅ اتصال موفق!{warn}\n📡 پروتکل‌های پنل: {found}\n\n" + view_text, reply_markup=kb)
        return True

    if state == "ap_location" and is_admin(uid):
        sd["location"] = text
        db.set_state(uid, "ap_maxusers", sd)
        await msg.reply_text(
            f"👥 سقف تعداد کاربر این پنل را بنویسید (مثلاً 200):\n\n"
            f"وقتی پنل به این عدد برسد، فقط «خریدهای جدید» می‌روند پنل بعدی؛ "
            f"تمدید سرویس‌های همین پنل همیشه فعال می‌ماند.\n"
            f"اگر نمی‌دانید بنویسید: - (پیش‌فرض = {DEFAULT_PANEL_MAX_USERS})")
        return True

    if state == "ap_maxusers" and is_admin(uid):
        if text.strip() in ("-", "ندارم", "skip"):
            sd["max_users"] = DEFAULT_PANEL_MAX_USERS
        elif text.isdigit():
            sd["max_users"] = int(text)
        else:
            await msg.reply_text("❌ عدد وارد کنید (یا - برای پیش‌فرض):")
            return True
        sd["status"] = "active"
        await finish_panel_wizard(msg, uid, sd)
        return True

    # ---------- ادمین: ویرایش پنل ----------
    if state == "ae_value" and is_admin(uid):
        field, pid = sd["field"], sd["panel_id"]
        if field == "max_users" and not (text.isdigit() and int(text) > 0):
            await msg.reply_text("❌ سقف کاربر باید عدد بزرگ‌تر از صفر باشد:")
            return True
        if field == "url" and not text.startswith("http"):
            await msg.reply_text("❌ آدرس باید با http یا https شروع شود:")
            return True
        if field not in ("name", "url", "username", "password", "location", "max_users"):
            db.set_state(uid, "none")
            return True
        val = int(text) if field == "max_users" else (text.rstrip("/") if field == "url" else text)
        db.update_panel(pid, **{field: val})
        db.set_state(uid, "none")
        await msg.reply_text("✅ پنل به‌روزرسانی شد.")
        return True

    # ---------- ادمین: پیام همگانی ----------
    if state == "broadcast_msg" and is_admin(uid):
        if len(text) > 4000:
            await msg.reply_text(f"❌ متن {len(text)} کاراکتر است؛ حداکثر ۴۰۰۰ کاراکتر مجاز است. کوتاه‌تر بفرستید:")
            return True
        if not text:
            await msg.reply_text("❌ متن خالی است؛ متن یا عکس بفرستید:")
            return True
        db.set_state(uid, "broadcast_confirm", {"text": text})
        await msg.reply_text(f"👀 پیش‌نمایش پیام همگانی:\n━━━━━━━━━━━━━━━\n{text}\n━━━━━━━━━━━━━━━\n"
                             f"👥 برای {len(db.all_user_ids())} کاربر ارسال شود؟",
                             reply_markup=InlineKeyboardMarkup([[btn("✅ ارسال", "bc:go"), btn("❌ لغو", "bc:no")]]))
        return True

    return False


MENU_ACTIONS = {
    "🔐 خرید اشتراک": "buy", "♻️ تمدید سرویس": "renew_menu", "🔑 اکانت تست": "test",
    "🛍 سرویس‌های من": "services", "🏦 کیف پول + شارژ": "wallet", "🏦 کیف پول": "wallet",
    "💵 تعرفه اشتراک ها": "tariff", "💵 تعرفه‌ها": "tariff", "💵 تعرفه": "tariff",
    "👥 زیرمجموعه گیری": "referral", "👥 زیرمجموعه‌گیری": "referral",
    "📚 آموزش": "tutorial", "☎️ پشتیبانی": "support", "🧑‍💼 پنل مدیریت": "admin",
}


# مرحله‌هایی که ورودی متنی ندارند و منتظر دکمه‌اند
BUTTON_WAIT_STATES = ("buy_plan", "buy_pay", "charge_confirm", "ap_map", "pm_map", "broadcast_confirm", "restore_confirm")


class FakeQuery:
    """برای استفاده از توابع مبتنی بر query داخل پیام‌های متنی."""
    def __init__(self, message):
        self.message = message

    async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
        await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

    async def answer(self, *a, **kw):
        pass


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    u = db.ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
    if u["is_blocked"]:
        await msg.reply_text("⛔ حساب شما توسط مدیریت مسدود شده است.")
        return
    state, sd = db.get_state(uid)

    text = (msg.text or "").strip()
    if is_admin(uid) and (text in ADMIN_MENU_ACTIONS or text == ADMIN_HOME):
        db.set_state(uid, "none")
        if text == ADMIN_HOME:
            await msg.reply_text("🏠 منوی اصلی\n\nاز منوی زیر انتخاب کنید:", reply_markup=main_menu_kb(uid, force=True))
        else:
            await admin_dispatch(FakeQuery(msg), uid, ["admin", *ADMIN_MENU_ACTIONS[text].split(":")])
        return

    # خروج خودکار از هر بخش با زدن هر دکمه منوی اصلی (انصراف سراسری)
    menu_hit = MENU_ACTIONS.get((msg.text or "").strip())
    if menu_hit and state != "none":
        db.set_state(uid, "none")
        state, sd = "none", {}

    if state != "none" and state not in ("buy_card_wait_receipt", "charge_wait_receipt",
                                         "renew_card_wait_receipt"):
        if await handle_state(update, context, state, sd):
            return
        # مرحله‌ای که دیگر وجود ندارد (مثلاً از نسخه‌ی قبلی ربات) — ریست تا کاربر گیر نکند؛
        # مرحله‌هایی که منتظر زدن دکمه‌اند دست نمی‌خورند تا جلسه‌ی خرید/افزودن پنل از بین نرود
        if state not in BUTTON_WAIT_STATES:
            db.set_state(uid, "none")
            state, sd = "none", {}

    action = MENU_ACTIONS.get((msg.text or "").strip())
    if not action:
        if state == "none":
            if is_miniapp_user(uid) and not is_admin(uid):
                await send_miniapp_only(msg)
                return
            await msg.reply_text("🏠 منوی اصلی\n\nاز منوی زیر انتخاب کنید:",
                                 reply_markup=main_menu_kb(uid))
        return
    await run_menu_action(msg, context, uid, action)


async def run_menu_action(msg, context, uid, action):
    """یک دکمه‌ی منوی اصلی؛ هم از منوی پایین ربات صدا زده می‌شود و هم از مینی‌اپ (پل /api/goto)."""
    fq = FakeQuery(msg)
    if action == "buy":
        await show_buy_services(fq, uid)
    elif action == "renew_menu":
        await show_renew_menu(msg, uid)
    elif action == "test":
        await send_test_account(msg, context, uid)
    elif action == "services":
        await show_services(fq, uid)
    elif action == "wallet":
        await show_wallet(fq, uid)
    elif action == "tariff":
        await show_tariff(fq)
    elif action == "tutorial":
        await show_tutorial_menu(fq)
    elif action == "support":
        text = db.setting("faq_text") or FAQ_DEFAULT
        await msg.reply_text(text, reply_markup=InlineKeyboardMarkup([
            [btn("📮 ارسال پیام به پشتیبانی", "sup:new")],
            [btn("🏠 بازگشت به منوی اصلی", "menu:back")],
        ]))
    elif action == "referral":
        await show_referral(fq, context, uid)
    elif action == "admin":
        if is_admin(uid):
            await msg.reply_text("🧑‍💼 پنل مدیریت:\n\nاز منوی پایین صفحه انتخاب کنید.", reply_markup=admin_menu_kb())
    return


# ---------- رسیدها (عکس) ----------
async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    u = db.ensure_user(uid, update.effective_user.username, update.effective_user.full_name)
    if u["is_blocked"]:
        return
    state, sd = db.get_state(uid)
    photo_id = msg.photo[-1].file_id

    if state == "broadcast_msg" and is_admin(uid):
        if len(msg.caption or "") > 900:
            await msg.reply_text("❌ کپشن عکس حداکثر ۹۰۰ کاراکتر می‌تواند باشد؛ دوباره بفرستید:")
            return
        db.set_state(uid, "broadcast_confirm", {"photo_id": photo_id, "text": msg.caption or ""})
        await msg.reply_photo(photo_id, caption=(msg.caption or "") + f"\n\n👥 برای {len(db.all_user_ids())} کاربر ارسال شود؟",
                              reply_markup=InlineKeyboardMarkup([[btn("✅ ارسال", "bc:go"), btn("❌ لغو", "bc:no")]]))
        return

    if state == "support_message":
        tid = db.create_ticket(uid, msg.caption or "(عکس)", photo_id)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ تیکت #{tid} ثبت شد.", reply_markup=main_menu_kb(uid))
        notify_group(context.bot, f"🎫 تیکت جدید #{tid} (عکس)\n👤 {who(uid)}", topic="tickets")
        await notify_admin(context.bot, f"🎫 تیکت جدید #{tid} از کاربر {uid} (عکس)")
        return

    if state == "charge_wait_receipt":
        amount = sd["amount"]
        rid = db.create_receipt(uid, amount, "wallet_charge", photo_id)
        db.set_state(uid, "none")
        await msg.reply_text("✅ رسید شما ثبت شد و برای ادمین ارسال شد.\n⏳ بعد از تایید، کیف پول شارژ می‌شود.",
                             reply_markup=main_menu_kb(uid))
        r = db.get_receipt(rid)
        await send_receipt_to_admins(context.bot, rid, photo_id,
            receipt_caption(r, "یک پرداخت جدید انجام شده است — افزایش موجودی"))
        return

    if state == "buy_card_wait_receipt":
        plan = user_plan(sd.get("plan_id"), uid)
        # جلسه‌ی خریدِ ناقص یا از نسخه‌ی قبلی ربات (سرویسی که دیگر فروخته نمی‌شود) رسید نمی‌سازد
        if not plan or sd.get("protocol") not in SERVICES or not sd.get("username"):
            db.set_state(uid, "none")
            await msg.reply_text("❌ جلسه خرید منقضی شده یا پلن یافت نشد. دوباره از «🔐 خرید اشتراک» شروع کنید.",
                                 reply_markup=main_menu_kb(uid))
            return
        rid = db.create_receipt(uid, plan["price"], "purchase", photo_id, meta={
            "kind": "purchase", "plan_id": plan["id"], "protocol": sd["protocol"],
            "username": sd["username"], "panel_id": sd.get("panel_id"),
            "ipsec_password": sd.get("ipsec_password")})
        db.set_state(uid, "none")
        await msg.reply_text("✅ رسید شما ثبت شد.\n⏳ بعد از تایید ادمین، سرویس به‌صورت خودکار ساخته و ارسال می‌شود.",
                             reply_markup=main_menu_kb(uid))
        r = db.get_receipt(rid)
        await send_receipt_to_admins(context.bot, rid, photo_id,
            receipt_caption(r, f"رسید خرید سرویس — {plan['volume_gb']} گیگ / {plan['days']} روز / {SERVICES[sd['protocol']]} / 👤 {sd['username']}"))
        return

    if state == "renew_card_wait_receipt":
        oid, price = sd["order_id"], sd["price"]
        rid = db.create_receipt(uid, price, "renew", photo_id,
                                meta={"kind": "renew", "order_id": oid, "plan_id": sd.get("plan_id")})
        db.set_state(uid, "none")
        await msg.reply_text("✅ رسید تمدید ثبت شد.⏳ بعد از تایید ادمین، سرویس تمدید می‌شود.",
                             reply_markup=main_menu_kb(uid))
        r = db.get_receipt(rid)
        await send_receipt_to_admins(context.bot, rid, photo_id,
            receipt_caption(r, f"رسید تمدید سرویس #{oid}"))
        return


# ---------- بازگردانی بکاپ (فایل) ----------
async def on_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    uid = update.effective_user.id
    state, sd = db.get_state(uid)
    if uid != ADMIN_ID or state != "restore_file":
        return
    doc = msg.document
    if doc.file_size and doc.file_size > 20 * 1024 * 1024:
        await msg.reply_text("❌ فایل بزرگ‌تر از ۲۰ مگابایت است.")
        return
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        tg_file = await doc.get_file()
        await tg_file.download_to_drive(path)
        check = sqlite3.connect(path)
        try:
            tables = {r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"users", "orders", "panels", "plans", "settings"} <= tables:
                raise ValueError("این فایل بکاپ ربات نیست")
            users = check.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            orders = check.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        finally:
            check.close()
    except Exception as e:
        try:
            os.remove(path)
        except OSError:
            pass
        await msg.reply_text(f"❌ فایل قابل استفاده نیست: {e}")
        return
    db.set_state(uid, "restore_confirm", {"path": path})
    await msg.reply_text(
        f"♻️ فایل بکاپ معتبر است: 👤 {users} کاربر | 🧾 {orders} سفارش\n\n"
        f"⚠️ با تایید، همه‌ی اطلاعات فعلی ربات با این فایل جایگزین می‌شود. ادامه می‌دهید؟",
        reply_markup=InlineKeyboardMarkup([[btn("✅ بله، بازگردانی شود", "bk:yes"), btn("❌ انصراف", "admin:backup")]]))


# =================== جاب‌ها ===================
async def health_job(context: ContextTypes.DEFAULT_TYPE):
    """هر ۵ دقیقه: اتصال پنل‌ها + خواندن دوباره‌ی پروتکل‌ها. پنلی که جواب ندهد از فروش خارج می‌شود و
    پروتکلی که روی پنل اضافه/حذف شد بدون دخالت ادمین در ربات اعمال می‌شود (با اطلاع به ادمین)."""
    for p in db.get_panels():
        if p["status"] == "inactive":
            continue  # غیرفعال دستی — از چرخه خارج است
        try:
            before, after = await asyncio.to_thread(refresh_panel, p)
            ok = True
        except Exception as e:
            log.warning("panel %s check failed: %s", p["id"], e)
            ok, before, after = False, {}, {}
        if not ok and p["status"] == "active":
            db.update_panel(p["id"], status="offline")
            notify_group(context.bot, f"⚠️ پنل «{p['name']}» offline شد و از فروش خارج شد!", topic="status")
            await notify_admin(context.bot, f"⚠️ پنل «{p['name']}» offline شد و از فروش خارج شد!")
        elif ok and p["status"] == "offline":
            db.update_panel(p["id"], status="active")
            notify_group(context.bot, f"✅ پنل «{p['name']}» دوباره online شد.", topic="status")
            await notify_admin(context.bot, f"✅ پنل «{p['name']}» دوباره online شد.")
        if ok and p["checked_at"] and set(before) != set(after):
            fresh = db.get_panel(p["id"])
            waiting = [SERVICES[s] for s in SERVICES
                       if s not in db.get_service_rows(p["id"]) and service_protocols_on(fresh, s)]
            note = (f"\n\n⚠️ برای فروش این سرویس‌ها گروه انتخاب کنید (🖥 مدیریت پنل‌ها ← 🧩 انتخاب گروه سرویس‌ها): "
                    f"{'، '.join(waiting)}") if waiting else ""
            await notify_admin(context.bot, f"🔔 پروتکل‌های پنل «{p['name']}» تغییر کرد:\n"
                                            f"{protocols_diff_text(before, after)}{note}")


async def reminder_job(context: ContextTypes.DEFAULT_TYPE):
    """هر ساعت: یادآوری انقضا — ۳ روز مانده، ۱ روز مانده، و وقتی منقضی شد. هر یادآوری یک بار ارسال می‌شود
    و با تمدید دوباره فعال می‌شود. اکانت‌های تست (قیمت صفر) یادآوری نمی‌گیرند."""
    t = now()
    for o in db.orders_to_remind():
        if not o["price"]:
            continue
        left = o["expire_at"] - t
        sent = o["reminded"] or 0
        if left <= -2 * 86400:
            db.x("UPDATE orders SET reminded = reminded | 7 WHERE id=?", (o["id"],))
            continue
        if left <= 0 and not sent & 4:
            text, mark = f"⛔ سرویس «{o['username']}» منقضی شد.\nبرای وصل شدن دوباره، تمدیدش کنید؛ شناسه و لینک عوض نمی‌شوند.", 7
        elif 0 < left <= 86400 and not sent & 2:
            text, mark = f"⏰ فقط کمتر از یک روز از سرویس «{o['username']}» باقی مانده است.", 3
        elif 86400 < left <= 3 * 86400 and not sent & 1:
            text, mark = f"⏳ کمتر از ۳ روز از اعتبار سرویس «{o['username']}» باقی مانده است.", 1
        else:
            continue
        try:
            await context.bot.send_message(o["user_id"], text, reply_markup=InlineKeyboardMarkup([
                [btn("♻️ تمدید سرویس", f"renew:{o['id']}")]]))
        except Exception as e:
            log.info("reminder to %s failed: %s", o["user_id"], e)
        # فقط اگر در این فاصله تمدید نشده باشد (تمدید expire_at را عوض و reminded را صفر می‌کند)
        db.x("UPDATE orders SET reminded = reminded | ? WHERE id=? AND expire_at=?", (mark, o["id"], o["expire_at"]))
        await asyncio.sleep(0.05)


async def daily_backup_job(context: ContextTypes.DEFAULT_TYPE):
    if db.setting("backup_auto", "1") != "1":
        return
    targets = [ADMIN_ID]
    chat = db.setting("backup_chat_id", "").strip()
    if chat:
        targets.append(chat if chat.startswith("@") else int(chat) if chat.lstrip("-").isdigit() else chat)
    group = _chat_target(db.setting("group_id"))
    for target in targets:
        try:
            await send_backup(context.bot, target, "💾 بکاپ خودکار روزانه‌ی ربات",
                              group_thread("backup") if target == group else None)
        except Exception as e:
            log.warning("daily backup to %s failed: %s", target, e)


async def daily_report_job(context: ContextTypes.DEFAULT_TYPE):
    """گزارش خودکار هر شب ساعت ۰۰:۰۰."""
    text = report_text("گزارش روزانه", now() - 86400)
    await notify_admin(context.bot, text)
    for key in ("channel_id", "group_id"):
        target = db.setting(key)
        if target:
            try:
                await context.bot.send_message(target if target.startswith("@") else int(target), text,
                                               message_thread_id=group_thread("report") if key == "group_id" else None)
            except Exception as e:
                log.warning("report to %s failed: %s", key, e)


async def on_error(update, context):
    log.exception("خطای ربات: %s", context.error)


_user_locks = weakref.WeakValueDictionary()


def per_user(handler):
    """پیام‌های کاربرهای مختلف همزمان پردازش می‌شوند (یک خرید کند بقیه را منتظر نمی‌گذارد)، ولی پیام‌های
    یک کاربر پشت‌سرهم؛ وگرنه دو بار زدن سریع یک دکمه می‌توانست دو عملیات همزمان روی state او اجرا کند."""
    async def wrapped(update, context):
        user = update.effective_user
        if not user:
            return await handler(update, context)
        lock = _user_locks.get(user.id)
        if lock is None:
            lock = asyncio.Lock()
            _user_locks[user.id] = lock
        async with lock:
            return await handler(update, context)
    return wrapped


async def start_miniapp(application):
    """سرور مینی‌اپ (miniapp.py) کنار ربات؛ اگر نصب نبود یا بالا نیامد، ربات بدون آن کار می‌کند."""
    try:
        import miniapp
        await miniapp.start(application, globals())
    except Exception as e:
        log.warning("miniapp not started: %s", e)


async def stop_miniapp(application):
    try:
        import miniapp
        await miniapp.stop(application)
    except Exception as e:
        log.warning("miniapp stop failed: %s", e)


def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("❌ ابتدا BOT_TOKEN و ADMIN_ID را در بالای همین فایل (bot.py) پر کنید.")
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).post_init(start_miniapp).post_shutdown(stop_miniapp).build()
    app.add_handler(CommandHandler("start", per_user(start)))
    app.add_handler(CommandHandler("admin", per_user(admin_menu_cmd)))
    app.add_handler(CallbackQueryHandler(per_user(on_callback_admin), pattern=r"^(pb|pbe|pbm|apm|pl|ple):"))
    app.add_handler(CallbackQueryHandler(per_user(on_callback)))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, per_user(on_photo)))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, per_user(on_document)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, per_user(on_message)))
    app.add_error_handler(on_error)
    if app.job_queue:
        app.job_queue.run_repeating(health_job, interval=300, first=30)
        app.job_queue.run_repeating(reminder_job, interval=3600, first=120)
        schedule_daily_jobs(app.job_queue)
    else:
        log.warning("job-queue نصب نیست: چک سلامت، یادآوری انقضا و بکاپ خودکار اجرا نمی‌شوند "
                    "(pip install 'python-telegram-bot[job-queue]')")
    log.info("🤖 ربات v%s روشن شد...", BOT_VERSION)
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
