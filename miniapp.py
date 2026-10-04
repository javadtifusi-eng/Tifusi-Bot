"""مینی‌اپ تلگرام تیفوسی: سرور کوچک HTTP داخل همان پروسه‌ی ربات.

ربات (bot.py) موقع روشن شدن start() را صدا می‌زند و این سرور روی 127.0.0.1 گوش می‌دهد؛
Caddy جلوی آن HTTPS را می‌دهد. همه‌ی منطق خرید، کیف پول و پنل از خود bot.py خوانده می‌شود
(ns = globals() همان فایل) تا دو نسخه از یک قانون نداشته باشیم.

احراز هویت: هر درخواست initData تلگرام را در هدر X-Init-Data می‌فرستد و با توکن ربات امضایش
چک می‌شود (https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)؛
پس هر کس فقط سرویس‌ها و موجودی خودش را می‌بیند.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

log = logging.getLogger("vpn_bot.miniapp")

HOST, PORT = "127.0.0.1", 8088
MINIAPP_URL = "https://app.bomalo.ir/"
INIT_DATA_MAX_AGE = 24 * 3600
PANEL_CACHE_SECONDS = 30
STATIC_DIR = Path(__file__).resolve().parent / "miniapp"
# سرویس‌هایی که مینی‌اپ می‌فروشد؛ «ikev2» همان پلن یکی برای IKEv2، L2TP و PPTP است
SHOP_SERVICES = {"ikev2": "L2TP و IKEv2", "xray": "V2Ray"}

ns = {}
_panel_cache = {}  # panel_id -> (time, {username: panel user})


def verify_init_data(init_data, bot_token):
    """شناسه‌ی کاربر تلگرام اگر امضای initData درست و تازه باشد، وگرنه None."""
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
    except ValueError:
        return None
    received = pairs.pop("hash", "")
    if not received:
        return None
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > INIT_DATA_MAX_AGE:
            return None
        user = json.loads(pairs.get("user", "{}"))
        return int(user["id"]), user
    except (ValueError, KeyError, TypeError):
        return None


@web.middleware
async def auth_mw(request, handler):
    if not request.path.startswith("/api/"):
        return await handler(request)
    found = verify_init_data(request.headers.get("X-Init-Data", ""), ns["BOT_TOKEN"])
    if not found:
        return web.json_response({"error": "auth"}, status=401)
    uid, tg_user = found
    db = ns["db"]
    u = db.ensure_user(uid, tg_user.get("username"), " ".join(
        x for x in (tg_user.get("first_name"), tg_user.get("last_name")) if x))
    if u["is_blocked"] and not ns["is_admin"](uid):
        return web.json_response({"error": "blocked"}, status=403)
    request["uid"] = uid
    return await handler(request)


def _panel_users(panel):
    """همه‌ی کاربرهای یک پنل (برای مصرف و وضعیت)، با کش کوتاه تا ۱۰۰ مشتری = یک درخواست."""
    hit = _panel_cache.get(panel["id"])
    if hit and time.time() - hit[0] < PANEL_CACHE_SECONDS:
        return hit[1]
    client = ns["panel_client"](panel)
    users, offset = {}, 0
    while True:
        page = client._call("/api/users", params={"offset": offset, "limit": 200}) or {}
        batch = page.get("users", [])
        users.update({u["username"]: u for u in batch})
        offset += len(batch)
        if not batch or offset >= int(page.get("total") or 0):
            break
    _panel_cache[panel["id"]] = (time.time(), users)
    return users


def _customer(order, pu):
    expire = int(order["expire_at"] or 0)
    left_days = max(0, -(-(expire - int(time.time())) // 86400)) if expire else None
    used = int((pu or {}).get("used_traffic") or 0)
    limit = int((pu or {}).get("data_limit") or 0) or int(order["volume_gb"] or 0) * 1073741824
    pstatus = (pu or {}).get("status") or "unknown"
    if pstatus in ("limited", "expired") or (left_days == 0 and expire):
        state = "bad"
    elif (left_days is not None and left_days <= 3) or (limit and used / limit > 0.85):
        state = "warn"
    else:
        state = "ok"
    sub = (order["sub_url"] or "").rstrip("/")
    return {
        "id": order["id"], "username": order["username"], "service": order["protocol"],
        "service_name": SHOP_SERVICES.get(order["protocol"]) or ns["service_name"](order["protocol"]),
        "used": used, "limit": limit, "expire": expire or None, "days_left": left_days,
        "panel_status": pstatus, "on": pstatus != "disabled", "state": state,
        "guide": sub + "/guide" if sub.startswith("https://") else None,
    }


async def api_me(request):
    uid = request["uid"]
    db = ns["db"]
    orders = db.get_user_orders(uid)
    return web.json_response({
        "id": uid, "balance": db.get_balance(uid), "orders": len(orders),
        "is_admin": bool(ns["is_admin"](uid)),
    })


async def api_customers(request):
    uid = request["uid"]
    db = ns["db"]
    orders = db.get_user_orders(uid)
    by_panel = {}
    for o in orders:
        by_panel.setdefault(o["panel_id"], []).append(o)
    out = []
    for pid, items in by_panel.items():
        panel = db.get_panel(pid)
        pusers = {}
        if panel:
            try:
                pusers = await asyncio.to_thread(_panel_users, panel)
            except Exception as e:  # پنل در دسترس نیست: از دیتابیس ربات نشان بده
                log.warning("miniapp: panel %s users failed: %s", pid, e)
        out += [_customer(o, pusers.get(o["username"])) for o in items]
    out.sort(key=lambda c: {"bad": 0, "warn": 1, "ok": 2}[c["state"]])
    stats = {k: sum(1 for c in out if c["state"] == k) for k in ("ok", "warn", "bad")}
    return web.json_response({"customers": out, "stats": stats, "total": len(out)})


async def api_plans(request):
    uid = request["uid"]
    db = ns["db"]
    shop = []
    for key, label in SHOP_SERVICES.items():
        plans = [ns["user_plan"](p["id"], uid) for p in db.get_plans(active_only=True, service=key)]
        plans = [p for p in plans if p]
        if not plans:
            continue
        plans.sort(key=lambda p: (p["volume_gb"] == 0, p["volume_gb"], p["user_limit"] or 0))
        shop.append({"service": key, "label": label, "plans": [
            {"id": p["id"], "gb": p["volume_gb"], "days": p["days"], "price": p["price"],
             "users": p["user_limit"] or 0, "title": p["title"]} for p in plans]})
    return web.json_response({"services": shop})


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def app_js(request):
    return web.FileResponse(STATIC_DIR / "app.js", headers={"Cache-Control": "no-store"})


async def start(application, bot_globals):
    """از post_init ربات صدا زده می‌شود."""
    ns.update(bot_globals)
    app = web.Application(middlewares=[auth_mw], client_max_size=8 * 1024 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/app.js", app_js)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/customers", api_customers)
    app.router.add_get("/api/plans", api_plans)
    if (STATIC_DIR / "assets").is_dir():
        app.router.add_static("/assets/", STATIC_DIR / "assets", append_version=False)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
    application.bot_data["miniapp_runner"] = runner
    log.info("miniapp listening on %s:%s", HOST, PORT)
    await set_tester_buttons(application.bot)


async def set_tester_buttons(bot):
    """دوره‌ی تست: دکمه‌ی منوی مینی‌اپ (کنار کادر پیام) فقط برای ادمین‌های اضافه‌شده (حساب‌های جواد).
    مشتری‌ها تا تأیید جواد چیزی نمی‌بینند."""
    from telegram import MenuButtonWebApp, WebAppInfo
    for uid in ns["get_admins"]():
        try:
            await bot.set_chat_menu_button(chat_id=uid, menu_button=MenuButtonWebApp(
                text="Tifusi", web_app=WebAppInfo(url=MINIAPP_URL)))
        except Exception as e:  # کسی که هنوز ربات را استارت نکرده
            log.info("miniapp menu button for %s skipped: %s", uid, e)
