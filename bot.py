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
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
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
    "ikev2": "IKEv2",
    "l2tp": "L2TP",
    "wireguard": "WireGuard",
}
# پروتکل‌های پنل برای هر سرویس — کاربر ساخته‌شده فقط به همین پروتکل‌ها دسترسی می‌گیرد
SERVICE_PROTOCOLS = {
    "xray": ["vless", "vmess", "trojan", "shadowsocks"],
    "hysteria2": ["hysteria2"],
    "ikev2": ["ikev2"],
    "l2tp": ["l2tp"],
    "wireguard": ["wireguard"],
}
# اکانت تست روی اولین سرویسِ در دسترس به همین ترتیب ساخته می‌شود
TEST_SERVICE_ORDER = ["ikev2", "xray", "hysteria2", "l2tp", "wireguard"]
# سفارش‌های نسخه‌ی ۴.۰ که یک سرویس کلی Tifusi بودند (بدون محدودیت پروتکل)
GENERIC_ORDER_KEY = "tifusi"

APP_ANDROID_URL = "https://github.com/javadtifusi-eng/Tifusi-VPN/releases/latest/download/tifusi-vpn.apk"

# سرویس‌هایی که مشتری با نام کاربری و رمز به آن‌ها وصل می‌شود و موقع خرید رمز دلخواه می‌گیرند
IPSEC_SERVICES = {"ikev2", "l2tp"}
# همان قاعده‌ی پنل (IPSEC_PASSWORD_PATTERN): نود رمز را داخل گیومه در swanctl.conf و chap-secrets
# می‌نویسد، پس گیومه، بک‌اسلش و فاصله باعث می‌شوند IKEv2/L2TP رمز دیگری را چک کنند
IPSEC_PASSWORD_RE = re.compile(r"[A-Za-z0-9@#$%&*._+=!-]{6,32}")
IPSEC_PASSWORD_RULES = "۶ تا ۳۲ کاراکتر؛ فقط حروف انگلیسی، عدد و @ # $ % & * . _ + = ! -"


# ══════════════════════ آموزش اتصال (training) ══════════════════════

# هر آموزش فقط سیستم‌عامل‌هایی را دارد که برایش معنی دارد؛ اگر یکی باشد مستقیم همان نمایش داده می‌شود
TUT_OS = [("android", "🤖 اندروید"), ("ios", "🍎 آیفون")]

