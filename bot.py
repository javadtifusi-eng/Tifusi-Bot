# -*- coding: utf-8 -*-
"""ربات فروش اشتراک VPN v4.0 — تک‌فایلی (همه‌چیز در همین یک فایل) — فقط Tifusi Panel (Xray / WireGuard / IKEv2 / L2TP) | چندپنلی.
فقط BOT_TOKEN و ADMIN_ID را در بالای فایل پر کنید و اجرا کنید: python bot.py"""
import re
import json
import time
import io
import asyncio
import logging
import datetime
from urllib.parse import urlparse

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          CallbackQueryHandler, ContextTypes, filters)

import sqlite3
import threading
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ══════════════════════ تنظیمات — فقط همین دو مقدار را پر کنید ══════════════════════
BOT_TOKEN = ""      # توکن ربات از @BotFather
ADMIN_ID = 0        # آیدی عددی ادمین از @userinfobot
DEFAULT_PANEL_MAX_USERS = 200   # سقف پیش‌فرض کاربر هر پنل — وقتی پنل به این عدد برسد، خریدهای جدید می‌روند پنل بعدی (تمدیدها همیشه روی همان پنل انجام می‌شوند)
# ════════════════════════════════════════════════════════════════════════════════════



# ══════════════════════ سرویس‌ها (services) ══════════════════════

# ربات فقط از طریق Tifusi Panel می‌فروشد. هر سرویس روی هر پنل به یک «گروه» پنل وصل می‌شود؛
# گروه تعیین می‌کند کاربر به کدام سرورها دسترسی دارد (سروری که در هیچ گروهی نیست برای همه است).
# ترتیب همین دیکشنری ترتیب دکمه‌های خرید است. سرویسی که هیچ پنلی برایش گروه انتخاب نکرده به مشتری
# نشان داده نمی‌شود — مثلاً WireGuard تا وقتی به پنل اضافه نشده و ادمین گروهی برایش انتخاب نکرده.
SERVICES = {
    "xray": "🌐 Xray (VLESS / VMess / Trojan)",
    "wireguard": "🔒 WireGuard",
    "ikev2": "🛡 IKEv2",
    "l2tp": "🔗 L2TP",
}
# اکانت تست روی اولین سرویسِ در دسترس به همین ترتیب ساخته می‌شود
TEST_SERVICE_ORDER = ["ikev2", "xray", "l2tp", "wireguard"]
# سفارش‌های نسخه‌ی قبلی Tifusi Panel (یک سرویس کلی با کلید tifusi) هم با همان منطق Tifusi تمدید/حذف می‌شوند
TIFUSI_ORDER_KEYS = set(SERVICES) | {"tifusi"}

APP_ANDROID_URL = "https://github.com/javadtifusi-eng/Tifusi-VPN/releases/latest/download/tifusi-vpn.apk"
APP_WINDOWS_URL = "https://github.com/javadtifusi-eng/Tifusi-VPN/releases/latest/download/TifusiVPN.exe"


# ══════════════════════ آموزش اتصال (training) ══════════════════════

# هر آموزش فقط سیستم‌عامل‌هایی را دارد که برایش معنی دارد؛ اگر یکی باشد مستقیم همان نمایش داده می‌شود
TUT_OS = [("windows", "🪟 ویندوز"), ("android", "🤖 اندروید"), ("ios", "🍎 آیفون")]

TRAININGS = {
    "app": {
        "title": "📱 اپ Tifusi VPN با کد اپ (اندروید / ویندوز)",
        "android": f"""🤖 اندروید:

1️⃣ اپ Tifusi VPN را دانلود و نصب کنید:
{APP_ANDROID_URL}
2️⃣ اپ را باز کنید و به تب «سرورها» بروید
3️⃣ «کد اپ» که ربات فرستاده (به شکل CODE@آدرس-پنل) را وارد کنید و «دریافت سرورها» را بزنید
4️⃣ یک سرور را انتخاب کنید و وصل شوید

💡 به‌جای کد، لینک اشتراک را هم می‌توانید وارد کنید. با تمدید سرویس، کد و لینک عوض نمی‌شوند.""",
        "windows": f"""🪟 ویندوز:

1️⃣ برنامه Tifusi VPN را دانلود و اجرا کنید:
{APP_WINDOWS_URL}
2️⃣ به تب «سرورها» بروید
3️⃣ «کد اپ» (CODE@آدرس-پنل) را وارد کنید و «دریافت سرورها» را بزنید
4️⃣ یک سرور را انتخاب کنید و وصل شوید

💡 به‌جای کد، لینک اشتراک را هم می‌توانید وارد کنید.""",
    },
    "iphone": {
        "title": "🍎 آیفون با لینک اشتراک (پروفایل IKEv2)",
        "ios": """🍎 آیفون / آیپد:

1️⃣ لینک اشتراکی که ربات فرستاده را کپی کنید
2️⃣ لینک را در Safari باز کنید (نه در مرورگر داخل تلگرام)
3️⃣ پروفایل IKEv2 را دانلود کنید و از Settings ← Profile Downloaded نصب کنید
4️⃣ از Settings ← VPN اتصال را روشن کنید

💡 برای سرویس Xray روی آیفون، آموزش «Xray با v2rayNG / Streisand» را ببینید.""",
    },
    "xray": {
        "title": "🌐 Xray با v2rayNG / Streisand",
        "android": """🤖 اندروید (v2rayNG):

1️⃣ اپ v2rayNG را نصب کنید
2️⃣ لینک اشتراک را کپی کنید
3️⃣ در اپ از منوی ☰ ← Subscription group setting ← ➕ لینک را اضافه کنید
4️⃣ منوی ⋮ ← Update subscription، سپس یک کانفیگ را انتخاب کنید و ▶️ را بزنید

💡 اپ Tifusi VPN هم با کد اپ همین سرویس را وصل می‌کند.""",
        "ios": """🍎 آیفون (Streisand):

1️⃣ اپ Streisand را از اپ‌استور نصب کنید
2️⃣ لینک اشتراک را کپی کنید
3️⃣ در اپ ➕ را بزنید و لینک را به‌عنوان Subscription اضافه کنید
4️⃣ یک سرور را انتخاب کنید و اتصال را روشن کنید""",
    },
}


# ══════════════════════ اتصال به Tifusi Panel (panel) ══════════════════════

class PanelError(Exception):
    pass