TRAININGS = {
    "app": {
        "title": "📱 اپ Tifusi VPN (اندروید)",
        "android": f"""🤖 اندروید:

1️⃣ اپ Tifusi VPN را دانلود و نصب کنید:
{APP_ANDROID_URL}
2️⃣ اپ را باز کنید و به تب «سرورها» بروید
3️⃣ «🆔 شناسه»ای که ربات فرستاده را در کادر «شناسه یا لینک اشتراک» بچسبانید و «دریافت سرورها» را بزنید
   📷 یا به‌جای آن «اسکن بارکد» را بزنید و QR code ارسالی ربات را اسکن کنید
4️⃣ به تب «خانه» برگردید، سرور را انتخاب کنید و دکمه‌ی اتصال را بزنید

💡 لینک اشتراک هم در همان کادر کار می‌کند. با تمدید سرویس، شناسه، لینک و QR عوض نمی‌شوند؛
اگر تغییری در سرورها دادیم، در تب «سرورها» دکمه‌ی «به‌روزرسانی» را بزنید.""",
    },
    "iphone": {
        "title": "🍎 آیفون / مک",
        "ios": """🍎 آیفون و مک:

1️⃣ «🔗 لینک اشتراک» را لمس کنید تا در Safari باز شود
2️⃣ برای IKEv2: در صفحه‌ی باز شده «نصب مستقیم روی iOS/macOS» را بزنید و اجازه‌ی دانلود پروفایل را بدهید
3️⃣ Settings ← General ← VPN & Device Management ← پروفایل Tifusi را باز کنید و Install را بزنید
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
4️⃣ منوی ⋮ ← Update subscription، یک کانفیگ را انتخاب و ▶️ را بزنید

💡 ساده‌ترین راه همان اپ Tifusi VPN با «🆔 شناسه» است.""",
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
    """کلاینت API پنل Tifusi Panel. هر کاربر یک لینک اشتراک و یک «شناسه» می‌گیرد که مستقیم در اپ Tifusi VPN
    وارد می‌شود؛ رمز کاربر را خود پنل مدیریت می‌کند.

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
                "l2tp_configs": links.get("l2tp_configs") or []}

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
            self.x("UPDATE users SET username=?, full_name=? WHERE id=?", (username or "", full_name or "", uid))
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
        return self.q(sql + " ORDER BY volume_gb", tuple(args))

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
        return "📱 Tifusi VPN"
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
PANEL_KNOWN_PROTOCOLS = {"vless", "vmess", "trojan", "shadowsocks", "hysteria2", "ikev2", "l2tp"}


def service_protocols_on(panel, service):
    """پروتکل‌های این سرویس که روی این پنل هاست دارند (به ترتیب SERVICE_PROTOCOLS) — برای تصمیم فروش."""
    available = panel_protocols(panel)
    return [p for p in SERVICE_PROTOCOLS.get(service, []) if available.get(p)]


def service_access_protocols(panel, service):
    """پروتکل‌هایی که کاربرِ این سرویس به آن‌ها دسترسی می‌گیرد: کل خانواده‌ی سرویس (نه فقط آن‌هایی که الان هاست دارند)
    تا اگر بعداً مثلاً Trojan به Xray اضافه شد، مشتریان فعلی Xray هم بدون تمدید به آن دسترسی داشته باشند."""
    available = panel_protocols(panel)
    return [p for p in SERVICE_PROTOCOLS.get(service, []) if p in PANEL_KNOWN_PROTOCOLS or available.get(p)]


def app_code_text(order, panel=None):
    """شناسه به شکل CODE@دامنه — با هر بیلد اپ و برای هر پنلی کار می‌کند. دامنه از لینک اشتراک خوانده
    می‌شود (آدرس عمومی پنل)، نه از آدرسی که ربات با آن به API وصل می‌شود و ممکن است IP یا پورت داخلی باشد."""
    if not order["app_code"]:
        return "-"
    host = urlparse(order["sub_url"] or "").netloc or (urlparse(panel["url"]).netloc if panel else "")
    return f"{order['app_code']}@{host}" if host else order["app_code"]


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


def btn(text, data):
    return InlineKeyboardButton(text, callback_data=data)


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
        return f"🛍️ {t} — {fmt(p['price'])} تومان"
    return f"🛍️ {plan_label(p)}"


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


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
def main_menu_kb(uid):
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
✅ سرویس‌های ما روی Tifusi Panel هستند: Xray (VLESS/VMess/Trojan)، IKEv2 و L2TP — با اپ Tifusi VPN روی اندروید و با لینک اشتراک روی آیفون.

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


def admin_menu_kb():
    return InlineKeyboardMarkup([
        [btn("📊 آمار ربات", "admin:stats")],
        [pbtn("💵 رسیدهای تایید نشده", "admin:receipts"), pbtn("🎫 لیست تیکت‌ها", "admin:tickets")],
        [btn("🗑 درخواست‌های حذف", "admin:delreqs")],
        [btn("🖥 مدیریت پنل‌ها", "admin:panels")],
        [pbtn("📦 مدیریت پلن‌ها", "admin:plans"), pbtn("💸 قیمت سرویس", "admin:plans_view")],
        [pbtn("👤 مدیریت کاربر", "admin:users"), pbtn("👑 مدیریت ادمین‌ها", "admin:admins")],
        [btn("⚙️ تنظیمات عمومی", "admin:settings")],
        [pbtn("📢 کانال/گروه گزارش", "admin:channel"), pbtn("📈 گزارش", "admin:report")],
        [pbtn("📣 پیام همگانی", "admin:broadcast"), pbtn("💾 بکاپ", "admin:backup")],
        [pbtn("🔧 قابلیت‌های پنل", "admin:panels_cap"), pbtn("🆕 نسخه و آپدیت", "admin:update")],
    ])


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
    db.set_state(u.id, "none")
    await update.message.reply_text(
        f"سلام {u.first_name} عزیز به ربات خوش آمدی 🌹👋\n\nاز منوی زیر استفاده کنید:",
        reply_markup=main_menu_kb(u.id))


# ---------- فلوی کاربر: منوها ----------
async def show_buy_services(query, uid):
    """قدم اول خرید: فقط سرویس‌هایی که همین الان روی پنل‌ها هاست و ظرفیت خالی دارند."""
    db.set_state(uid, "none")
    # سرویسی که هنوز پلنی ندارد نشان داده نمی‌شود تا مشتری به صفحه‌ی خالی نرسد
    services = [s for s in available_services() if db.get_plans(active_only=True, service=s)]
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
    """رمز ۱۰ کاراکتری بدون نویسه‌های شبیه به هم (0/O و 1/l/I) تا دستی در تنظیمات VPN آیفون راحت تایپ شود."""
    alphabet = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(10))


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


def delivery_details_html(order, panel, links):
    """بعد از بارکد به همین ترتیب: پروفایل آیفون، شناسه، اطلاعات ورود IKEv2/L2TP و لینک اپ — بدون متن آموزشی.
    رمز از خود پنل خوانده می‌شود نه از سفارش، تا همیشه همانی باشد که نود واقعاً چک می‌کند."""
    esc = html.escape
    ikev2 = (links or {}).get("ikev2_configs") or []
    l2tp = (links or {}).get("l2tp_configs") or []
    parts = []
    if ikev2 and ikev2[0].get("mobileconfig_url"):
        parts.append(f"🍎 نصب پروفایل آیفون:\n{esc(ikev2[0]['mobileconfig_url'])}")
    parts.append(f"🆔 شناسه: <code>{esc(app_code_text(order, panel))}</code>")

    configs = ikev2 + l2tp
    if configs:
        lines = [f"👤 نام کاربری: <code>{esc(configs[0]['username'])}</code>",
                 f"🔑 رمز عبور: <code>{esc(configs[0]['password'])}</code>"]
        for cfg in configs:
            if len(configs) > 1:
                lines.append(f"\n📍 {esc(cfg.get('remark') or cfg['server'])}")
            lines.append(f"🌐 آدرس: <code>{esc(cfg['server'])}</code>")
            if cfg.get("remote_id"):
                lines.append(f"🪪 ریموت آیدی: <code>{esc(cfg['remote_id'])}</code>")
            if cfg.get("psk"):
                lines.append(f"🔐 سکرت: <code>{esc(cfg['psk'])}</code>")
        parts.append("\n".join(lines))
    elif order["protocol"] in IPSEC_SERVICES and order["password"]:
        # پنل جواب نداد: دست‌کم نام کاربری و رمزی که با آن ساخته شد
        parts.append(f"👤 نام کاربری: <code>{esc(order['username'])}</code>\n"
                     f"🔑 رمز عبور: <code>{esc(order['password'])}</code>")

    parts.append(f"📲 Tifusi VPN:\n{esc(APP_ANDROID_URL)}")
    return "\n\n".join(parts)


async def deliver_service(context, chat_id, order, panel):
    """تحویل سرویس: یک خط خلاصه، بارکد لینک اشتراک با لینک زیرش، و بعد delivery_details_html."""
    dt = datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d")
    await context.bot.send_message(chat_id, f"✅ {service_name(order['protocol'])} — {vol_text(order['volume_gb'])} — تا {dt}")
    if order["sub_url"] and not await send_order_qr(context, chat_id, order):
        await context.bot.send_message(chat_id, order["sub_url"])
    links = None
    if order["protocol"] in IPSEC_SERVICES:
        try:
            links = await asyncio.to_thread(panel_client(panel).links, order["username"])
        except PanelError as e:
            log.warning("fetching IPsec details for %s failed: %s", order["username"], e)
    await context.bot.send_message(chat_id, delivery_details_html(order, panel, links),
                                   parse_mode="HTML", disable_web_page_preview=True)


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
async def show_services(query, uid):
    orders = db.get_user_orders(uid)
    if not orders:
        await safe_edit(query, "🛍 شما هنوز سرویسی ندارید.", reply_markup=back_kb())
        return
    text = f"🛍 سرویس‌های شما:\n\n"
    rows = []
    for o in orders:
        name = order_name(o)
        status = "" if o["status"] == "active" else " ⏳(درخواست حذف)"
        text += f"{o['username']} ← {name}\n"
        rows.append([btn(f"{o['username']} — {name}{status}", f"svc:{o['id']}")])
    rows.append([btn("🔙 بازگشت", "menu:back")])
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
    if not o["volume_gb"]:
        usage_line = "📦 حجم: نامحدود ♾ (بدون محدودیت مصرف)"
    elif panel:
        try:
            used_bytes = await asyncio.to_thread(panel_client(panel).usage, o["username"])
            if used_bytes is not None:
                used = gb(used_bytes)
                total = o["volume_gb"]
                left = max(0, round(total - used, 2))
                usage_line = f"📊 وضعیت مصرف:\n📦 {total} گیگ | 🔻 {used} گیگ | ✅ {left} گیگ باقی"
        except Exception:
            pass

    creds = (f"👤 یوزرنیم: `{o['username']}`\n"
             f"🆔 شناسه: `{app_code_text(o, panel)}`\n"
             f"🔗 لینک اشتراک: `{o['sub_url'] or '-'}`\n"
             f"📲 اندروید: {APP_ANDROID_URL}")
    text = (f"{md(service_name(o['protocol']))} — #{o['id']}\n"
            f"🖥 پنل: {md(pname)}\n\n{creds}\n\n{usage_line}\n"
            f"⏳ {remaining_text(o['expire_at'])} | 🕓 {dt}")
    rows = []
    if o["status"] == "active":
        rows.append([btn("♻️ تمدید سرویس", f"renew:{o['id']}")])
        refresh = btn("🔄 بروزرسانی اطلاعات", f"svc:{o['id']}")
        rows.append([btn("📷 QR code", f"qr:{o['id']}"), refresh] if o["sub_url"] else [refresh])
        rows.append([btn("❌ بازگشت وجه / حذف سرویس", f"delreq:{o['id']}")])
    rows.append([btn("🏠 بازگشت به لیست سرویس‌ها", "menu:services")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")


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
    if db.one("SELECT id FROM orders WHERE user_id=? AND price=0", (uid,)):
        await msg.reply_text("❌ اکانت تست فقط یک‌بار به هر کاربر داده می‌شود.\n🛍 سرویس‌های قبلی‌ات را از «سرویس‌های من» ببین.")
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


async def finalize_wallet_purchase(query, context, uid, data):
    plan = db.get_plan(data["plan_id"])
    if not plan:
        await safe_edit(query, "❌ پلن یافت نشد.", reply_markup=back_kb())
        return
    bal_before = db.get_balance(uid)
    if not db.try_spend(uid, plan["price"]):
        await safe_edit(query, "❌ موجودی کیف پول کافی نیست. لطفاً ابتدا شارژ کنید.",
                        reply_markup=InlineKeyboardMarkup([[btn("➕ شارژ کیف پول", "wallet:charge")],
                                                           [btn("🔙 بازگشت", "menu:back")]]))
        return
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
    plan = db.get_plan(pid)
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
    p = db.get_plan(plan_id) if plan_id else db.get_plan(o["plan_id"])
    plan = dict(p) if p else {"id": o["plan_id"], "volume_gb": o["volume_gb"], "days": o["days"], "price": o["price"], "user_limit": None}
    # فقط شکستِ خودِ تمدید خطا برمی‌گرداند (و باعث بازگشت وجه می‌شود)؛ اگر تمدید انجام شد ولی پیام نرسید،
    # نباید پول برگردد چون سرویس تمدید شده است.
    new_o, panel = await asyncio.to_thread(do_renew, o, plan)
    dt = datetime.datetime.fromtimestamp(new_o["expire_at"]).strftime("%Y-%m-%d %H:%M")
    try:
        await context.bot.send_message(uid,
            f"✅ سرویس `{new_o['username']}` تمدید شد!\n\n"
            f"📦 پلن جدید: {vol_text(new_o['volume_gb'])} — {new_o['days']} روز\n"
            f"👤 یوزرنیم: `{new_o['username']}`\n"
            f"🆔 شناسه: `{app_code_text(new_o, panel)}`\n"
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
    blocked = db.one("SELECT COUNT(*) c FROM users WHERE is_blocked=1")["c"]
    wallets = db.one("SELECT COALESCE(SUM(balance),0) s FROM users")["s"]
    vol_sold = db.one("SELECT COALESCE(SUM(volume_gb),0) s FROM orders")["s"]
    refs = db.one("SELECT COUNT(*) c FROM users WHERE referred_by IS NOT NULL")["c"]
    tests = db.one("SELECT COUNT(*) c FROM orders WHERE price=0")["c"]
    rc_ok = db.one("SELECT COUNT(*) c FROM receipts WHERE status='approved'")["c"]
    rc_no = db.one("SELECT COUNT(*) c FROM receipts WHERE status='rejected'")["c"]
    tk_closed = db.one("SELECT COUNT(*) c FROM tickets WHERE status='closed'")["c"]
    panels = db.get_panels()
    p_on = len([p for p in panels if p["status"] == "active"])
    p_off = len([p for p in panels if p["status"] == "offline"])
    p_ina = len([p for p in panels if p["status"] == "inactive"])
    text = (f"📊 آمار کامل ربات\n"
            f"━━━━━━━━━━━━━━━\n"
            f"👥 کاربران\n"
            f"👤 کل کاربران: {t['users']}\n"
            f"⛔ بلاک‌شده: {blocked}\n"
            f"🤝 عضوشده با دعوت: {refs}\n"
            f"💎 موجودی کل کیف‌پول‌ها: {fmt(wallets)} تومان\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🛍 سفارش‌ها\n"
            f"🧾 کل سفارشات: {t['orders']}\n"
            f"✅ سرویس‌های فعال: {t['active']}\n"
            f"🔑 اکانت‌های تست: {tests}\n"
            f"📦 حجم کل فروخته‌شده: {fmt(vol_sold)} گیگ\n"
            f"💰 درآمد کل: {fmt(t['revenue'])} تومان\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🖥 پنل‌ها\n"
            f"🟢 فعال: {p_on} | 🔴 آفلاین: {p_off} | ⚪ غیرفعال: {p_ina} | مجموع: {len(panels)}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💵 رسیدها\n"
            f"⏳ در انتظار: {t['pending_receipts']} | ✅ تاییدشده: {rc_ok} | ❌ ردشده: {rc_no}\n"
            f"🎫 تیکت‌ها → باز: {t['tickets_open']} | بسته: {tk_closed}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📅 ۲۴ ساعت گذشته:\n"
            f"👤 کاربر جدید: {day['new_users']} | 🛍 سفارش: {day['new_orders']} | 💰 {fmt(day['revenue'])} تومان\n"
            f"📅 ۷ روز گذشته:\n"
            f"👤 کاربر جدید: {week['new_users']} | 🛍 سفارش: {week['new_orders']} | 💰 {fmt(week['revenue'])} تومان\n"
            f"📅 ۳۰ روز گذشته:\n"
            f"👤 کاربر جدید: {month['new_users']} | 🛍 سفارش: {month['new_orders']} | 💰 {fmt(month['revenue'])} تومان")
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))


async def admin_delete_requests(query):
    """درخواست‌های حذفی که هنوز بررسی نشده‌اند. تا پیش از این، دکمه‌های تایید/رد فقط
    روی همان پیام اعلان ادمین بودند؛ با پاک شدن آن چت، سفارش برای همیشه در حالت
    «درخواست حذف» می‌ماند — نه تمدید می‌شود و نه دوباره می‌شود درخواست داد."""
    orders = db.pending_delete_requests()
    if not orders:
        await safe_edit(query, "✅ درخواست حذف بررسی‌نشده‌ای وجود ندارد.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        return
    rows = []
    text = "🗑 درخواست‌های حذف بررسی‌نشده:\n\n"
    for o in orders:
        text += f"#{o['id']} — {o['username']} — {service_name(o['protocol'])} — کاربر {o['user_id']}\n"
        rows.append([btn(f"✅ تایید حذف #{o['id']}", f"dq:ok:{o['id']}"),
                     btn(f"❌ رد #{o['id']}", f"dq:no:{o['id']}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_receipts(query):
    receipts = db.pending_receipts()
    if not receipts:
        await safe_edit(query, "✅ رسید تایید نشده‌ای وجود ندارد.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        return
    names = {"wallet_charge": "➕ شارژ کیف پول", "purchase": "🛍 خرید سرویس", "renew": "♻️ تمدید"}
    rows = []
    text = f"💵 رسیدهای تایید نشده:\n\n"
    for r in receipts:
        text += f"#{r['id']} — {names.get(r['rtype'], r['rtype'])} — {fmt(r['amount'])} تومان — کاربر {r['user_id']}\n"
        rows.append([btn(f"#{r['id']} | {names.get(r['rtype'])} | {fmt(r['amount'])}", f"rc:{r['id']}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


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
    if r["rtype"] == "wallet_charge":
        db.add_balance(r["user_id"], r["amount"])
        await context.bot.send_message(r["user_id"],
            f"💎 کاربر گرامی مبلغ {fmt(r['amount'])} تومان به کیف پول شما واریز گردید. با تشکر از پرداخت شما 🙏\n\n"
            f"🛒 کد پیگیری شما: R{r['id']}\n"
            f"💰 موجودی فعلی: {fmt(db.get_balance(r['user_id']))} تومان")
        await query.message.reply_text(f"✅ رسید #{rid} تایید شد — کیف پول کاربر شارژ شد.",
            reply_markup=InlineKeyboardMarkup([[btn("⚙️ مدیریت کاربر", f"au:panel:{r['user_id']}")]]))
    elif r["rtype"] == "purchase":
        plan = db.get_plan(meta.get("plan_id"))
        if not plan:
            await query.message.reply_text("❌ پلن حذف شده؛ وجه را دستی برگردانید.")
            return
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
    text = f"👑 مدیریت ادمین‌ها\n\n👑 ادمین اصلی: {ADMIN_ID}\n"
    for a in ads:
        text += f"👤 ادمین: {a}\n"
    text += "\nℹ️ ادمین‌ها دسترسی کامل دارند: تایید پرداخت، تنظیمات و همه بخش‌ها."
    rows = [[btn("➕ افزودن ادمین", "adm:add")]]
    for a in ads:
        rows.append([btn(f"🗑 حذف {a}", f"adm:del:{a}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


# ---------- مدیریت کاربر ----------
async def admin_user_panel(query, uid_target):
    u = db.get_user(uid_target)
    if not u:
        await safe_edit(query, "❌ کاربر یافت نشد.")
        return
    services = db.get_user_orders(uid_target, active_only=False)
    text = (f"👤 کاربر: {u['full_name']} (@{u['username'] or '-'})\n"
            f"🆔 {u['id']}\n💰 موجودی: {fmt(u['balance'])} تومان\n"
            f"🛍 سرویس‌ها: {len(services)} عدد\n"
            f"👥 زیرمجموعه: {db.referral_count(u['id'])} نفر")
    kb = InlineKeyboardMarkup([
        [btn("➕ شارژ دستی کیف پول", f"au:charge:{u['id']}")],
        [btn("🛍 مشاهده سرویس‌ها", f"au:svcs:{u['id']}"), btn("🔙 بازگشت", "admin:menu")],
    ])
    await safe_edit(query, text, reply_markup=kb)


# ---------- تنظیمات ----------
SETTING_KEYS = [
    ("backup_chat_id", "💾 آیدی کانال بکاپ"),
    ("card_number", "🏦 شماره کارت"),
    ("card_name", "👤 صاحب حساب"),
    ("support_id", "☎️ پشتیبانی"),
    ("test_volume_gb", "🔑 حجم تست"),
    ("test_days", "🔑 مدت تست"),
    ("faq_text", "❓ سوالات متداول"),
]
# چیدمان دکمه‌ها در صفحه تنظیمات (یک ردیف کامل یا دو دکمه کنار هم)
SETTING_LAYOUT = [
    ("test_volume_gb", "test_days"),
    ("card_number", "card_name"),
    ("support_id", "faq_text"),
    ("backup_chat_id",),
]


async def admin_settings(query):
    # اکانت تست پیش‌فرض خاموش است؛ کلید روشن/خاموش کنار حجم و مدت تست نمایش داده می‌شود
    test_label = f"🔑 اکانت تست: {'فعال' if db.setting('test_enabled', '0') == '1' else 'غیرفعال'}"
    text = f"⚙️ تنظیمات عمومی\n"
    labels = dict(SETTING_KEYS)
    for key, label in SETTING_KEYS:
        if key == "test_volume_gb":
            text += test_label + "\n"
        val = db.setting(key, "—")
        if key == "faq_text" and val != "—":
            val = "✅ تنظیم شده"
        text += f"{label}: {val}\n"
    rows = [[btn(test_label, "tgl:test_enabled")]]
    for line in SETTING_LAYOUT:
        rows.append([btn(f"✏️ {labels[k]}", f"set:{k}") for k in line])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_channel(query):
    text = (f"📢 تنظیم کانال/گروه گزارش\n\n"
            f"کانال: {db.setting('channel_id', '—')}\nگروه: {db.setting('group_id', '—')}\n\n"
            f"آیدی را با @ یا عدد -100 وارد کنید. ربات باید در کانال/گروه ادمین باشد.")
    kb = InlineKeyboardMarkup([
        [btn("✏️ آیدی کانال", "set:channel_id"), btn("✏️ آیدی گروه", "set:group_id")],
        [btn("🔙 بازگشت", "admin:menu")],
    ])
    await safe_edit(query, text, reply_markup=kb)


# ---------- تیکت‌ها ----------
async def admin_tickets(query):
    tickets = db.open_tickets()
    if not tickets:
        await safe_edit(query, "✅ تیکت بازی وجود ندارد.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        return
    rows = []
    text = f"🎫 تیکت‌های باز:\n\n"
    for t in tickets:
        preview = (t["message"] or "")[:40]
        text += f"#{t['id']} — کاربر {t['user_id']}: {preview}\n"
        rows.append([btn(f"🎫 #{t['id']} — کاربر {t['user_id']}", f"tk:{t['id']}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


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
def report_text(title, ts):
    s = db.stats_since(ts)
    t = db.totals()
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
    kb = InlineKeyboardMarkup([
        [btn("📅 امروز", "report:day")],
        [btn("📅 هفتگی", "report:week"), btn("📅 ماهانه", "report:month")],
        [btn("🔙 بازگشت", "admin:menu")],
    ])
    await safe_edit(query, f"📈 گزارش\n\nبازه گزارش را انتخاب کنید:", reply_markup=kb)


# ---------- مدیریت پلن‌ها ----------
async def admin_plans(query):
    plans = db.get_plans()
    rows = [[btn("➕ افزودن پلن جدید", "pl:add")]]
    text = f"📦 مدیریت پلن‌ها (هر سرویس پلن‌ها و قیمت‌های خودش):\n🧺 فعال | 🔴 غیرفعال\n"
    for service in [*SERVICES, ""]:
        group = [p for p in plans if plan_service(p) == service]
        if not group:
            continue
        rows.append([btn(f"── {SERVICES.get(service, 'همه‌ی سرویس‌ها (پلن قدیمی)')} ──", "pl:noop")])
        for p in group:
            st = "🧺" if p["active"] else "🔴"
            rows.append([btn(f"{st} #{p['id']} | {plan_label(p)} — {fmt(p['price'])} تومان", f"pl:{p['id']}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


def plan_service_kb(prefix, back):
    rows = [[btn(name, f"{prefix}:{key}")] for key, name in SERVICES.items()]
    rows.append([btn("🔙 بازگشت", back)])
    return InlineKeyboardMarkup(rows)


async def admin_plan_detail(query, pid):
    p = db.get_plan(pid)
    if not p:
        await safe_edit(query, "❌ پلن یافت نشد.")
        return
    st = "فعال 🟢" if p["active"] else "غیرفعال 🔴"
    try:
        ul = int(p["user_limit"] or 0)
    except (IndexError, KeyError, TypeError, ValueError):
        ul = 0
    ul_text = f"{ul} دستگاه همزمان" if ul else "بدون محدودیت دستگاه"
    text = (f"📦 پلن #{p['id']}\n🧩 سرویس: {plan_service_name(p)}\n🛍️ {plan_label(p)}\n"
            f"💰 قیمت: {fmt(p['price'])} تومان\n👥 لیمت دستگاه همزمان: {ul_text}\n📌 وضعیت: {st}")
    kb = InlineKeyboardMarkup([
        [btn("✏️ عنوان", f"ple:{pid}:title"), btn("🧩 سرویس", f"pl:svc:{pid}")],
        [btn("✏️ حجم (گیگ)", f"ple:{pid}:volume_gb"), btn("✏️ مدت (روز)", f"ple:{pid}:days")],
        [btn("✏️ قیمت (تومان)", f"ple:{pid}:price"), btn("👥 تعداد کاربر (0 تا 5)", f"ple:{pid}:user_limit")],
        [btn("🔁 فعال / غیرفعال", f"pl:toggle:{pid}"), btn("🗑 حذف پلن", f"pl:del:{pid}")],
        [btn("🔙 بازگشت", "admin:plans")],
    ])
    await safe_edit(query, text, reply_markup=kb)


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
    pbtns = []
    text = "🖥 مدیریت پنل‌های Tifusi Panel:\n\n"
    for p in panels:
        cnt = db.count_panel_active_orders(p["id"])
        sold = [SERVICES[k] for k in db.get_service_map(p["id"]) if service_protocols_on(p, k)]
        text += (f"{panel_status_icon(p)} #{p['id']} {p['name']} — {p['location']} — {cnt}/{p['max_users']} کاربر "
                 f"{'، '.join(sold)}\n")
        pbtns.append(btn(f"#{p['id']} {p['name']} ({cnt}/{p['max_users']})", f"pb:{p['id']}"))
    rows = [[btn("➕ افزودن پنل", "pb:add")]] + [pbtns[i:i + 2] for i in range(0, len(pbtns), 2)]
    if not panels:
        text += "پنلی ثبت نشده.\n"
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_panel_detail(query, pid):
    p = db.get_panel(pid)
    if not p:
        await safe_edit(query, "❌ پنل یافت نشد.")
        return
    cnt = db.count_panel_active_orders(pid)
    icons = {"active": "🟢 فعال", "inactive": "⚪ غیرفعال", "offline": "🔴 Offline"}
    checked = datetime.datetime.fromtimestamp(p["checked_at"]).strftime("%Y-%m-%d %H:%M") if p["checked_at"] else "هرگز"
    tls = "\n⚠️ گواهی SSL پنل معتبر نیست (self-signed)؛ اتصال رمزنگاری شده ولی هویت پنل تایید نمی‌شود." if p["tls_insecure"] else ""
    text = (f"🖥 پنل #{p['id']}: {p['name']} (Tifusi Panel)\n\n"
            f"🌐 آدرس: {p['url']}\n👤 یوزر: {p['username']}\n"
            f"📍 موقعیت: {p['location'] or '—'}\n"
            f"📌 وضعیت: {icons.get(p['status'], p['status'])}\n"
            f"👥 کاربران فعال ربات: {cnt}/{p['max_users']}\n"
            f"🕓 آخرین بررسی: {checked}{tls}\n\n"
            f"📡 پروتکل‌های روی پنل:\n{protocols_text(p)}\n\n"
            f"🧩 سرویس‌ها:\n{service_map_text(p)}")
    kb = InlineKeyboardMarkup([
        [btn("🔄 بررسی اتصال و به‌روزرسانی پروتکل‌ها", f"pb:test:{pid}")],
        [btn("🔁 فعال / غیرفعال", f"pb:toggle:{pid}"), btn("✏️ ویرایش پنل", f"pb:edit:{pid}")],
        [btn("🧩 انتخاب گروه سرویس‌ها", f"pbm:{pid}")],
        [btn("🗑 حذف پنل", f"pb:del:{pid}"), btn("🔙 بازگشت", "admin:panels")],
    ])
    await safe_edit(query, text, reply_markup=kb)


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
    kb = InlineKeyboardMarkup([
        [btn("✏️ نام", f"pbe:{pid}:name"), btn("✏️ آدرس", f"pbe:{pid}:url")],
        [btn("✏️ یوزرنیم", f"pbe:{pid}:username"), btn("✏️ پسورد", f"pbe:{pid}:password")],
        [btn("✏️ موقعیت", f"pbe:{pid}:location"), btn("✏️ سقف کاربر", f"pbe:{pid}:max_users")],
        [btn("🧩 انتخاب گروه سرویس‌ها", f"pbm:{pid}")],
        [btn("🔙 بازگشت", f"pb:{pid}")],
    ])
    await safe_edit(query, "✏️ کدام مورد را ویرایش می‌کنید؟", reply_markup=kb)


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
        await safe_edit(query, "پنلی ثبت نشده است.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        return
    text = "🔧 قابلیت‌ها و ظرفیت پنل‌ها:\n\n"
    icons = {"active": "🟢", "inactive": "⚪", "offline": "🔴"}
    for p in panels:
        cnt = db.count_panel_active_orders(p["id"])
        sold = [SERVICES[k] for k in SERVICES if k in db.get_service_map(p["id"]) and service_protocols_on(p, k)]
        text += (f"{icons.get(p['status'], '⚪')} {p['name']} — {cnt}/{p['max_users']} کاربر\n"
                 f"   📡 {', '.join(panel_protocols(p)) or '—'}\n"
                 f"   🧩 {', '.join(sold) if sold else '—'}\n")
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))


# ---------- بکاپ ----------
async def send_backup(bot, chat_id, note="💾 بکاپ دیتابیس ربات"):
    """کپی سازگار دیتابیس (کاربران، کیف پول‌ها، سفارش‌ها، پنل‌ها، پلن‌ها، تنظیمات) به‌صورت فایل برای ادمین."""
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        await asyncio.to_thread(db.backup_to, tmp)
        stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M")
        t = db.totals()
        with open(tmp, "rb") as f:
            await bot.send_document(chat_id, f, filename=f"tifusi-bot-backup_{stamp}.db",
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
    await safe_edit(query,
        "💾 بکاپ ربات\n\n"
        "بکاپ شامل همه‌چیز است: کاربران، موجودی کیف پول‌ها، سفارش‌ها، رسیدها، پنل‌ها، پلن‌ها و تنظیمات.\n\n"
        f"🕓 بکاپ خودکار روزانه (ساعت ۳ بامداد به ادمین اصلی): {'فعال ✅' if auto else 'غیرفعال ❌'}\n"
        "📢 اگر «آیدی کانال بکاپ» را در تنظیمات عمومی وارد کنید، بکاپ روزانه آنجا هم فرستاده می‌شود.",
        reply_markup=InlineKeyboardMarkup([
            [btn("📥 دریافت بکاپ الان", "bk:now")],
            [btn("♻️ بازگردانی از فایل بکاپ", "bk:restore"), btn("🔁 بکاپ خودکار: روشن/خاموش", "bk:auto")],
            [btn("🔙 بازگشت", "admin:menu")],
        ]))


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
            plan = db.get_plan(int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
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
            plan = db.get_plan(sd.get("plan_id"))
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
            plan = db.get_plan(sd.get("plan_id"))
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
            p = db.get_plan(pid) if pid else db.get_plan(o["plan_id"])
            # پلن سرویس دیگری (با قیمت دیگر) نباید با دکمه‌ی دست‌کاری‌شده برای این سرویس خریده شود
            if pid and (not p or not plan_fits(p, o["protocol"])):
                return
            price = p["price"] if p else o["price"]
            plan_id = pid or o["plan_id"]
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

        # ---------- ادمین ----------
        if not is_admin(uid):
            return

        if cmd == "admin":
            what = parts[1]
            if what == "menu":
                await safe_edit(query, f"🧑‍💼 پنل مدیریت:", reply_markup=admin_menu_kb())
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
                await safe_edit(query,
                    f"🆕 نسخه ربات: {BOT_VERSION}\n📅 تاریخ نسخه: {BOT_VERSION_DATE}\n\n"
                    f"برای آپدیت، روی سرور ربات بزنید:\n tifusi bot\n"
                    f"و گزینه‌ی «Update bot» را انتخاب کنید. تنظیمات و دیتابیس حفظ می‌شوند؛\n"
                    f"برای اطمینان قبلش از «💾 بکاپ» یک نسخه بگیرید.",
                    reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
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
            await safe_edit(query, report_text(title, now() - span),
                            reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:report")]]))
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
            if parts[1] == "charge":
                db.set_state(uid, "au_amount", {"target": int(parts[2])})
                await safe_edit(query, "💰 مبلغ شارژ دستی را به تومان وارد کنید:")
            elif parts[1] == "panel":
                await admin_user_panel(query, int(parts[2]))
            elif parts[1] == "svcs":
                services = db.get_user_orders(int(parts[2]), active_only=False)
                text = f"🛍 سرویس‌های کاربر {parts[2]}:\n\n"
                for o in services:
                    text += (f"#{o['id']} — {o['username']} — {order_name(o)} — "
                             f"{'✅' if o['status'] == 'active' else o['status']}\n")
                await safe_edit(query, text or "سرویسی ندارد.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙", "admin:menu")]]))
            return

        if cmd == "set":
            key = parts[1]
            db.set_state(uid, "set_value", {"key": key})
            await safe_edit(query, f"✏️ مقدار جدید برای «{key}» را ارسال کنید:")
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
        plan = db.get_plan(sd.get("plan_id"))
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
        if not IPSEC_PASSWORD_RE.fullmatch(text):
            await msg.reply_text(f"❌ رمز نامعتبر است.\n{IPSEC_PASSWORD_RULES}\n\nدوباره ارسال کنید:",
                                 reply_markup=password_prompt_kb(sd.get("protocol")) if sd.get("protocol") in SERVICES else None)
            return True
        plan = db.get_plan(sd.get("plan_id"))
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
    if state == "support_message":
        tid = db.create_ticket(uid, text)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ تیکت #{tid} ثبت شد. به‌زودی پاسخ می‌گیرید.", reply_markup=main_menu_kb(uid))
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
        services = db.get_user_orders(u["id"], active_only=False)
        kb = InlineKeyboardMarkup([
            [btn("➕ شارژ دستی کیف پول", f"au:charge:{u['id']}")],
            [btn("🛍 مشاهده سرویس‌ها", f"au:svcs:{u['id']}"), btn("🔙 بازگشت", "admin:menu")]])
        await msg.reply_text(
            f"👤 {u['full_name']} (@{u['username'] or '-'})\n🆔 {u['id']}\n"
            f"💰 موجودی: {fmt(u['balance'])} تومان\n🛍 سرویس‌ها: {len(services)}",
            reply_markup=kb)
        return True

    if state == "au_amount" and is_admin(uid):
        try:
            amount = int(text.replace(",", ""))
        except ValueError:
            await msg.reply_text("❌ فقط عدد وارد کنید:")
            return True
        target = sd["target"]
        db.add_balance(target, amount)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ {fmt(amount)} تومان به کاربر {target} شارژ شد.")
        try:
            await context.bot.send_message(target, f"💰 کیف پول شما {fmt(amount)} تومان شارژ شد (شارژ دستی).")
        except Exception:
            pass
        return True

    # ---------- ادمین: تنظیمات ----------
    if state == "set_value" and is_admin(uid):
        if sd["key"] in ("test_volume_gb", "test_days") and not (text.isdigit() and int(text) > 0):
            await msg.reply_text("❌ یک عدد بزرگ‌تر از صفر وارد کنید:")
            return True
        db.set_setting(sd["key"], text)
        db.set_state(uid, "none")
        await msg.reply_text(f"✅ تنظیم «{sd['key']}» ذخیره شد.")
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
            await msg.reply_text("🏠 منوی اصلی\n\nاز منوی زیر انتخاب کنید:",
                                 reply_markup=main_menu_kb(uid))
        return

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
            await msg.reply_text(f"🧑‍💼 پنل مدیریت:", reply_markup=admin_menu_kb())
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
        plan = db.get_plan(sd.get("plan_id"))
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
            await notify_admin(context.bot, f"⚠️ پنل «{p['name']}» offline شد و از فروش خارج شد!")
        elif ok and p["status"] == "offline":
            db.update_panel(p["id"], status="active")
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
    for target in targets:
        try:
            await send_backup(context.bot, target, "💾 بکاپ خودکار روزانه‌ی ربات")
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
                await context.bot.send_message(target if target.startswith("@") else int(target), text)
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


def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("❌ ابتدا BOT_TOKEN و ADMIN_ID را در بالای همین فایل (bot.py) پر کنید.")
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler("start", per_user(start)))
    app.add_handler(CallbackQueryHandler(per_user(on_callback_admin), pattern=r"^(pb|pbe|pbm|apm|pl|ple):"))
    app.add_handler(CallbackQueryHandler(per_user(on_callback)))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, per_user(on_photo)))
    app.add_handler(MessageHandler(filters.Document.ALL & ~filters.COMMAND, per_user(on_document)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, per_user(on_message)))
    app.add_error_handler(on_error)
    if app.job_queue:
        app.job_queue.run_repeating(health_job, interval=300, first=30)
        app.job_queue.run_repeating(reminder_job, interval=3600, first=120)
        app.job_queue.run_daily(daily_report_job, time=datetime.time(23, 0))
        app.job_queue.run_daily(daily_backup_job, time=datetime.time(3, 0))
    else:
        log.warning("job-queue نصب نیست: چک سلامت، یادآوری انقضا و بکاپ خودکار اجرا نمی‌شوند "
                    "(pip install 'python-telegram-bot[job-queue]')")
    log.info("🤖 ربات v%s روشن شد...", BOT_VERSION)
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