class TifusiPanelAPI:
    """کلاینت API پنل Tifusi Panel (هسته‌های Xray / IKEv2 / L2TP) - هر کاربر یک لینک اشتراک و یک «کد اپ»
    می‌گیرد که مستقیم در اپ Tifusi VPN وارد می‌شود. گروه‌های پنل تعیین می‌کنند کاربر به کدام سرورها دسترسی
    دارد؛ سروری که در هیچ گروهی نیست برای همه‌ی کاربران است. رمز کاربر را خود پنل مدیریت می‌کند."""

    def __init__(self, url, username, password, timeout=15):
        self.base = url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        self.s = requests.Session()
        self.s.verify = False
        self.s.headers.update({"Accept": "application/json"})

    def _u(self, path):
        return self.base + path

    def login(self):
        try:
            r = self.s.post(self._u("/api/auth/login"),
                            json={"username": self.username, "password": self.password},
                            timeout=self.timeout)
        except requests.RequestException as e:
            raise PanelError(f"خطای اتصال: {e}")
        if r.status_code == 429:
            raise PanelError("تلاش ورود زیاد بود؛ چند دقیقه بعد دوباره امتحان کنید")
        if r.status_code != 200:
            raise PanelError("ورود به پنل ناموفق بود (آدرس/یوزرنیم/پسورد را چک کنید)")
        try:
            token = r.json().get("access_token")
        except ValueError:
            token = None
        if not token:
            raise PanelError("ورود به پنل ناموفق بود (توکن دریافت نشد)")
        self.s.headers.update({"Authorization": f"Bearer {token}"})
        return True

    def _call(self, path, method="get", **kwargs):
        try:
            r = self.s.request(method.upper(), self._u(path), timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            raise PanelError(f"خطای اتصال: {e}")
        if r.status_code >= 400:
            try:
                msg = r.json().get("detail")
            except ValueError:
                msg = None
            raise PanelError(str(msg) if msg else f"عملیات ناموفق (HTTP {r.status_code})")
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError:
            return None

    def list_groups(self):
        """گروه‌های پنل برای نگاشت سرویس ← گروه. پنلی که گروه ندارد همه‌ی سرورهایش عمومی است،
        برای همین یک ردیف «سرورهای عمومی» (بدون گروه، شناسه ۰) برمی‌گردد تا بشود پنل را اضافه کرد."""
        obj = self._call("/api/groups", params={"limit": 200}) or {}
        groups = obj.get("groups", []) if isinstance(obj, dict) else (obj or [])
        result = [{"inbound_id": g.get("id"), "remark": g.get("name", ""), "port": 0,
                   "protocol": "group", "enabled": True} for g in groups]
        if not result:
            result.append({"inbound_id": 0, "remark": "سرورهای عمومی (بدون گروه)", "port": 0,
                           "protocol": "group", "enabled": True})
        return result

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
                "app_code": links.get("app_code", "")}

    @staticmethod
    def _limits(total_gb, expire_ts):
        # حجم ۰ یعنی نامحدود؛ انقضا با منطقه‌ی زمانی UTC فرستاده می‌شود
        expire = datetime.datetime.fromtimestamp(int(expire_ts), tz=datetime.timezone.utc).isoformat()
        return expire, (int(total_gb) * 1024 ** 3 if total_gb else None)

    def add_user(self, group_ids, username, total_gb, expire_ts):
        expire, data_limit = self._limits(total_gb, expire_ts)
        user = self._call("/api/users", "post", json={
            "username": username, "status": "active", "expire": expire, "data_limit": data_limit,
            "group_ids": [int(g) for g in group_ids if int(g)], "note": "Tifusi Bot",
        })
        return self._with_links(user)

    def renew_user(self, username, total_gb, expire_ts):
        """همان کاربر به‌روز می‌شود تا لینک اشتراک و شناسه‌ی اپ عوض نشوند؛ حجم جدید روی مصرف فعلی
        اضافه می‌شود چون پنل مصرف را صفر نمی‌کند. اگر کاربر روی پنل نبود None برمی‌گرداند."""
        user = self.find_user(username)
        if not user:
            return None
        expire, extra = self._limits(total_gb, expire_ts)
        data_limit = int(user.get("used_traffic") or 0) + extra if extra else None
        user = self._call(f"/api/users/{int(user['id'])}", "put",
                          json={"status": "active", "expire": expire, "data_limit": data_limit})
        return self._with_links(user)

    def del_user(self, username):
        try:
            user = self.find_user(username)
            if user:
                self._call(f"/api/users/{int(user['id'])}", "delete")
        except PanelError:
            return None

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
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init()

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
        # مهاجرت: ستون تعداد کاربر (دستگاه همزمان) برای هر پلن — 0 یعنی پیروی از لیمت اینباند
        try:
            self.x("ALTER TABLE plans ADD COLUMN user_limit INTEGER DEFAULT 0")
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
        return self.x("""INSERT INTO panels (name,url,username,password,location,max_users,status,type,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (d.get("name", ""), d.get("url", ""), d.get("username", ""), d.get("password", ""),
             d.get("location", ""), int(d.get("max_users", 200)), d.get("status", "active"),
             d.get("type", "tifusi"), int(time.time())))

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
        (۰ = سرورهای عمومی)، remark = نام گروه. mapping: {service: {"id": ..., "name": ...}}"""
        self.x("DELETE FROM panel_inbounds WHERE panel_id=?", (panel_id,))
        for key in SERVICES:
            g = mapping.get(key)
            if g:
                self.x("INSERT INTO panel_inbounds (panel_id,inbound_id,protocol,port,enabled,remark) VALUES (?,?,?,0,1,?)",
                       (panel_id, int(g.get("id") or 0), key, g.get("name", "")))

    def get_service_map(self, panel_id):
        """{کلید سرویس: ردیف} فقط برای سرویس‌های فعلی؛ ردیف‌های قدیمی (inbound یا گروه نسخه‌های قبل) نادیده گرفته می‌شوند."""
        rows = self.q("SELECT * FROM panel_inbounds WHERE panel_id=? AND enabled=1 ORDER BY id", (panel_id,))
        return {r["protocol"]: r for r in rows if r["protocol"] in SERVICES}

    # ---------- پلن‌ها ----------
    def add_plan(self, volume_gb, days, price, title="", user_limit=0):
        return self.x("INSERT INTO plans (volume_gb,days,price,active,created_at,title,user_limit) VALUES (?,?,?,1,?,?,?)",
                      (int(volume_gb), int(days), int(price), int(time.time()), title, int(user_limit)))

    def get_plans(self, active_only=False):
        sql = "SELECT * FROM plans"
        if active_only:
            sql += " WHERE active=1"
        return self.q(sql + " ORDER BY volume_gb")

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

    def get_user_orders(self, uid, active_only=True):
        sql = "SELECT * FROM orders WHERE user_id=?"
        if active_only:
            sql += " AND status IN ('active','delreq_pending')"
        return self.q(sql + " ORDER BY id DESC", (uid,))

    def update_order(self, oid, **fields):
        if not fields:
            return
        sets = ",".join(f"{k}=?" for k in fields)
        self.x(f"UPDATE orders SET {sets} WHERE id=?", (*fields.values(), oid))

    def count_panel_active_orders(self, panel_id):
        return self.one("SELECT COUNT(*) c FROM orders WHERE panel_id=? AND status='active'", (panel_id,))["c"]

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

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
log = logging.getLogger("vpn_bot")

db = DB()

def service_name(key):
    """نام نمایشی سرویس؛ کلیدهای نسخه‌های قبلی ربات با برچسب «سرویس قدیمی» نمایش داده می‌شوند."""
    if key in SERVICES:
        return SERVICES[key]
    if key == "tifusi":
        return "📱 Tifusi VPN"
    return f"🗄 سرویس قدیمی ({key})"


def is_legacy_panel(panel):
    """پنل‌هایی از دیتابیس نسخه‌ی قبلی که Tifusi Panel نیستند: نه در فروش، نه در چک سلامت — فقط نمایش."""
    return (panel["type"] or "") != "tifusi"


def order_is_legacy(o):
    """سفارشی که با منطق Tifusi قابل مدیریت نیست: کلیدش سرویس فعلی نیست یا پنلش Tifusi Panel نیست.
    نوع پنل هم چک می‌شود چون سفارش‌های پنل‌های قدیمی Xray هم کلید xray دارند."""
    if o["protocol"] not in TIFUSI_ORDER_KEYS:
        return True
    panel = db.get_panel(o["panel_id"])
    return bool(panel) and is_legacy_panel(panel)


def order_name(o):
    return f"🗄 سرویس قدیمی ({o['protocol']})" if order_is_legacy(o) else service_name(o["protocol"])


LEGACY_ORDER_TEXT = ("⚠️ این سرویس مربوط به نسخه‌ی قبلی ربات است و دیگر از اینجا قابل تمدید یا حذف نیست.\n"
                     "🔐 برای ادامه، لطفاً از «خرید اشتراک» یک سرویس جدید بخرید.")


def app_code_text(order, panel):
    """کد اپ به شکل CODE@دامنه‌ی پنل — با هر بیلد اپ کار می‌کند، حتی اگر پنل پیش‌فرض اپ پنل دیگری باشد."""
    if not panel or not order["app_code"]:
        return "-"
    return f"{order['app_code']}@{urlparse(panel['url']).netloc}"


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
        ["🎲 گردونه شانس", "🔑 اکانت تست"],
        ["🏦 کیف پول + شارژ", "🛍 سرویس‌های من"],
        ["💵 تعرفه اشتراک ها", "👥 زیرمجموعه گیری"],
        ["📚 آموزش", "☎️ پشتیبانی"],
    ]
    if is_admin(uid):
        rows.append(["🧑‍💼 پنل مدیریت"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


FAQ_DEFAULT = """💡 سوالات متداول ⁉️

1️⃣ فیلترشکن شما از چه نوعیه؟
✅ سرویس‌های ما روی Tifusi Panel هستند: Xray (VLESS/VMess/Trojan)، IKEv2 و L2TP — با اپ Tifusi VPN روی اندروید و ویندوز و با لینک اشتراک روی آیفون.

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
        [pbtn("📊 آمار ربات", "admin:stats"), pbtn("💵 رسیدهای تایید نشده", "admin:receipts")],
        [pbtn("👤 مدیریت کاربر", "admin:users"), pbtn("💸 قیمت سرویس", "admin:plans_view")],
        [pbtn("⚙️ تنظیمات عمومی", "admin:settings"), pbtn("🎫 لیست تیکت‌ها", "admin:tickets")],
        [pbtn("🔧 قابلیت‌های پنل", "admin:panels_cap"), pbtn("🆕 آپدیت ربات", "admin:update")],
        [pbtn("📢 کانال/گروه", "admin:channel"), pbtn("📈 گزارش", "admin:report")],
        [pbtn("🖥 مدیریت پنل‌ها", "admin:panels"), pbtn("📦 مدیریت پلن‌ها", "admin:plans")],
        [pbtn("👑 مدیریت ادمین‌ها", "admin:admins")],
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
async def show_plans(query, uid):
    plans = db.get_plans(active_only=True)
    if not plans:
        await safe_edit(query, "❌ فعلاً پلنی تعریف نشده است.", reply_markup=back_kb())
        return
    text = "🔐 خرید اشتراک\n\nلطفاً پلن مورد نظر را انتخاب کنید:"
    rows = []
    for p in plans:
        rows.append([btn(plan_line(p), f"plan:{p['id']}")])
    rows.append([btn("🔙 بازگشت", "menu:back")])
    db.set_state(uid, "none")
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def show_wallet(query, uid):
    bal = db.get_balance(uid)
    kb = InlineKeyboardMarkup([
        [btn("💰 افزایش موجودی (کارت به کارت)", "wallet:charge")],
        [btn("👤 حساب کاربری", "acc:show")],
        [btn("🏠 بازگشت به منوی اصلی", "menu:back")],
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
    plans = db.get_plans(active_only=True)
    text = "💵 تعرفه‌ها (الگوی قیمت)\n\n"
    for p in plans:
        text += plan_line(p) + "\n"
    await safe_edit(query, text, reply_markup=back_kb())


# ---------- ساخت سرویس ----------
def pick_panel(service, prefer_panel_id=None):
    """Load Balancing: خلوت‌ترین پنل فعال Tifusi با ظرفیت خالی که برای این سرویس گروه انتخاب کرده.
    اگر prefer_panel_id هنوز شرایط را دارد همان برمی‌گردد (یوزرنیم مشتری روی همان پنل چک شده بود)."""
    candidates = []
    for p in db.get_panels(active_only=True):
        if is_legacy_panel(p) or service not in db.get_service_map(p["id"]):
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
    """سرویس‌هایی (به ترتیب SERVICES) که حداقل یک پنل فعال با ظرفیت خالی برایشان گروه دارد."""
    return [s for s in SERVICES if pick_panel(s)]


def panel_client(panel):
    return TifusiPanelAPI(panel["url"], panel["username"], panel["password"])


def create_service_on_panel(user_id, plan, service, username, panel_id=None):
    """ساخت کاربر روی Tifusi Panel با گروهِ انتخاب‌شده برای این سرویس. رمز را ربات نمی‌سازد؛
    پنل لینک اشتراک و کد اپ صادر می‌کند و همان‌ها به مشتری تحویل داده می‌شوند."""
    if service not in SERVICES:
        # مثلاً رسید در انتظارِ یک خرید از نسخه‌ی قبلی ربات — خطا باعث بازگشت خودکار وجه می‌شود
        raise PanelError("این سرویس دیگر فروخته نمی‌شود؛ لطفاً یک سرویس جدید بخرید")
    panel = pick_panel(service, panel_id)
    if not panel:
        raise PanelError(f"ظرفیت پنل‌های سرویس «{SERVICES[service]}» تکمیل است یا پنلی فعال نیست")
    gid = int(db.get_service_map(panel["id"])[service]["inbound_id"] or 0)
    expire_at = now() + plan["days"] * 86400
    client = panel_client(panel)
    client.login()
    # گروه ۰ همان «سرورهای عمومی» است و به پنل فرستاده نمی‌شود (group_ids خالی)
    res = client.add_user([gid] if gid else [], username, plan["volume_gb"], expire_at)
    oid = db.create_order({
        "user_id": user_id, "panel_id": panel["id"], "plan_id": plan["id"],
        "protocol": service, "username": username, "password": "", "inbound_id": gid,
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


async def send_order_qr(context, chat_id, order, panel):
    """ارسال QR لینک اشتراک با کپشن نام سرویس، یوزرنیم و کد اپ؛ در صورت خطا فقط False."""
    png = qr_png(order["sub_url"])
    if not png:
        return False
    caption = (f"{service_name(order['protocol'])}\n"
               f"👤 یوزرنیم: {order['username']}\n"
               f"🔢 کد اپ: {app_code_text(order, panel)}")
    try:
        await context.bot.send_photo(chat_id, png, caption=caption)
        return True
    except Exception as e:
        log.warning("send QR failed for %s: %s", chat_id, e)
        return False


def app_guide_text(service):
    """لینک اپ‌ها و راهنمای کوتاه اتصال — برای همه‌ی سرویس‌ها یکسان، به‌جز نکته‌ی v2rayNG برای Xray."""
    text = (f"📲 اپ Tifusi VPN:\n"
            f"🤖 اندروید: {APP_ANDROID_URL}\n"
            f"🪟 ویندوز: {APP_WINDOWS_URL}\n\n"
            f"📌 در اپ Tifusi VPN (اندروید/ویندوز) کد اپ را در تب «سرورها» وارد کنید.\n"
            f"🍎 آیفون: لینک اشتراک را در Safari باز کنید.")
    if service == "xray":
        text += "\n🌐 لینک اشتراک Xray در v2rayNG و Streisand هم کار می‌کند."
    return text


async def deliver_service(context, chat_id, order, panel):
    """ارسال اطلاعات سرویس به کاربر: متن (کد اپ + لینک اشتراک + لینک اپ‌ها) و بعد تصویر QR لینک اشتراک."""
    dt = datetime.datetime.fromtimestamp(order["expire_at"]).strftime("%Y-%m-%d %H:%M")
    text = (
        f"✅ سرویس شما ساخته شد!\n\n"
        f"{service_name(order['protocol'])} — #{order['id']}\n"
        f"🖥 پنل: {md(panel['name'])} {md(panel['location'])}\n"
        f"📦 حجم: {vol_text(order['volume_gb'])}\n"
        f"⏳ اعتبار: {order['days']} روز — تا {dt}\n\n"
        f"👤 یوزرنیم: `{order['username']}`\n"
        f"🔢 کد اپ: `{app_code_text(order, panel)}`\n"
        f"🔗 لینک اشتراک:\n`{order['sub_url'] or '-'}`\n\n"
        f"{app_guide_text(order['protocol'])}\n\n"
        f"📚 آموزش کامل در منوی «📚 آموزش».")
    await context.bot.send_message(chat_id, text, parse_mode="Markdown")
    await send_order_qr(context, chat_id, order, panel)


# ---------- تمدید ----------
def do_renew(order, plan):
    """تمدید روی همان پنل Tifusi — همان کاربر به‌روز می‌شود تا لینک اشتراک و کد اپ عوض نشوند؛
    اگر کاربر روی پنل حذف شده بود، با همان یوزرنیم و گروه سرویس دوباره ساخته می‌شود."""
    if order_is_legacy(order):
        raise PanelError("سرویس قدیمی قابل تمدید نیست؛ لطفاً سرویس جدید بخرید")
    panel = db.get_panel(order["panel_id"])
    if not panel:
        raise PanelError("پنل این سرویس حذف شده است")
    client = panel_client(panel)
    client.login()
    base = max(now(), order["expire_at"])
    expire_at = base + plan["days"] * 86400
    res = client.renew_user(order["username"], plan["volume_gb"], expire_at)
    if res is None:
        # گروه فعلی سرویس روی پنل؛ اگر ادمین آن را برداشته، همان گروهی که سفارش با آن ساخته شده بود
        grp = db.get_service_map(panel["id"]).get(order["protocol"])
        gid = int((grp["inbound_id"] if grp else order["inbound_id"]) or 0)
        res = client.add_user([gid] if gid else [], order["username"], plan["volume_gb"], expire_at)
    db.update_order(order["id"], expire_at=expire_at, volume_gb=plan["volume_gb"], days=plan["days"],
                    price=plan["price"], plan_id=plan.get("id", order["plan_id"]) or order["plan_id"],
                    status="active", sub_url=res["subscription_url"], app_code=res["app_code"])
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
        icon = name.split()[0]
        status = "" if o["status"] == "active" else " ⏳(درخواست حذف)"
        text += f"{icon} {o['username']} ← {name}\n"
        rows.append([btn(f"{icon} {o['username']}{status}", f"svc:{o['id']}")])
    rows.append([btn("🔙 بازگشت", "menu:back")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def show_service_detail(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid:
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    panel = db.get_panel(o["panel_id"])
    pname = panel["name"] if panel else "حذف‌شده"
    dt = datetime.datetime.fromtimestamp(o["expire_at"]).strftime("%Y-%m-%d — %H:%M")

    if order_is_legacy(o):
        # سفارش نسخه‌ی قبلی ربات: فقط نمایش — تمدید و حذف از اینجا ممکن نیست
        creds = f"👤 یوزرنیم: `{o['username']}`"
        if o["password"]:
            creds += f"\n🔑 پسورد: `{o['password']}`"
        if o["sub_url"]:
            creds += f"\n🔗 لینک اشتراک: `{o['sub_url']}`"
        text = (f"{md(order_name(o))} — #{o['id']}\n🖥 پنل: {md(pname)}\n\n{creds}\n"
                f"📦 حجم: {vol_text(o['volume_gb'])}\n"
                f"⏳ {remaining_text(o['expire_at'])} | 🕓 {dt}\n\n{LEGACY_ORDER_TEXT}")
        rows = [[btn("🔐 خرید اشتراک جدید", "menu:buy")],
                [btn("🏠 بازگشت به لیست سرویس‌ها", "menu:services")]]
        await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows), parse_mode="Markdown")
        return

    # مصرف از همان پنلی که سرویس روی آن ساخته شده
    usage_line = "📊 وضعیت مصرف: در دسترس نیست (پنل پاسخ نمی‌دهد)"
    if not o["volume_gb"]:
        usage_line = "📦 حجم: نامحدود ♾ (بدون محدودیت مصرف)"
    elif panel:
        try:
            client = panel_client(panel)
            await asyncio.to_thread(client.login)
            used_bytes = await asyncio.to_thread(client.usage, o["username"])
            if used_bytes is not None:
                used = gb(used_bytes)
                total = o["volume_gb"]
                left = max(0, round(total - used, 2))
                usage_line = f"📊 وضعیت مصرف:\n📦 {total} گیگ | 🔻 {used} گیگ | ✅ {left} گیگ باقی"
        except Exception:
            pass

    creds = (f"👤 یوزرنیم: `{o['username']}`\n"
             f"🔢 کد اپ: `{app_code_text(o, panel)}`\n"
             f"🔗 لینک اشتراک: `{o['sub_url'] or '-'}`\n"
             f"📲 اندروید: {APP_ANDROID_URL}\n🪟 ویندوز: {APP_WINDOWS_URL}")
    text = (f"{service_name(o['protocol'])} — #{o['id']}\n"
            f"🖥 پنل: {md(pname)}\n\n{creds}\n\n{usage_line}\n"
            f"⏳ {remaining_text(o['expire_at'])} | 🕓 {dt}")
    rows = []
    if o["status"] == "active":
        rows.append([btn("♻️ تمدید سرویس", f"renew:{o['id']}")])
        if o["sub_url"]:
            rows.append([btn("📷 QR code", f"qr:{o['id']}")])
        rows.append([btn("🔄 بروزرسانی اطلاعات", f"svc:{o['id']}")])
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
    kb = InlineKeyboardMarkup([[btn("💰 افزایش موجودی", "wallet:charge")],
                               [btn("🏠 بازگشت به منوی اصلی", "menu:back")]])
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
    orders = [o for o in db.get_user_orders(uid) if o["status"] == "active"]
    renewable = [o for o in orders if not order_is_legacy(o)]
    if not renewable:
        text = "❌ سرویس فعالی برای تمدید ندارید.\nاول از «🔐 خرید اشتراک» سرویس بخر."
        if orders:
            text += "\n\nℹ️ سرویس‌های نسخه‌ی قبلی ربات قابل تمدید نیستند؛ لطفاً سرویس جدید بخرید."
        await msg.reply_text(text)
        return
    rows = [[btn(f"♻️ {o['username']} — {vol_text(o['volume_gb'])}", f"renew:{o['id']}")] for o in renewable]
    await msg.reply_text(f"♻️ تمدید سرویس\n\nکدام سرویس را تمدید می‌کنی؟",
                         reply_markup=InlineKeyboardMarkup(rows))


# ---------- پرداخت ----------
def pay_kb():
    return InlineKeyboardMarkup([
        [btn("🏦 پرداخت از کیف پول", "pay:wallet")],
        [btn("💳 کارت به کارت", "pay:card")],
        [btn("❌ بستن لیست", "menu:buy")],
    ])


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
    if db.get_balance(uid) < plan["price"]:
        await safe_edit(query, "❌ موجودی کیف پول کافی نیست. لطفاً ابتدا شارژ کنید.",
                        reply_markup=InlineKeyboardMarkup([[btn("➕ شارژ کیف پول", "wallet:charge")],
                                                           [btn("🔙 بازگشت", "menu:back")]]))
        return
    await safe_edit(query, "♻️ در حال ساخت سرویس... لطفاً چند ثانیه صبر کنید.")
    bal_before = db.get_balance(uid)
    db.add_balance(uid, -plan["price"])
    try:
        order, panel = await asyncio.to_thread(
            create_service_on_panel, uid, plan, data["protocol"], data["username"], data.get("panel_id"))
    except Exception as e:
        db.add_balance(uid, plan["price"])  # بازگشت وجه
        await context.bot.send_message(uid, f"❌ خطا در ساخت سرویس: {e}\n💰 مبلغ به کیف پول برگشت.")
        return
    db.set_state(uid, "none")
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
def legacy_order_kb(oid):
    return InlineKeyboardMarkup([[btn("🔐 خرید اشتراک جدید", "menu:buy")],
                                 [btn("🔙 بازگشت", f"svc:{oid}")]])


async def renew_menu(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid or o["status"] != "active":
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    if order_is_legacy(o):
        await safe_edit(query, LEGACY_ORDER_TEXT, reply_markup=legacy_order_kb(oid))
        return
    plans = db.get_plans(active_only=True)
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
    if not o or not plan or o["user_id"] != uid:
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    if order_is_legacy(o):
        await safe_edit(query, LEGACY_ORDER_TEXT, reply_markup=legacy_order_kb(oid))
        return
    kb = InlineKeyboardMarkup([
        [btn("🏦 پرداخت از کیف پول", f"rnw:w:{oid}:{pid}")],
        [btn("💳 کارت به کارت", f"rnw:c:{oid}:{pid}")],
        [btn("🔙 بازگشت", f"renew:{oid}")],
    ])
    await safe_edit(query,
        f"♻️ تمدید سرویس «{o['username']}»\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 پلن جدید: {plan_label(plan)}\n"
        f"💰 مبلغ: {fmt(plan['price'])} تومان\n\n"
        f"✅ یوزرنیم، کد اپ و لینک اشتراک ثابت می‌مانند.\nروش پرداخت را انتخاب کن:",
        reply_markup=kb)


async def do_renew_and_deliver(query, context, uid, oid, plan_id=None):
    o = db.get_order(oid)
    p = db.get_plan(plan_id) if plan_id else db.get_plan(o["plan_id"])
    plan = dict(p) if p else {"id": o["plan_id"], "volume_gb": o["volume_gb"], "days": o["days"], "price": o["price"]}
    try:
        new_o, panel = await asyncio.to_thread(do_renew, o, plan)
    except Exception as e:
        raise PanelError(str(e))
    dt = datetime.datetime.fromtimestamp(new_o["expire_at"]).strftime("%Y-%m-%d %H:%M")
    await context.bot.send_message(uid,
        f"✅ سرویس {new_o['username']} تمدید شد!\n\n"
        f"📦 پلن جدید: {vol_text(new_o['volume_gb'])} — {new_o['days']} روز\n"
        f"👤 یوزرنیم: `{new_o['username']}`\n"
        f"🔢 کد اپ: `{app_code_text(new_o, panel)}`\n"
        f"🔗 لینک اشتراک: `{new_o['sub_url'] or '-'}`\n"
        f"⏳ اعتبار جدید: تا {dt}",
        parse_mode="Markdown")


# ---------- درخواست حذف ----------
async def delreq_confirm(query, uid, oid):
    o = db.get_order(oid)
    if not o or o["user_id"] != uid:
        await safe_edit(query, "❌ سرویس یافت نشد.", reply_markup=back_kb())
        return
    if order_is_legacy(o):
        await safe_edit(query, LEGACY_ORDER_TEXT, reply_markup=legacy_order_kb(oid))
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
        [btn("❌ رد پرداخت", f"rc:no:{rid}")],
        [btn("⭕️ بلاک کردن کاربر", f"rc:block:{rid}")],
        [btn("⭕️ شارژ دستی", f"rc:manual:{rid}")],
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
    all_panels = db.get_panels()
    panels = [p for p in all_panels if not is_legacy_panel(p)]
    p_old = len(all_panels) - len(panels)
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
            f"🟢 فعال: {p_on} | 🔴 آفلاین: {p_off} | ⚪ غیرفعال: {p_ina} | مجموع: {len(panels)}"
            f"{f' | 🗄 قدیمی: {p_old}' if p_old else ''}\n"
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
                create_service_on_panel, r["user_id"], plan, meta["protocol"], meta["username"], meta.get("panel_id"))
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
        if not o:
            await query.message.reply_text("❌ سفارش یافت نشد.")
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
        [btn("🛍 مشاهده سرویس‌ها", f"au:svcs:{u['id']}")],
        [btn("🔙 بازگشت", "admin:menu")],
    ])
    await safe_edit(query, text, reply_markup=kb)


# ---------- تنظیمات ----------
SETTING_KEYS = [
    ("card_number", "🏦 شماره کارت"),
    ("card_name", "👤 صاحب حساب"),
    ("support_id", "☎️ پشتیبانی"),
    ("price_per_gb", "💵 قیمت هر گیگ"),
    ("test_volume_gb", "🔑 حجم تست"),
    ("test_days", "🔑 مدت تست"),
    ("faq_text", "❓ سوالات متداول"),
]


async def admin_settings(query):
    # اکانت تست پیش‌فرض خاموش است؛ کلید روشن/خاموش کنار حجم و مدت تست نمایش داده می‌شود
    test_label = f"🔑 اکانت تست: {'فعال' if db.setting('test_enabled', '0') == '1' else 'غیرفعال'}"
    text = f"⚙️ تنظیمات عمومی\n"
    rows = []
    for key, label in SETTING_KEYS:
        if key == "test_volume_gb":
            text += test_label + "\n"
            rows.append([btn(test_label, "tgl:test_enabled")])
        val = db.setting(key, "—")
        if key == "faq_text" and val != "—":
            val = "✅ تنظیم شده"
        text += f"{label}: {val}\n"
        rows.append([btn(f"✏️ {label}", f"set:{key}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_channel(query):
    text = (f"📢 تنظیم کانال/گروه گزارش\n\n"
            f"کانال: {db.setting('channel_id', '—')}\nگروه: {db.setting('group_id', '—')}\n\n"
            f"آیدی را با @ یا عدد -100 وارد کنید. ربات باید در کانال/گروه ادمین باشد.")
    kb = InlineKeyboardMarkup([
        [btn("✏️ آیدی کانال", "set:channel_id")],
        [btn("✏️ آیدی گروه", "set:group_id")],
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
        [btn("📅 هفتگی", "report:week")],
        [btn("📅 ماهانه", "report:month")],
        [btn("🔙 بازگشت", "admin:menu")],
    ])
    await safe_edit(query, f"📈 گزارش\n\nبازه گزارش را انتخاب کنید:", reply_markup=kb)


# ---------- مدیریت پلن‌ها ----------
async def admin_plans(query):
    plans = db.get_plans()
    rows = [[btn("➕ افزودن پلن جدید", "pl:add")]]
    text = f"📦 مدیریت پلن‌ها:\n🧺 فعال | 🔴 غیرفعال\n"
    for p in plans:
        st = "🧺" if p["active"] else "🔴"
        rows.append([btn(f"{st} #{p['id']} | {plan_label(p)}", f"pl:{p['id']}")])
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


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
    ul_text = f"{ul} کاربره" if ul else "پیروی از اینباند"
    text = f"📦 پلن #{p['id']}\n🛍️ {plan_label(p)}\n👥 لیمت دستگاه همزمان: {ul_text}\n📌 وضعیت: {st}"
    kb = InlineKeyboardMarkup([
        [btn("✏️ عنوان", f"ple:{pid}:title")],
        [btn("✏️ حجم (گیگ)", f"ple:{pid}:volume_gb")],
        [btn("✏️ مدت (روز)", f"ple:{pid}:days")],
        [btn("✏️ قیمت (تومان)", f"ple:{pid}:price")],
        [btn("👥 تعداد کاربر (0 تا 5)", f"ple:{pid}:user_limit")],
        [btn("🔁 فعال / غیرفعال", f"pl:toggle:{pid}")],
        [btn("🗑 حذف پلن", f"pl:del:{pid}")],
        [btn("🔙 بازگشت", "admin:plans")],
    ])
    await safe_edit(query, text, reply_markup=kb)


# ---------- مدیریت پنل‌ها ----------
def panel_status_icon(p):
    if is_legacy_panel(p):
        return "🗄 قدیمی (غیرفعال)"
    return {"offline": "🔴 Offline", "inactive": "⚪ غیرفعال"}.get(p["status"], "🟢")


def service_map_text(panel_id):
    """نمایش نگاشت سرویس ← گروه یک پنل."""
    smap = db.get_service_map(panel_id)
    lines = []
    for key, name in SERVICES.items():
        g = smap.get(key)
        if g:
            lines.append(f"  ✅ {name} ← گروه «{g['remark'] or '-'}» (#{g['inbound_id']})")
        else:
            lines.append(f"  ❌ {name} ← روی این پنل فروخته نمی‌شود")
    return "\n".join(lines)


def groups_for_state(groups):
    """گروه‌های list_groups به شکل فشرده برای ذخیره در state (شناسه ۰ = سرورهای عمومی)."""
    return [{"id": int(g["inbound_id"] or 0), "name": g["remark"] or f"#{g['inbound_id']}"} for g in groups]


def map_step_view(sd):
    """یک مرحله از انتخاب گروه: برای سرویس شماره‌ی step یک گروه یا «روی این پنل فروخته نشود».
    هم در جادوی افزودن پنل (ap_map) و هم در انتخاب مجدد برای پنل موجود (pm_map) استفاده می‌شود."""
    keys = list(SERVICES)
    step = sd.get("step", 0)
    key = keys[step]
    text = (f"🧩 انتخاب گروه سرویس‌ها ({step + 1}/{len(keys)})\n\n"
            f"گروه پنل تعیین می‌کند کاربر به کدام سرورها دسترسی دارد؛ سروری که در هیچ گروهی نیست برای همه است.\n\n")
    for k in keys[:step]:
        g = sd["map"].get(k)
        text += f"{'✅' if g else '❌'} {SERVICES[k]} ← {('«' + g['name'] + '»') if g else 'فروخته نمی‌شود'}\n"
    text += f"\n👉 سرویس «{SERVICES[key]}» روی کدام گروه فروخته شود؟"
    cur = sd.get("current", {}).get(key)
    if sd.get("panel_id"):
        text += f"\n(انتخاب فعلی: {('«' + cur + '»') if cur else 'فروخته نمی‌شود'})"
    rows = [[btn(f"👥 {g['name']}", f"apm:{key}:{g['id']}")] for g in sd["groups"]]
    rows.append([btn("🚫 روی این پنل فروخته نشود", f"apm:{key}:x")])
    rows.append([btn("🔙 انصراف", f"pb:{sd['panel_id']}" if sd.get("panel_id") else "admin:panels")])
    return text, InlineKeyboardMarkup(rows)


async def admin_panels(query):
    panels = db.get_panels()
    rows = [[btn("➕ افزودن پنل", "pb:add")]]
    text = f"🖥 مدیریت پنل‌های Tifusi Panel:\n\n"
    for p in panels:
        cnt = db.count_panel_active_orders(p["id"])
        text += f"{panel_status_icon(p)} #{p['id']} {p['name']} — {p['location']} — {cnt}/{p['max_users']} کاربر\n"
        suffix = "قدیمی" if is_legacy_panel(p) else f"{cnt}/{p['max_users']}"
        rows.append([btn(f"#{p['id']} {p['name']} ({suffix})", f"pb:{p['id']}")])
    if not panels:
        text += "پنلی ثبت نشده.\n"
    if any(is_legacy_panel(p) for p in panels):
        text += "\nℹ️ پنل‌های «قدیمی» از نسخه‌ی قبلی ربات هستند و در فروش، تمدید و چک سلامت استفاده نمی‌شوند."
    rows.append([btn("🔙 بازگشت", "admin:menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(rows))


async def admin_panel_detail(query, pid):
    p = db.get_panel(pid)
    if not p:
        await safe_edit(query, "❌ پنل یافت نشد.")
        return
    cnt = db.count_panel_active_orders(pid)
    if is_legacy_panel(p):
        text = (f"🗄 پنل #{p['id']}: {p['name']} — قدیمی (غیرفعال)\n\n"
                f"🌐 آدرس: {p['url']}\n📍 موقعیت: {p['location'] or '—'}\n"
                f"👥 سفارش‌های فعال ثبت‌شده: {cnt}\n\n"
                f"⚠️ این پنل از نسخه‌ی قبلی ربات است و Tifusi Panel نیست؛ برای فروش، تمدید و چک سلامت "
                f"استفاده نمی‌شود و سرویس‌های قبلی کاربرانش فقط نمایش داده می‌شوند.")
        kb = InlineKeyboardMarkup([
            [btn("🗑 حذف پنل", f"pb:del:{pid}")],
            [btn("🔙 بازگشت", "admin:panels")],
        ])
        await safe_edit(query, text, reply_markup=kb)
        return
    icons = {"active": "🟢 فعال", "inactive": "⚪ غیرفعال", "offline": "🔴 Offline"}
    text = (f"🖥 پنل #{p['id']}: {p['name']} (Tifusi Panel)\n\n"
            f"🌐 آدرس: {p['url']}\n👤 یوزر: {p['username']}\n"
            f"📍 موقعیت: {p['location'] or '—'}\n"
            f"📌 وضعیت: {icons.get(p['status'], p['status'])}\n"
            f"👥 کاربران: {cnt}/{p['max_users']}\n\n"
            f"🧩 سرویس‌ها و گروه‌ها:\n{service_map_text(pid)}")
    kb = InlineKeyboardMarkup([
        [btn("🔄 تست اتصال", f"pb:test:{pid}")],
        [btn("🔁 فعال / غیرفعال", f"pb:toggle:{pid}")],
        [btn("🧩 انتخاب گروه سرویس‌ها", f"pbm:{pid}")],
        [btn("✏️ ویرایش پنل", f"pb:edit:{pid}")],
        [btn("🗑 حذف پنل", f"pb:del:{pid}")],
        [btn("🔙 بازگشت", "admin:panels")],
    ])
    await safe_edit(query, text, reply_markup=kb)


async def admin_panel_test(query, pid):
    p = db.get_panel(pid)
    if not p:
        return
    back = InlineKeyboardMarkup([[btn("🔙 بازگشت", f"pb:{pid}")]])
    if is_legacy_panel(p):
        await safe_edit(query, f"🗄 پنل {p['name']} قدیمی است و تست نمی‌شود.", reply_markup=back)
        return
    await safe_edit(query, f"🔄 در حال تست پنل {p['name']}...")
    try:
        ms = await asyncio.to_thread(panel_client(p).ping)
        await query.message.reply_text(f"✅ پنل {p['name']} — Online ({ms}ms)", reply_markup=back)
    except Exception as e:
        await query.message.reply_text(f"❌ پنل {p['name']} — Offline\nخطا: {e}", reply_markup=back)


async def admin_panel_edit(query, pid):
    kb = InlineKeyboardMarkup([
        [btn("✏️ نام", f"pbe:{pid}:name")],
        [btn("✏️ آدرس", f"pbe:{pid}:url")],
        [btn("✏️ یوزرنیم", f"pbe:{pid}:username")],
        [btn("✏️ پسورد", f"pbe:{pid}:password")],
        [btn("✏️ موقعیت", f"pbe:{pid}:location")],
        [btn("✏️ سقف کاربر", f"pbe:{pid}:max_users")],
        [btn("🧩 انتخاب گروه سرویس‌ها", f"pbm:{pid}")],
        [btn("🔙 بازگشت", f"pb:{pid}")],
    ])
    await safe_edit(query, "✏️ کدام مورد را ویرایش می‌کنید؟", reply_markup=kb)


async def finish_panel_wizard(message, uid, draft):
    draft["type"] = "tifusi"
    pid = db.add_panel(draft)
    db.set_service_map(pid, draft.get("map", {}))
    db.set_state(uid, "none")
    note = ("از این پس کاربران جدید به‌صورت خودکار روی خلوت‌ترین پنل ساخته می‌شوند." if draft.get("map") else
            "⚠️ هیچ سرویسی برای این پنل انتخاب نشد؛ تا از «🧩 انتخاب گروه سرویس‌ها» گروهی انتخاب نکنید، "
            "روی این پنل فروشی انجام نمی‌شود.")
    await message.reply_text(
        f"✅ پنل «{draft['name']}» با موفقیت ثبت شد!\n\n"
        f"🌐 {draft['url']}\n📍 {draft['location']}\n👥 سقف: {draft['max_users']} کاربر\n\n"
        f"🧩 سرویس‌ها:\n{service_map_text(pid)}\n\n{note}",
        reply_markup=main_menu_kb(uid))


async def admin_panels_cap(query):
    panels = db.get_panels()
    if not panels:
        await safe_edit(query, "پنلی ثبت نشده است.",
                        reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
        return
    text = f"🔧 قابلیت‌ها و ظرفیت پنل‌ها:\n\n"
    icons = {"active": "🟢", "inactive": "⚪", "offline": "🔴"}
    for p in panels:
        if is_legacy_panel(p):
            text += f"🗄 {p['name']} — قدیمی (غیرفعال)\n"
            continue
        cnt = db.count_panel_active_orders(p["id"])
        smap = db.get_service_map(p["id"])
        sold = [SERVICES[k] for k in SERVICES if k in smap]
        text += (f"{icons.get(p['status'], '⚪')} {p['name']} — {cnt}/{p['max_users']} کاربر\n"
                 f"   🧩 {', '.join(sold) if sold else '—'}\n")
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))


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
                await show_plans(query, uid)
            elif what == "services":
                await show_services(query, uid)
            return

        if cmd == "plan":
            db.set_state(uid, "buy_proto", {"plan_id": int(parts[1])})
            # فقط سرویس‌هایی که حداقل یک پنل فعال با ظرفیت خالی برایشان گروه دارد
            rows = [[btn(SERVICES[s], f"proto:{s}")] for s in available_services()]
            if not rows:
                await safe_edit(query, "❌ فعلاً ظرفیت خالی برای ساخت سرویس وجود ندارد. کمی بعد تلاش کن.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:buy")]]))
                return
            rows.append([btn("🔙 بازگشت", "menu:buy")])
            await safe_edit(query, "🧩 سرویس مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(rows))
            return

        if cmd == "proto":
            state, sd = db.get_state(uid)
            service = parts[1] if len(parts) > 1 else ""
            if service not in SERVICES or not sd.get("plan_id") or not pick_panel(service):
                # دکمه‌ی قدیمی یا سرویسی که الان ظرفیت ندارد
                await safe_edit(query, "❌ این سرویس الان در دسترس نیست. دوباره از «خرید اشتراک» شروع کنید.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "menu:buy")]]))
                return
            sd["protocol"] = service
            db.set_state(uid, "buy_username", sd)
            await safe_edit(query,
                f"👤 انتخاب نام کاربری\n\nیک نام کاربری دلخواه ارسال کنید\n\n"
                "⚠️ نام کاربری باید بدون @ ، فاصله و خط تیره باشد\n"
                "⚠️ نام کاربری باید انگلیسی باشد\n\n"
                "✅ نام‌های صحیح: ali12 | mahdi | ws1_ksdf\n"
                "❌ نام‌های نادرست: ali | tele@ | محسن | _mahdi",
                reply_markup=InlineKeyboardMarkup([[btn("🏠 بازگشت به منوی قبل", "menu:buy")]]))
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
            if o and o["user_id"] == uid and o["status"] == "active" and not order_is_legacy(o):
                if not await send_order_qr(context, uid, o, db.get_panel(o["panel_id"])):
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
            if not o or o["user_id"] != uid:
                return
            if order_is_legacy(o):
                await safe_edit(query, LEGACY_ORDER_TEXT, reply_markup=legacy_order_kb(oid))
                return
            p = db.get_plan(pid) if pid else db.get_plan(o["plan_id"])
            price = p["price"] if p else o["price"]
            plan_id = pid or o["plan_id"]
            if parts[1] == "w":
                if db.get_balance(uid) < price:
                    await safe_edit(query, "❌ موجودی کیف پول کافی نیست.",
                        reply_markup=InlineKeyboardMarkup([[btn("💰 افزایش موجودی", "wallet:charge")],
                                                           [btn("🔙 بازگشت", f"svc:{oid}")]]))
                    return
                await safe_edit(query, "♻️ در حال تمدید...")
                bal_before = db.get_balance(uid)
                db.add_balance(uid, -price)
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
                if o and o["user_id"] == uid and o["status"] == "active" and order_is_legacy(o):
                    await safe_edit(query, LEGACY_ORDER_TEXT, reply_markup=legacy_order_kb(oid))
                elif o and o["user_id"] == uid and o["status"] == "active":
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
                [btn("💰 افزایش موجودی", "wallet:charge")],
                [btn("🔙 بازگشت", "menu:back")],
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
                    f"🆕 نسخه ربات: {db.setting('bot_version', '3.0')}\n"
                    f"📅 تاریخ نسخه: {db.setting('bot_version_date', '—')}",
                    reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:menu")]]))
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
            if parts[1] == "ok":
                panel = db.get_panel(o["panel_id"])
                err = ""
                if order_is_legacy(o):
                    # درخواست حذفی که قبل از به‌روزرسانی ثبت شده؛ پنل قدیمی از ربات مدیریت نمی‌شود
                    err = "سرویس قدیمی است؛ در صورت نیاز کاربر را دستی از پنل قبلی حذف کنید"
                elif panel:
                    try:
                        client = panel_client(panel)
                        await asyncio.to_thread(client.login)
                        await asyncio.to_thread(client.del_user, o["username"])
                    except Exception as e:
                        err = str(e)
                # بازگشت وجه متناسب با روزهای باقی‌مانده
                refund = 0
                if o["expire_at"] > now() and o["days"]:
                    refund = int(o["price"] * (o["expire_at"] - now()) / (o["days"] * 86400))
                db.update_order(oid, status="deleted")
                if refund:
                    db.add_balance(o["user_id"], refund)
                await context.bot.send_message(o["user_id"],
                    f"🗑 سرویس {o['username']} حذف شد.\n💰 مبلغ {fmt(refund)} تومان به کیف پول شما برگشت.")
                await safe_edit(query, f"✅ سرویس #{oid} حذف شد و {fmt(refund)} تومان برگشت." +
                                (f"\n⚠️ خطای پنل: {err}" if err else ""))
            else:
                db.update_order(oid, status="active")
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
            if not p or is_legacy_panel(p):
                await safe_edit(query, "❌ این پنل Tifusi Panel نیست یا حذف شده است.",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", "admin:panels")]]))
                return
            await safe_edit(query, f"🔄 در حال دریافت گروه‌های پنل {p['name']}...")
            try:
                client = panel_client(p)
                await asyncio.to_thread(client.login)
                groups = await asyncio.to_thread(client.list_groups)
            except Exception as e:
                await safe_edit(query, f"❌ اتصال ناموفق: {e}",
                                reply_markup=InlineKeyboardMarkup([[btn("🔙 بازگشت", f"pb:{pid}")]]))
                return
            current = {k: (r["remark"] or f"#{r['inbound_id']}") for k, r in db.get_service_map(pid).items()}
            sd = {"panel_id": pid, "groups": groups_for_state(groups), "map": {}, "step": 0, "current": current}
            db.set_state(uid, "pm_map", sd)
            text, kb = map_step_view(sd)
            await safe_edit(query, text, reply_markup=kb)
            return

        if cmd == "apm":
            state, sd = db.get_state(uid)
            keys = list(SERVICES)
            step = sd.get("step", 0)
            if state not in ("ap_map", "pm_map") or step >= len(keys) or len(parts) < 3 or parts[1] != keys[step]:
                return  # دکمه‌ی قدیمی یا دوبار زده‌شده
            if parts[2] != "x":
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
            if parts[1] == "add":
                db.set_state(uid, "plan_add_title")
                await safe_edit(query, "➕ افزودن پلن\n\n1) عنوان پلن را بنویسید (مثلاً: 20 گیگ یک کاربره یک ماهه یا نامحدود دو کاربره یک ماهه):")
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
            await msg.reply_text("❌ نام کاربری نامعتبر است.\nباید با حرف انگلیسی شروع شود، ۳ تا ۲۰ کاراکتر، بدون @ و فاصله و خط تیره:")
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
            client = panel_client(panel)
            await asyncio.to_thread(client.login)
            if await asyncio.to_thread(client.get_user, text):
                await msg.reply_text("❌ این یوزرنیم قبلاً روی سرور استفاده شده. لطفاً یوزرنیم دیگری انتخاب کنید:")
                return True
        except Exception:
            pass
        # مرحله‌ی رمز حذف شده: پنل خودش لینک اشتراک و کد اپ صادر می‌کند
        sd["username"] = text
        sd["panel_id"] = panel["id"]
        db.set_state(uid, "buy_pay", sd)
        await msg.reply_text(
            f"🧾 پیش‌فاکتور\n"
            f"📦 {md(plan_label(plan))}\n"
            f"🧩 سرویس: {SERVICES[service]}\n👤 یوزرنیم: `{text}`\n"
            f"💰 مبلغ: {fmt(plan['price'])} تومان\n\n"
            f"🔑 رمز لازم نیست؛ بعد از ساخت سرویس، کد اپ و لینک اشتراک برایتان ارسال می‌شود.\n"
            f"⚠️ سرویس فقط بعد از پرداخت و تایید، ساخته و فعال می‌شود.\n\nروش پرداخت:",
            reply_markup=pay_kb(), parse_mode="Markdown")
        return True

    # ---------- شارژ کیف پول ----------
    if state == "charge_amount":
        try:
            amount = int(text.replace(",", "").replace("٬", ""))
        except ValueError:
            await msg.reply_text("❌ فقط عدد وارد کنید (به تومان):")
            return True
        if not (20000 <= amount <= 50000000):
            await msg.reply_text("❌ مبلغ باید بین ۲۰٬۰۰۰ تا ۵٬۰۰۰٬۰۰۰ تومان باشد:")
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
            [btn("🛍 مشاهده سرویس‌ها", f"au:svcs:{u['id']}")]])
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
        await msg.reply_text("۴) این پلن چند کاربره باشد؟ (عدد 1 تا 5)\n\n"
                             "یعنی حداکثر چند دستگاه بتوانند همزمان با این اکانت وصل شوند.\n"
                             "۰ یعنی بدون لیمت اختصاصی — از User Limit اینباند پیروی می‌کند.")
        return True

    if state == "plan_add_users" and is_admin(uid):
        if not text.isdigit() or not (0 <= int(text) <= 5):
            await msg.reply_text("❌ عددی بین 0 تا 5 وارد کنید:")
            return True
        vol = parse_volume_from_title(sd.get("title", ""))
        db.add_plan(vol, sd["days"], sd["price"], sd.get("title", ""), int(text))
        db.set_state(uid, "none")
        ul_txt = f"{text} کاربره" if int(text) else "پیروی از اینباند"
        await msg.reply_text(f"✅ پلن «{sd.get('title')}» — {fmt(sd['price'])} تومان — {sd['days']} روز — 👥 {ul_txt} اضافه شد.")
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
            await msg.reply_text("❌ تعداد کاربر باید بین 0 تا 5 باشد (۰ = پیروی از لیمت اینباند):")
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
        wait = await msg.reply_text("🔄 در حال تست اتصال و دریافت گروه‌های پنل...")
        try:
            client = TifusiPanelAPI(sd["url"], sd["username"], sd["password"])
            await asyncio.to_thread(client.login)
            # پنلی که گروه ندارد یک ردیف «سرورهای عمومی» با شناسه‌ی ۰ برمی‌گرداند
            groups = await asyncio.to_thread(client.list_groups)
        except Exception as e:
            await wait.edit_text(f"❌ اتصال ناموفق: {e}\n\nاز اول شروع کنید: 🖥 مدیریت پنل‌ها ← ➕ افزودن پنل")
            db.set_state(uid, "none")
            return True
        sd.update({"groups": groups_for_state(groups), "map": {}, "step": 0})
        db.set_state(uid, "ap_map", sd)
        view_text, kb = map_step_view(sd)
        await wait.edit_text("✅ اتصال موفق!\n\n" + view_text, reply_markup=kb)
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
        val = int(text) if field == "max_users" else text
        db.update_panel(pid, **{field: val})
        db.set_state(uid, "none")
        await msg.reply_text("✅ پنل به‌روزرسانی شد.")
        return True

    return False


MENU_ACTIONS = {
    "🔐 خرید اشتراک": "buy", "♻️ تمدید سرویس": "renew_menu", "🔑 اکانت تست": "test",
    "🎲 گردونه شانس": "wheel", "🎡 گردونه شانس": "wheel",
    "🛍 سرویس‌های من": "services", "🏦 کیف پول + شارژ": "wallet", "🏦 کیف پول": "wallet",
    "💵 تعرفه اشتراک ها": "tariff", "💵 تعرفه‌ها": "tariff", "💵 تعرفه": "tariff",
    "👥 زیرمجموعه گیری": "referral", "👥 زیرمجموعه‌گیری": "referral",
    "📚 آموزش": "tutorial", "☎️ پشتیبانی": "support", "🧑‍💼 پنل مدیریت": "admin",
}


# مرحله‌هایی که ورودی متنی ندارند و منتظر دکمه‌اند
BUTTON_WAIT_STATES = ("buy_proto", "buy_pay", "charge_confirm", "ap_map", "pm_map")


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
        await show_plans(fq, uid)
    elif action == "renew_menu":
        await show_renew_menu(msg, uid)
    elif action == "test":
        await send_test_account(msg, context, uid)
    elif action == "wheel":
        await msg.reply_text("🎲 گردونه شانس به‌زودی فعال می‌شود! 🎁\nجوایز و تخفیف‌های هیجانی در راه است...")
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
            "username": sd["username"], "panel_id": sd.get("panel_id")})
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


# =================== جاب‌ها ===================
async def health_job(context: ContextTypes.DEFAULT_TYPE):
    """چک سلامت پنل‌ها هر ۵ دقیقه (فقط Tifusi Panel؛ پنل‌های قدیمی نادیده گرفته می‌شوند)."""
    for p in db.get_panels():
        if p["status"] == "inactive" or is_legacy_panel(p):
            continue  # غیرفعال دستی یا پنل قدیمی — از چرخه خارج است
        try:
            await asyncio.to_thread(panel_client(p).login)
            ok = True
        except Exception:
            ok = False
        if not ok and p["status"] == "active":
            db.update_panel(p["id"], status="offline")
            await notify_admin(context.bot, f"⚠️ پنل «{p['name']}» offline شد و از Load Balancing خارج شد!")
        elif ok and p["status"] == "offline":
            db.update_panel(p["id"], status="active")
            await notify_admin(context.bot, f"✅ پنل «{p['name']}» دوباره online شد.")


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


def main():
    if not BOT_TOKEN or not ADMIN_ID:
        raise SystemExit("❌ ابتدا BOT_TOKEN و ADMIN_ID را در بالای همین فایل (bot.py) پر کنید.")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(on_callback_admin, pattern=r"^(pb|pbe|pbm|apm|pl|ple):"))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_error_handler(on_error)
    if app.job_queue:
        app.job_queue.run_repeating(health_job, interval=300, first=60)
        app.job_queue.run_daily(daily_report_job, time=datetime.time(23, 0))
    log.info("🤖 ربات v4.0 روشن شد...")
    asyncio.set_event_loop(asyncio.new_event_loop())
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
