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
import re
import secrets
import time
from types import SimpleNamespace
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
# همان وضعیت‌هایی که db.get_user_orders نشان می‌دهد
LIVE_ORDER_STATUSES = ("active", "delreq_pending")

ns = {}
_APP = {}  # "app": تلگرام Application، برای تکمیل خرید معلق از داخل rc_approve
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


def _guide_url(order):
    """صفحه‌ی آموزش فقط برای اتصال‌های L2TP/PPTP (پلن IPsec)؛ V2Ray فقط لینک اشتراک و QR می‌گیرد."""
    sub = ns["public_sub_url"](order["sub_url"] or "").rstrip("/")
    if order["protocol"] not in ns["IPSEC_SERVICES"] or not sub.startswith("https://"):
        return None
    return sub + "/guide"


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
    sub = ns["public_sub_url"](order["sub_url"] or "").rstrip("/")
    return {
        "id": order["id"], "username": order["username"], "service": order["protocol"],
        "service_name": SHOP_SERVICES.get(order["protocol"]) or ns["service_name"](order["protocol"]),
        "used": used, "limit": limit, "expire": expire or None, "days_left": left_days,
        "panel_status": pstatus, "on": pstatus != "disabled", "state": state,
        "guide": _guide_url(order),
        # لینک اشتراک برای کپی و بارکد در جزئیات کاربر (QR از /api/qr?kind=sub)
        "sub": sub if sub.startswith("https://") else None,
    }


async def api_me(request):
    uid = request["uid"]
    db = ns["db"]
    orders = db.get_user_orders(uid)
    return web.json_response({
        "id": uid, "balance": db.get_balance(uid), "orders": len(orders),
        "is_admin": bool(ns["is_admin"](uid)),
        "free_pass": bool(ns["has_free_pass"](uid)),
        # پشتیبانی و گرفتن شماره کارت: چت مستقیم تلگرام با همین یوزرنیم (تنظیم support_username)
        "support": (db.setting("support_username", "") or "").lstrip("@"),
        "test_enabled": db.setting("test_enabled", "0") == "1",
        "unread": db.one("SELECT COUNT(*) c FROM notifications WHERE user_id=? AND seen=0", (uid,))["c"],
    })


# ---------- 🔔 زنگوله: خبرهای مهم (تأیید رسید، انقضا، شارژ دستی، پیام پشتیبانی، …) به‌جای پیام چت ----------
async def api_notifs(request):
    uid = request["uid"]
    db = ns["db"]
    rows = db.q("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50", (uid,))
    return web.json_response({"items": [{"id": r["id"], "kind": r["kind"], "text": r["text"], "order_id": r["order_id"],
                                         "at": r["created_at"], "seen": bool(r["seen"])} for r in rows]})


async def api_notifs_seen(request):
    ns["db"].x("UPDATE notifications SET seen=1 WHERE user_id=? AND seen=0", (request["uid"],))
    return web.json_response({"ok": True})


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


async def api_toggle(request):
    """کلید سبز/قرمز: روشن یا خاموش کردن یک سرویس خود همین کاربر روی پنل.
    سرویس تمام‌شده (حجم یا تاریخ) روشن نمی‌شود؛ باید تمدید شود."""
    uid = request["uid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    db = ns["db"]
    order = db.get_order(int(body.get("order_id") or 0))
    # فقط سفارش‌های زنده‌ی خود همین کاربر (همان‌هایی که در لیست مشتری‌ها دیده می‌شوند)؛
    # سفارش حذف‌شده‌ای که هنوز کاربرش روی پنل هست نباید از اینجا خاموش شود
    if not order or order["user_id"] != uid or order["status"] not in LIVE_ORDER_STATUSES:
        return web.json_response({"error": "not_found"}, status=404)
    turn_on = bool(body.get("on"))
    panel = db.get_panel(order["panel_id"])
    if not panel:
        return web.json_response({"error": "panel"}, status=503)
    if turn_on:
        expire = int(order["expire_at"] or 0)
        pu = (await asyncio.to_thread(_panel_users, panel)).get(order["username"]) or {}
        if (expire and expire < time.time()) or pu.get("status") in ("limited", "expired"):
            return web.json_response({"error": "finished"}, status=409)
    client = ns["panel_client"](panel)
    try:
        ok = await asyncio.to_thread(client.set_status, order["username"], "active" if turn_on else "disabled")
    except Exception as e:
        log.warning("miniapp toggle %s failed: %s", order["id"], e)
        return web.json_response({"error": "panel"}, status=502)
    if not ok:
        return web.json_response({"error": "not_on_panel"}, status=404)
    _panel_cache.pop(panel["id"], None)
    ns["notify_group"](request.app["tg_app"].bot,
                       f"{'🟢 روشن' if turn_on else '🔴 خاموش'} شد از مینی‌اپ: {order['username']}\n👤 {ns['who'](uid)}",
                       topic="sales")
    return web.json_response({"ok": True, "on": turn_on})


# ---------- خرید داخل مینی‌اپ (کیف پول) ----------
USERNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{2,19}")
MAX_BULK = 20
_buy_locks = {}


def _err(code, status=400, **extra):
    return web.json_response(dict(error=code, **extra), status=status)


async def _free_username(client, base, taken):
    """base اگر آزاد بود همان، وگرنه base2، base3…؛ taken یوزرنیم‌هایی است که همین خرید گرفته."""
    for i in range(0, 200):
        name = base if i == 0 else f"{base[:17]}{i + 1}"
        if name in taken:
            continue
        if not await asyncio.to_thread(client.find_user, name):
            return name
    return None


async def _create_accounts(app, uid, plan, service, base, password, qty, free=False):
    """ساخت qty اکانت پشت سر هم با یک پنل؛ هر اکانت جدا از کیف پول کسر می‌شود (مگر Free Pass) و اگر
    روی پنل ساخته نشد، همان مبلغ برمی‌گردد. مشترک بین خرید مستقیم و تکمیل خرید معلق بعد از شارژ."""
    db = ns["db"]
    panel = ns["pick_panel"](service)
    if not panel:
        return [], "capacity"
    ipsec = service in ns["IPSEC_SERVICES"]
    # Free Pass: سفارش با قیمت صفر ثبت می‌شود تا در فروش و درآمد حساب نشود
    order_plan = dict(plan, price=0) if free else plan
    client = ns["panel_client"](panel)
    if not base:
        base = "u" + "".join(secrets.choice("abcdefghjkmnpqrstuvwxyz23456789") for _ in range(6))
    ctx = SimpleNamespace(bot=app.bot, application=app, job_queue=app.job_queue, args=[])
    made, taken, failed = [], set(), None
    for _ in range(qty):
        try:
            name = await _free_username(client, base, taken)
        except Exception as e:
            failed = f"panel: {e}"
            break
        if not name:
            failed = "username_taken"
            break
        if not free and not db.try_spend(uid, plan["price"]):
            failed = "balance"
            break
        pw = password if (password and qty == 1) else (ns["random_ipsec_password"]() if ipsec else None)
        try:
            order, opanel = await asyncio.to_thread(
                ns["create_service_on_panel"], uid, order_plan, service, name, panel["id"], pw)
        except Exception as e:
            if not free:
                db.add_balance(uid, plan["price"])  # بازگشت وجه
            failed = str(e)[:200]
            break
        taken.add(name)
        made.append(_made_json(order))
        try:
            await ns["deliver_service"](ctx, uid, order, opanel, quiet=True)
        except Exception as e:
            log.warning("miniapp deliver %s failed: %s", order["id"], e)
    _panel_cache.pop(panel["id"], None)
    return made, failed


def _made_json(order):
    """اکانت تازه برای مینی‌اپ: V2Ray لینک اشتراک (و QR از /api/qr) می‌گیرد؛ آموزش فقط برای L2TP/PPTP."""
    sub = ns["public_sub_url"](order["sub_url"] or "")
    return {"id": order["id"], "username": order["username"], "password": order["password"],
            "service": order["protocol"], "sub": sub if order["protocol"] not in ns["IPSEC_SERVICES"] else None,
            "guide": _guide_url(order)}


def _parse_buy(body, uid):
    """(service, plan, qty, base, password) یا (None, کد خطا)."""
    service = str(body.get("service") or "")
    plan = ns["user_plan"](_int(body.get("plan_id")), uid)
    if service not in SHOP_SERVICES or service not in ns["SERVICES"] or not plan or not plan["active"] \
            or not ns["plan_fits"](plan, service):
        return None, "plan"
    qty = max(1, min(MAX_BULK, _int(body.get("qty"), 1)))
    base = str(body.get("username") or "").strip()
    if base and not USERNAME_RE.fullmatch(base):
        return None, "username"
    password = str(body.get("password") or "").strip().translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
    if service in ns["IPSEC_SERVICES"] and password and not ns["IPSEC_PASSWORD_RE"].fullmatch(password):
        return None, "password"
    return (service, plan, qty, base, password), None


# ---------- خرید معلق: موجودی کم بود؛ بعد از تأیید شارژ توسط ادمین خودکار تکمیل می‌شود ----------
PENDING_KEY = "pending_buy_app:{}"


def _pending(uid):
    db = ns["db"]
    try:
        data = json.loads(db.setting(PENDING_KEY.format(uid)) or "null")
    except ValueError:
        return None
    if not data or time.time() - data.get("saved_at", 0) > ns["PENDING_BUY_TTL"]:
        return None
    return data


def _clear_pending(uid):
    if ns["db"].setting(PENDING_KEY.format(uid)):
        ns["db"].set_setting(PENDING_KEY.format(uid), "")


def _pending_json(uid):
    p = _pending(uid)
    plan = ns["user_plan"](p["plan_id"], uid) if p else None
    if not p or not plan or not plan["active"]:
        return None
    total = plan["price"] * p["qty"]
    return {"service": p["service"], "service_label": SHOP_SERVICES.get(p["service"], p["service"]),
            "plan": {"id": plan["id"], "gb": plan["volume_gb"], "days": plan["days"], "price": plan["price"],
                     "users": plan["user_limit"] or 0},
            "qty": p["qty"], "username": p.get("username") or "", "total": total,
            "need": max(0, total - ns["db"].get_balance(uid))}


async def resume_pending_buy(bot, uid):
    """بعد از تأیید شارژ کیف پول (offer_pending_buy در rc_approve): اگر خرید معلق مینی‌اپ هست و موجودی
    حالا کافی است، همان پلن و یوزرنیم و تعداد ساخته می‌شود. True یعنی خرید معلقی بود (کاملش کرد یا هنوز کم دارد)."""
    p = _pending(uid)
    if not p or _APP.get("app") is None:
        return False
    db = ns["db"]
    plan = ns["user_plan"](p["plan_id"], uid)
    if not plan or not plan["active"] or not ns["plan_fits"](plan, p["service"]):
        _clear_pending(uid)
        await ns["tell"](bot, uid, "⚠️ پلنی که برای خرید معلقت انتخاب کرده بودی دیگه فروخته نمی‌شه؛ از تب خرید یه پلن دیگه انتخاب کن.")
        return True
    total = plan["price"] * p["qty"]
    if db.get_balance(uid) < total:
        await ns["tell"](bot, uid, f"🛒 خرید معلقت هنوز {ns['fmt'](total - db.get_balance(uid))} تومان کم داره؛ بعد از شارژ بعدی خودکار ساخته می‌شه.",
                         kind="wallet")
        return True
    lock = _buy_locks.setdefault(uid, asyncio.Lock())
    async with lock:
        _clear_pending(uid)
        made, failed = await _create_accounts(_APP["app"], uid, plan, p["service"], p.get("username") or "",
                                              p.get("password") or "", p["qty"])
    if made:
        names = "، ".join(m["username"] for m in made)
        await ns["tell"](bot, uid, f"✅ خرید معلقت خودکار تکمیل شد: {names}\n"
                                   f"💎 موجودی فعلی: {ns['fmt'](db.get_balance(uid))} تومان"
                                   + (f"\n⚠️ بقیه ساخته نشد ({failed})؛ پولش به کیف پول برگشت." if failed else ""),
                         kind="wallet", order_id=made[0]["id"])
        ns["notify_group"](bot, f"🛍 خرید معلق بعد از شارژ تکمیل شد\n👤 {ns['who'](uid)} | {len(made)} اکانت", topic="sales")
    else:
        await ns["tell"](bot, uid, f"❌ خرید معلقت ساخته نشد ({failed}); پولت توی کیف پول مونده. از تب خرید دوباره امتحان کن.",
                         kind="refund")
    return True


async def api_buy(request):
    """خرید از کیف پول، مثل finalize_wallet_purchase ربات: کسر اتمیک، ساخت روی پنل، برگشت وجه اگر نشد،
    کارت تحویل در چت. موبایل‌فروش می‌تواند چند اکانت با هم بسازد (qty) که پشت سر هم نام‌گذاری می‌شوند.
    موجودی کم: خرید معلق ذخیره می‌شود (402) و بعد از تأیید شارژ خودکار تکمیل می‌شود.
    Free Pass: بدون بررسی و کسر موجودی."""
    uid = request["uid"]
    parsed, err = _parse_buy(await _body(request), uid)
    if err:
        return _err(err)
    service, plan, qty, base, password = parsed
    db = ns["db"]
    free = ns["has_free_pass"](uid)
    total = plan["price"] * qty
    if not free and db.get_balance(uid) < total:
        db.set_setting(PENDING_KEY.format(uid), json.dumps({
            "service": service, "plan_id": plan["id"], "qty": qty, "username": base, "password": password,
            "saved_at": time.time()}))
        return _err("balance", 402, need=total - db.get_balance(uid), pending=True)
    if not ns["pick_panel"](service):
        return _err("capacity", 503)
    lock = _buy_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return _err("busy", 429)
    async with lock:
        made, failed = await _create_accounts(request.app["tg_app"], uid, plan, service, base, password, qty, free=free)
    if made:
        _clear_pending(uid)
    return web.json_response({"ok": bool(made), "made": made, "failed": failed,
                              "balance": db.get_balance(uid)}, status=200 if made else 502)


async def api_pending(request):
    uid = request["uid"]
    db = ns["db"]
    rows = db.q("SELECT d.*, t.reply FROM direct_orders d LEFT JOIN tickets t ON t.id = d.ticket_id "
                "WHERE d.user_id=? AND d.status IN ('open','receipt') ORDER BY d.id DESC", (uid,))
    return web.json_response({"pending": _pending_json(uid), "direct": [_direct_json(r) for r in rows]})


async def api_pending_cancel(request):
    _clear_pending(request["uid"])
    return web.json_response({"ok": True})


# ---------- پرداخت مستقیم (کارت به کارت) از طریق تیکت ----------
def _direct_json(r):
    return {"id": r["id"], "ticket": r["ticket_id"], "status": r["status"], "service": r["service"],
            "service_label": SHOP_SERVICES.get(r["service"], r["service"]), "username": r["username"],
            "password": r["password"] or "", "amount": r["amount"], "plan_id": r["plan_id"],
            "card": r["reply"] or "", "at": r["created_at"]}


async def api_direct(request):
    """شماره کارت ثابتی در برنامه نیست: یک تیکت خرید ساخته می‌شود تا ادمین شماره کارت را جواب بدهد؛
    کاربر بعد رسید را برای همین سفارش می‌فرستد (api_direct_receipt) و تأیید ادمین اکانت را می‌سازد."""
    uid = request["uid"]
    parsed, err = _parse_buy(await _body(request), uid)
    if err:
        return _err(err)
    service, plan, _qty, base, password = parsed
    db = ns["db"]
    if db.one("SELECT COUNT(*) c FROM direct_orders WHERE user_id=? AND status IN ('open','receipt')", (uid,))["c"] >= MAX_PENDING_RECEIPTS:
        return _err("too_many", 429)
    panel = ns["pick_panel"](service)
    if not panel:
        return _err("capacity", 503)
    # یوزرنیم همین حالا روی پنل چک می‌شود تا بعد از پرداخت به اسم تکراری نخورد
    try:
        reserved = {r["username"] for r in db.q("SELECT username FROM direct_orders WHERE status IN ('open','receipt')")}
        name = await _free_username(ns["panel_client"](panel), base or "u" + secrets.token_hex(3), reserved)
    except Exception as e:
        log.warning("miniapp direct username check failed: %s", e)
        return _err("capacity", 503)
    if not name:
        return _err("username_taken", 409)
    if service in ns["IPSEC_SERVICES"] and not password:
        password = ns["random_ipsec_password"]()
    fmt = ns["fmt"]
    plan_text = ns["plan_label"](plan)
    text = (f"🛒 درخواست خرید با پرداخت مستقیم (کارت به کارت)\n"
            f"📦 {plan_text}\n🧩 سرویس: {SHOP_SERVICES.get(service, service)}\n👤 یوزرنیم: {name}\n"
            f"💰 مبلغ: {fmt(plan['price'])} تومان\n\n"
            f"✍️ لطفاً شماره کارت و نام صاحب حساب را در پاسخ همین تیکت بفرستید.")
    tid = db.create_ticket(uid, text)
    did = db.x("INSERT INTO direct_orders (user_id,ticket_id,plan_id,service,username,password,amount,status,created_at) "
               "VALUES (?,?,?,?,?,?,?,'open',?)", (uid, tid, plan["id"], service, name, password, plan["price"], int(time.time())))
    bot = request.app["tg_app"].bot
    ns["notify_group"](bot, f"🎫 تیکت خرید مستقیم #{tid}\n👤 {ns['who'](uid)} | 💸 {fmt(plan['price'])} تومان", topic="tickets")
    btn = ns["btn"]
    await ns["notify_admin"](bot, f"🎫 تیکت #{tid} — {text}",
                             reply_markup=ns["InlineKeyboardMarkup"]([[btn("✍️ پاسخ (شماره کارت)", f"tk:reply:{tid}"),
                                                                       btn("🔒 بستن", f"tk:close:{tid}")]]))
    return web.json_response({"ok": True, "direct": _direct_json(
        db.one("SELECT d.*, NULL reply FROM direct_orders d WHERE d.id=?", (did,)))})


def _own_direct(uid, did):
    r = ns["db"].one("SELECT d.*, t.reply FROM direct_orders d LEFT JOIN tickets t ON t.id = d.ticket_id "
                     "WHERE d.id=? AND d.user_id=?", (did, uid))
    return r


async def api_direct_receipt(request):
    """رسید یک سفارش مستقیم: مثل api_charge آپلود می‌شود، ولی رسیدِ «خرید» با مشخصات همان سفارش ثبت می‌شود
    تا تأیید ادمین (rc_approve) مستقیم اکانت را بسازد. بدون تأیید ادمین هیچ اکانتی ساخته نمی‌شود."""
    uid = request["uid"]
    db = ns["db"]
    try:
        form = await request.post()
        did = _int(form.get("id"))
        photo = form.get("photo")
    except Exception:
        return _err("form")
    r = _own_direct(uid, did)
    if not r or r["status"] != "open":
        return _err("not_found", 404)
    if photo is None or not hasattr(photo, "file"):
        return _err("photo")
    data = photo.file.read(MAX_RECEIPT_BYTES + 1)
    if not data or len(data) > MAX_RECEIPT_BYTES:
        return _err("photo_size")
    photo_id = await _upload_receipt_photo(request.app["tg_app"].bot, uid, data,
                                           f"🧾 رسید پرداخت مستقیم — {ns['fmt'](r['amount'])} تومان — {r['username']}")
    if not photo_id:
        return _err("telegram", 502)
    meta = {"plan_id": r["plan_id"], "protocol": r["service"], "username": r["username"], "panel_id": None,
            "ipsec_password": r["password"] or None, "direct_order_id": r["id"]}
    rid = db.create_receipt(uid, r["amount"], "purchase", photo_id, meta)
    db.x("UPDATE direct_orders SET status='receipt', receipt_id=? WHERE id=?", (rid, r["id"]))
    rec = db.get_receipt(rid)
    await ns["send_receipt_to_admins"](request.app["tg_app"].bot, rid, photo_id,
                                       ns["receipt_caption"](rec, f"پرداخت مستقیم خرید (تیکت #{r['ticket_id']}) — {r['username']}"))
    return web.json_response({"ok": True, "receipt": rid})


async def api_direct_cancel(request):
    uid = request["uid"]
    r = _own_direct(uid, _int((await _body(request)).get("id")))
    if not r or r["status"] != "open":
        return _err("not_found", 404)
    ns["db"].x("UPDATE direct_orders SET status='cancelled' WHERE id=?", (r["id"],))
    if r["ticket_id"]:
        t = ns["db"].get_ticket(r["ticket_id"])
        if t and t["status"] == "open":
            ns["db"].set_ticket(t["id"], "closed")
    return web.json_response({"ok": True})


# ---------- تمدید داخل مینی‌اپ (کیف پول) ----------
def _live_order(db, uid, order_id):
    order = db.get_order(int(order_id or 0))
    if not order or order["user_id"] != uid or order["status"] != "active":
        return None
    return order


async def api_renew_plans(request):
    uid = request["uid"]
    db = ns["db"]
    order = _live_order(db, uid, request.query.get("order_id"))
    if not order:
        return _err("not_found", 404)
    plans = [ns["user_plan"](p["id"], uid) for p in db.get_plans(active_only=True, service=order["protocol"])]
    plans = [p for p in plans if p and ns["plan_fits"](p, order["protocol"])]
    return web.json_response({"order": {"id": order["id"], "username": order["username"]}, "plans": [
        {"id": p["id"], "gb": p["volume_gb"], "days": p["days"], "price": p["price"], "users": p["user_limit"] or 0}
        for p in plans]})


async def api_renew(request):
    """مثل دکمه‌ی rnw:w ربات: پلن واقعی و فعال همان سرویس، کسر اتمیک، تمدید، برگشت وجه اگر نشد."""
    uid = request["uid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    db = ns["db"]
    order = _live_order(db, uid, body.get("order_id"))
    if not order:
        return _err("not_found", 404)
    plan = ns["user_plan"](int(body.get("plan_id") or 0), uid)
    if not plan or not plan["active"] or not ns["plan_fits"](plan, order["protocol"]):
        return _err("plan")
    lock = _buy_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return _err("busy", 429)
    async with lock:
        bal_before = db.get_balance(uid)
        free = ns["has_free_pass"](uid)
        if not free and not db.try_spend(uid, plan["price"]):
            return _err("balance", 402, need=plan["price"] - bal_before)
        app = request.app["tg_app"]
        ctx = SimpleNamespace(bot=app.bot, application=app, job_queue=app.job_queue, args=[])
        try:
            await ns["do_renew_and_deliver"](None, ctx, uid, order["id"], plan["id"], quiet=True)
        except Exception as e:
            if not free:
                db.add_balance(uid, plan["price"])
            log.warning("miniapp renew %s failed: %s", order["id"], e)
            return _err("renew", 502, detail=str(e)[:200])
        _panel_cache.pop(order["panel_id"], None)
    new = db.get_order(order["id"])
    return web.json_response({"ok": True, "expire": new["expire_at"], "balance": db.get_balance(uid)})


# ---------- اطلاعات اتصال و نصب پروفایل داخل مینی‌اپ (کار حضوری موبایل‌فروش) ----------
def _own_order(db, uid, order_id):
    order = db.get_order(_int(order_id))
    if not order or order["user_id"] != uid or order["status"] not in LIVE_ORDER_STATUSES:
        return None
    return order


async def _order_connect(order):
    """اطلاعات اتصال همان‌طور که پنل الان می‌دهد (رمز از پنل، نه از سفارش، تا همانی باشد که نود چک می‌کند)."""
    info = {"id": order["id"], "username": order["username"], "service": order["protocol"],
            "password": order["password"] or "", "sub": ns["public_sub_url"](order["sub_url"] or ""),
            "guide": _guide_url(order),
            "ikev2": None, "l2tp": None, "pptp": None}
    if order["protocol"] not in ns["IPSEC_SERVICES"]:
        return info
    panel = ns["db"].get_panel(order["panel_id"])
    links = None
    if panel:
        try:
            links = await asyncio.to_thread(ns["panel_client"](panel).links, order["username"])
        except Exception as e:
            log.warning("miniapp connect links %s: %s", order["username"], e)
    pptp = ((links or {}).get("pptp_configs") or [None])[0]
    if pptp:
        info["pptp"] = {"server": pptp.get("server") or ""}
    for kind in ("ikev2", "l2tp"):
        cfgs = (links or {}).get(f"{kind}_configs") or []
        if cfgs:
            c = cfgs[0]
            info["password"] = c.get("password") or info["password"]
            info[kind] = {"server": c.get("server") or "", "remote_id": c.get("remote_id") or "",
                          "secret": c.get("psk") or "" if kind == "l2tp" else "",
                          "install": ns["public_sub_url"](c.get("install_url") or c.get("mobileconfig_url") or "")}
    return info


async def api_connect(request):
    order = _own_order(ns["db"], request["uid"], request.query.get("order_id"))
    if not order:
        return _err("not_found", 404)
    return web.json_response(await _order_connect(order))


async def api_qr(request):
    """QR لینک نصب پروفایل آیفون (kind=ikev2|l2tp) یا لینک اشتراک (kind=sub)، تا مشتری حضوری با دوربین
    گوشی خودش اسکن کند و پروفایل روی گوشی خودش نصب شود."""
    order = _own_order(ns["db"], request["uid"], request.query.get("order_id"))
    if not order:
        return _err("not_found", 404)
    info = await _order_connect(order)
    kind = request.query.get("kind")
    data = info["sub"] if kind == "sub" else (info.get(kind) or {}).get("install") if kind in ("ikev2", "l2tp") else None
    if not data:
        return _err("no_link", 404)
    png = await asyncio.to_thread(ns["qr_png"], data)
    if png is None:
        return _err("qr", 500)
    png = png.getvalue()
    return web.Response(body=png, content_type="image/png", headers={"Cache-Control": "private, max-age=3600"})


# ---------- کیف پول و شارژ کارت به کارت داخل مینی‌اپ ----------
CHARGE_MIN, CHARGE_MAX = 20000, 50000000
MAX_RECEIPT_BYTES = 8 * 1024 * 1024
MAX_PENDING_RECEIPTS = 3


async def api_wallet(request):
    uid = request["uid"]
    db = ns["db"]
    rows = db.q("SELECT id, amount, rtype, status, created_at FROM receipts WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    return web.json_response({
        "balance": db.get_balance(uid),
        "card_number": db.setting("card_number", ""), "card_name": db.setting("card_name", ""),
        "min": CHARGE_MIN, "max": CHARGE_MAX,
        "receipts": [{"id": r["id"], "amount": r["amount"], "type": r["rtype"], "status": r["status"],
                      "at": r["created_at"]} for r in rows],
    })


async def _upload_receipt_photo(bot, uid, data, title):
    """عکس یک بار در تاپیک «💳 رسید و پرداخت» گروه گزارش آپلود می‌شود تا file_id تلگرام را داشته باشیم؛
    در چت خود مشتری چیزی نمی‌آید. اگر گروه تنظیم نبود یا نشد، مثل قبل در چت خود مشتری. None اگر نشد."""
    db = ns["db"]
    sent = None
    target = ns["_chat_target"](db.setting("group_id"))
    if target is not None:
        try:
            sent = await bot.send_photo(target, data, message_thread_id=ns["group_thread"]("pay"),
                                        caption=f"{title}\n👤 {ns['who'](uid)}")
        except Exception as e:
            log.warning("miniapp receipt upload to group failed: %s", e)
    if sent is None:
        try:
            sent = await bot.send_photo(uid, data, caption=f"{title}\n✅ ثبت شد و برای ادمین فرستاده شد؛ بعد از تأیید انجام می‌شه.")
        except Exception as e:
            log.warning("miniapp receipt photo for %s failed: %s", uid, e)
            return None
    return sent.photo[-1].file_id


async def api_charge(request):
    """عکس رسید از مینی‌اپ: اول در گروه گزارش آپلود می‌شود (تا file_id تلگرام داشته باشیم)،
    بعد همان مسیر رسید ربات: create_receipt و send_receipt_to_admins."""
    uid = request["uid"]
    db = ns["db"]
    try:
        form = await request.post()
        amount = int(str(form.get("amount") or "0").replace(",", ""))
        photo = form.get("photo")
    except Exception:
        return _err("form")
    if not (CHARGE_MIN <= amount <= CHARGE_MAX):
        return _err("amount", min=CHARGE_MIN, max=CHARGE_MAX)
    if photo is None or not hasattr(photo, "file"):
        return _err("photo")
    # جلوی رگبار رسید الکی: هر کاربر حداکثر چند رسید منتظر تأیید
    if db.one("SELECT COUNT(*) c FROM receipts WHERE user_id=? AND status='pending'", (uid,))["c"] >= MAX_PENDING_RECEIPTS:
        return _err("too_many", 429)
    data = photo.file.read(MAX_RECEIPT_BYTES + 1)
    if not data or len(data) > MAX_RECEIPT_BYTES:
        return _err("photo_size")
    photo_id = await _upload_receipt_photo(request.app["tg_app"].bot, uid, data,
                                           f"🧾 عکس رسید شارژ از مینی‌اپ — {ns['fmt'](amount)} تومان")
    if not photo_id:
        return _err("telegram", 502)
    bot = request.app["tg_app"].bot
    rid = db.create_receipt(uid, amount, "wallet_charge", photo_id)
    db.set_state(uid, "none")
    r = db.get_receipt(rid)
    await ns["send_receipt_to_admins"](bot, rid, photo_id,
                                       ns["receipt_caption"](r, "یک پرداخت جدید انجام شده است — افزایش موجودی (مینی‌اپ)"))
    return web.json_response({"ok": True, "receipt": rid})


# ---------- تب مدیریت (فقط ادمین) ----------
class _AdminMsg:
    """جای query.message در rc_approve/rc_reject. chat_id صفر است تا پیام رسید پیش همه‌ی ادمین‌ها
    بسته شود (close_receipt_for_others)، و جواب‌ها به‌جای چت به مینی‌اپ برمی‌گردند."""
    chat_id = 0
    photo = None
    caption = None

    def __init__(self, notes):
        self.notes = notes

    async def reply_text(self, text, **kw):
        self.notes.append(text)

    async def edit_reply_markup(self, **kw):
        return True

    async def delete(self):
        return True


class _AdminQuery:
    def __init__(self):
        self.notes = []
        self.message = _AdminMsg(self.notes)

    async def answer(self, text=None, **kw):
        if text:
            self.notes.append(text)

    async def edit_message_text(self, text, **kw):
        self.notes.append(text)


def _admin_only(request):
    return ns["is_admin"](request["uid"])


async def api_admin_summary(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    now = time.time()
    span = {k: db.stats_since(int(now - d * 86400)) for k, d in (("day", 1), ("week", 7), ("month", 30))}
    pending = []
    for r in db.pending_receipts():
        u = db.get_user(r["user_id"])
        meta = json.loads(r["meta"] or "{}")
        pending.append({"id": r["id"], "user_id": r["user_id"], "amount": r["amount"], "type": r["rtype"],
                        "at": r["created_at"], "user": (u["full_name"] or "") if u else "",
                        "uname": (u["username"] or "") if u else "", "username": meta.get("username") or ""})
    return web.json_response({"span": span, "totals": db.totals(), "pending": pending})


async def api_admin_receipt_photo(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    r = ns["db"].get_receipt(int(request.query.get("id") or 0))
    if not r or not r["photo_id"]:
        return _err("not_found", 404)
    try:
        f = await request.app["tg_app"].bot.get_file(r["photo_id"])
        data = bytes(await f.download_as_bytearray())
    except Exception as e:
        log.warning("miniapp receipt photo %s failed: %s", r["id"], e)
        return _err("telegram", 502)
    return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


async def api_admin_receipt(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    try:
        body = await request.json()
    except Exception:
        body = {}
    rid, action = int(body.get("id") or 0), body.get("action")
    if action not in ("ok", "no"):
        return _err("action")
    app = request.app["tg_app"]
    ctx = SimpleNamespace(bot=app.bot, application=app, job_queue=app.job_queue, args=[])
    q = _AdminQuery()
    fn = ns["rc_approve"] if action == "ok" else ns["rc_reject"]
    try:
        await fn(q, ctx, rid)
    except Exception as e:
        log.warning("miniapp receipt %s %s failed: %s", rid, action, e)
        return _err("failed", 502, detail=str(e)[:200])
    r = ns["db"].get_receipt(rid)
    ns["notify_group"](app.bot, f"👑 رسید R{rid} از مینی‌اپ {'تأیید' if action == 'ok' else 'رد'} شد — ادمین: {ns['who'](request['uid'])}",
                       topic="pay")
    return web.json_response({"ok": True, "status": r["status"] if r else None, "notes": q.notes})


# ---------- تب مدیریت: کاربرها، تعرفه‌ها، تیکت‌ها، پیام همگانی ----------
# همان قانون‌های پنل مدیریت ربات (au_amount، au_disc، ticket_reply، plan_edit_value، run_broadcast)؛
# هر کار ادمین در تاپیک «📊 گزارش» گروه ثبت می‌شود.
def _admin_log(request, text):
    ns["notify_group"](request.app["tg_app"].bot, f"👑 مینی‌اپ — {text}\nادمین: {ns['who'](request['uid'])}", topic="report")


async def _body(request):
    try:
        b = await request.json()
        return b if isinstance(b, dict) else {}
    except Exception:
        return {}


def _int(v, default=0):
    try:
        return int(str(v).strip().translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _user_row(u, svc=0):
    return {"id": u["id"], "name": (u["full_name"] or "").strip(), "uname": u["username"] or "",
            "balance": int(u["balance"] or 0), "blocked": bool(u["is_blocked"]),
            "discount": int(u["discount_pct"] or 0), "services": svc,
            "joined": u["created_at"] or None, "seen": u["last_seen"] or None,
            "refs": ns["db"].referral_count(u["id"])}


ADMIN_USER_FILTERS = {"all": "", "balance": " AND u.balance > 0", "neg": " AND u.balance < 0",
                      "blocked": " AND COALESCE(u.is_blocked,0)=1",
                      "ref": " AND u.id IN (SELECT referred_by FROM users WHERE referred_by IS NOT NULL)"}


async def api_admin_users(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    q = (request.query.get("q") or "").strip().lstrip("@")
    filt = ADMIN_USER_FILTERS.get(request.query.get("f") or "all", "")
    offset = max(0, _int(request.query.get("offset")))
    where, args = "1=1" + filt, []
    if q:
        where += " AND (CAST(u.id AS TEXT) LIKE ? OR u.username LIKE ? OR u.full_name LIKE ?)"
        args += [f"{q}%", f"%{q}%", f"%{q}%"]
    total = db.one(f"SELECT COUNT(*) c FROM users u WHERE {where}", tuple(args))["c"]
    rows = db.q(f"""SELECT u.*, (SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id AND o.status IN ('active','delreq_pending')) svc
                    FROM users u WHERE {where} ORDER BY COALESCE(NULLIF(u.last_seen,0), u.created_at) DESC LIMIT 25 OFFSET ?""",
                tuple(args) + (offset,))
    return web.json_response({"total": total, "offset": offset, "users": [_user_row(r, r["svc"]) for r in rows]})


async def api_admin_user(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    u = db.get_user(_int(request.query.get("id")))
    if not u:
        return _err("not_found", 404)
    orders = db.get_user_orders(u["id"])
    paid = db.one("SELECT COALESCE(SUM(amount),0) s FROM receipts WHERE user_id=? AND status='approved'", (u["id"],))["s"]
    bought = db.one("SELECT COUNT(*) c, COALESCE(SUM(price),0) s FROM orders WHERE user_id=?", (u["id"],))
    row = _user_row(u, len(orders))
    row.update({"paid": paid, "orders_count": bought["c"], "orders_sum": bought["s"],
                "is_admin": bool(ns["is_admin"](u["id"])),
                "referrer": ns["who"](u["referred_by"]) if u["referred_by"] else None,
                "ref_users": [{"id": r["id"], "name": (r["full_name"] or "").strip(), "uname": r["username"] or ""}
                              for r in db.q("SELECT * FROM users WHERE referred_by=? ORDER BY id DESC LIMIT 30", (u["id"],))],
                "orders": [{"id": o["id"], "username": o["username"], "service": ns["service_name"](o["protocol"]),
                            "expire": o["expire_at"] or None, "gb": o["volume_gb"], "status": o["status"]} for o in orders]})
    return web.json_response(row)


async def api_admin_user_action(request):
    """{id, action: credit|debit|block|unblock|discount|message, amount?, pct?, text?}"""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db, fmt = ns["db"], ns["fmt"]
    bot = request.app["tg_app"].bot
    b = await _body(request)
    action = b.get("action")
    u = db.get_user(_int(b.get("id")))
    if not u:
        return _err("not_found", 404)
    target = u["id"]
    label = ns["who"](target)
    if action in ("credit", "debit"):
        amount = _int(b.get("amount"))
        if not 0 < amount <= 50_000_000:
            return _err("amount")
        if action == "debit":
            if not db.try_spend(target, amount):
                return _err("low_balance", balance=db.get_balance(target))
            _admin_log(request, f"➖ {fmt(amount)} تومان از کیف پول {label} کم شد")
        else:
            db.add_balance(target, amount)
            _admin_log(request, f"➕ {fmt(amount)} تومان به کیف پول {label} اضافه شد")
            try:
                await ns["tell"](bot, target, f"💰 کیف پول شما {fmt(amount)} تومان شارژ شد (شارژ دستی).", kind="wallet")
            except Exception:
                pass
            try:
                await ns["offer_pending_buy"](bot, target)
            except Exception as e:
                log.info("offer_pending_buy %s: %s", target, e)
    elif action in ("block", "unblock"):
        if action == "block" and ns["is_admin"](target):
            return _err("admin")
        db.x("UPDATE users SET is_blocked=? WHERE id=?", (1 if action == "block" else 0, target))
        _admin_log(request, f"{'⛔ مسدود شد' if action == 'block' else '✅ رفع مسدودی'}: {label}")
    elif action == "discount":
        pct = _int(b.get("pct"), -1)
        if not 0 <= pct <= 100:
            return _err("pct")
        db.x("UPDATE users SET discount_pct=? WHERE id=?", (pct, target))
        _admin_log(request, f"🏷 تخفیف {label} شد {pct}٪")
    elif action == "message":
        text = (b.get("text") or "").strip()
        if not text or len(text) > 3500:
            return _err("text")
        try:
            await ns["tell"](bot, target, f"📩 پیام از پشتیبانی:\n\n{text}", kind="support")
        except Exception as e:
            return _err("send", 502, detail=str(e)[:200])
        _admin_log(request, f"📩 پیام به {label}")
    else:
        return _err("action")
    return web.json_response({"ok": True, "user": _user_row(db.get_user(target), len(db.get_user_orders(target)))})


def _plan_json(p):
    return {"id": p["id"], "service": p["service"] or "", "service_name": ns["SERVICES"].get(p["service"] or "", "بدون سرویس"),
            "title": p["title"] or "", "gb": p["volume_gb"], "days": p["days"], "price": p["price"],
            "users": p["user_limit"] or 0, "active": bool(p["active"])}


async def api_admin_plans(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    plans = sorted(ns["db"].get_plans(), key=lambda p: (p["service"] or "", p["volume_gb"] == 0, p["volume_gb"], p["user_limit"] or 0, p["price"]))
    return web.json_response({"plans": [_plan_json(p) for p in plans],
                              "services": [{"key": k, "name": v} for k, v in ns["SERVICES"].items()]})


async def api_admin_plan(request):
    """{id, price?, days?, title?, active?} — مرحله‌ی تأیید (قبل/بعد) در خود مینی‌اپ است."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db, fmt = ns["db"], ns["fmt"]
    b = await _body(request)
    p = db.get_plan(_int(b.get("id")))
    if not p:
        return _err("not_found", 404)
    fields = {}
    if "price" in b:
        v = _int(b["price"], -1)
        if not 0 < v <= 100_000_000:
            return _err("price")
        fields["price"] = v
    if "days" in b:
        v = _int(b["days"], -1)
        if not 0 < v <= 3650:
            return _err("days")
        fields["days"] = v
    if "title" in b:
        v = (b.get("title") or "").strip()
        if not v or len(v) > 80:
            return _err("title")
        fields["title"] = v
    if "active" in b:
        fields["active"] = 1 if b["active"] else 0
    fields = {k: v for k, v in fields.items() if p[k] != v}
    if not fields:
        return web.json_response({"ok": True, "plan": _plan_json(p)})
    db.update_plan(p["id"], **fields)
    names = {"price": "قیمت", "days": "مدت", "title": "عنوان", "active": "وضعیت"}

    def show(k, v):
        return fmt(v) if k == "price" else ("فعال" if v else "خاموش") if k == "active" else v
    change = "، ".join(f"{names[k]}: {show(k, p[k])} ← {show(k, v)}" for k, v in fields.items())
    _admin_log(request, f"🏷 تعرفه #{p['id']} ({p['title'] or ''}) عوض شد — {change}")
    return web.json_response({"ok": True, "plan": _plan_json(db.get_plan(p["id"]))})


async def api_admin_tickets(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    status = "closed" if request.query.get("s") == "closed" else "open"
    rows = db.q("SELECT * FROM tickets WHERE status=? ORDER BY id DESC LIMIT 30", (status,))
    out = []
    for t in rows:
        u = db.get_user(t["user_id"])
        out.append({"id": t["id"], "user_id": t["user_id"], "user": (u["full_name"] or "") if u else "",
                    "uname": (u["username"] or "") if u else "", "text": t["message"] or "", "photo": bool(t["photo_id"]),
                    "reply": t["reply"] or "", "at": t["created_at"]})
    return web.json_response({"tickets": out})


async def api_admin_ticket_photo(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    t = ns["db"].get_ticket(_int(request.query.get("id")))
    if not t or not t["photo_id"]:
        return _err("not_found", 404)
    try:
        f = await request.app["tg_app"].bot.get_file(t["photo_id"])
        data = bytes(await f.download_as_bytearray())
    except Exception as e:
        log.warning("miniapp ticket photo %s failed: %s", t["id"], e)
        return _err("telegram", 502)
    return web.Response(body=data, content_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


async def api_admin_ticket(request):
    """{id, action: reply|close, text?} — مثل ticket_reply ربات: پاسخ به کاربر می‌رود و تیکت بسته می‌شود."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    b = await _body(request)
    t = db.get_ticket(_int(b.get("id")))
    if not t:
        return _err("not_found", 404)
    if t["status"] != "open":
        return _err("closed", 409)
    if b.get("action") == "reply":
        text = (b.get("text") or "").strip()
        if not text or len(text) > 3500:
            return _err("text")
        db.set_ticket(t["id"], "closed", reply=text)
        sent = True
        try:
            await ns["tell"](request.app["tg_app"].bot, t["user_id"], f"☎️ پاسخ پشتیبانی به تیکت #{t['id']}:\n\n{text}", kind="support")
        except Exception:
            sent = False
        _admin_log(request, f"🎫 تیکت #{t['id']} پاسخ داده و بسته شد ({ns['who'](t['user_id'])})")
        return web.json_response({"ok": True, "sent": sent})
    if b.get("action") == "close":
        db.set_ticket(t["id"], "closed")
        _admin_log(request, f"🔒 تیکت #{t['id']} بدون پاسخ بسته شد")
        return web.json_response({"ok": True})
    return _err("action")


_broadcast_running = set()


async def api_admin_broadcast(request):
    """GET: تعداد گیرنده‌ها. POST {text, count}: count باید همان عددی باشد که ادمین در مرحله‌ی تأیید دید."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    count = len(ns["db"].all_user_ids())
    if request.method == "GET":
        return web.json_response({"count": count, "running": bool(_broadcast_running)})
    b = await _body(request)
    text = (b.get("text") or "").strip()
    if not text or len(text) > 3500:
        return _err("text")
    if _int(b.get("count"), -1) != count:
        return _err("count_changed", 409, count=count)
    if _broadcast_running:
        return _err("running", 409)
    uid = request["uid"]
    bot = request.app["tg_app"].bot
    _broadcast_running.add(uid)

    async def run():
        try:
            await ns["run_broadcast"](bot, uid, {"text": text})
        except Exception as e:
            log.warning("miniapp broadcast failed: %s", e)
        finally:
            _broadcast_running.discard(uid)
    asyncio.create_task(run())
    _admin_log(request, f"📣 پیام همگانی برای {count} کاربر شروع شد:\n\n{text[:300]}")
    return web.json_response({"ok": True, "count": count})


# ---------- «⚙️ همه‌ی بخش‌ها»: پنل‌ها، افزودن/حذف پلن، تنظیمات، ادمین‌ها، بکاپ ----------
# همان قانون‌های منوی /admin ربات (admin_panels، refresh_panel، ap_*، pbm/apm، set_value، adm، send_backup).
def _panel_json(p):
    svc_rows = ns["db"].get_service_rows(p["id"])
    services = []
    for key, name in ns["SERVICES"].items():
        on_panel = ns["service_protocols_on"](p, key)
        r = svc_rows.get(key)
        if not on_panel:
            st = "none"
        elif r and r["enabled"]:
            st = r["remark"] or "-"
        elif r:
            st = "off"
        else:
            st = "سرورهای عمومی"
        services.append({"key": key, "name": name, "state": st})
    return {"id": p["id"], "name": p["name"], "url": p["url"], "username": p["username"], "location": p["location"] or "",
            "status": p["status"], "max_users": p["max_users"], "count": ns["db"].count_panel_active_orders(p["id"]),
            "protocols": ns["panel_protocols"](p), "services": services, "checked_at": p["checked_at"] or None,
            "tls_insecure": bool(p["tls_insecure"])}


async def api_admin_panels(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    return web.json_response({"panels": [_panel_json(p) for p in ns["db"].get_panels()]})


PANEL_FIELDS = ("name", "url", "username", "password", "location", "max_users")


async def api_admin_panel(request):
    """{id, action: test|toggle|edit|delete|groups|map, ...}"""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    b = await _body(request)
    p = db.get_panel(_int(b.get("id")))
    if not p:
        return _err("not_found", 404)
    action = b.get("action")
    if action == "test":
        t0 = time.time()
        try:
            before, after = await asyncio.to_thread(ns["refresh_panel"], p)
        except Exception as e:
            if p["status"] == "active":
                db.update_panel(p["id"], status="offline")
            return web.json_response({"ok": False, "error": str(e)[:300], "panel": _panel_json(db.get_panel(p["id"]))})
        if p["status"] == "offline":
            db.update_panel(p["id"], status="active")
        return web.json_response({"ok": True, "ms": int((time.time() - t0) * 1000),
                                  "diff": ns["protocols_diff_text"](before, after), "panel": _panel_json(db.get_panel(p["id"]))})
    if action == "toggle":
        new = "inactive" if p["status"] == "active" else "active"
        db.update_panel(p["id"], status=new)
        _admin_log(request, f"🖥 پنل «{p['name']}» {'از فروش خارج شد' if new == 'inactive' else 'دوباره فعال شد'}")
    elif action == "edit":
        fields = {}
        for k in PANEL_FIELDS:
            if k not in b or b[k] in (None, ""):
                continue
            v = str(b[k]).strip()
            if k == "max_users":
                v = _int(v, 0)
                if v <= 0:
                    return _err("max_users")
            elif k == "url":
                if not v.startswith("http"):
                    return _err("url")
                v = v.rstrip("/")
            fields[k] = v
        if fields:
            db.update_panel(p["id"], **fields)
            _admin_log(request, f"🖥 پنل «{p['name']}» ویرایش شد: {'، '.join(k for k in fields if k != 'password') or 'پسورد'}"
                                + ("، پسورد" if "password" in fields and len(fields) > 1 else ""))
    elif action == "delete":
        # پنلی که هنوز سرویس فعال دارد حذف نمی‌شود (سرویس‌ها از دید ربات و مینی‌اپ گم می‌شوند)؛ اول «خارج از فروش»
        active = db.count_panel_active_orders(p["id"])
        if active:
            return _err("has_orders", 409, count=active)
        db.delete_panel(p["id"])
        _admin_log(request, f"🗑 پنل «{p['name']}» حذف شد")
        return web.json_response({"ok": True, "deleted": True})
    elif action == "groups":
        # برای انتخاب دوباره‌ی گروه سرویس‌ها: پروتکل‌ها و گروه‌ها تازه از خود پنل
        try:
            await asyncio.to_thread(ns["refresh_panel"], p)
            groups = await asyncio.to_thread(ns["panel_client"](p).list_groups)
        except Exception as e:
            return _err("panel", 502, detail=str(e)[:300])
        p = db.get_panel(p["id"])
        return web.json_response({"ok": True, "groups": groups,
                                  "services": [{"key": k, "name": ns["SERVICES"][k]} for k in ns["mappable_services"](ns["panel_protocols"](p))],
                                  "panel": _panel_json(p)})
    elif action == "map":
        mapping = _clean_map(b.get("map"))
        if mapping is None:
            return _err("map")
        db.set_service_map(p["id"], mapping)
        _admin_log(request, f"🧩 گروه سرویس‌های پنل «{p['name']}» عوض شد")
    else:
        return _err("action")
    return web.json_response({"ok": True, "panel": _panel_json(db.get_panel(p["id"]))})


def _clean_map(raw):
    """{سرویس: {"id", "name"} یا null} از مینی‌اپ ← همان شکل set_service_map؛ None اگر خراب بود."""
    if not isinstance(raw, dict):
        return None
    out = {}
    for k, g in raw.items():
        if k not in ns["SERVICES"]:
            return None
        if g is None:
            out[k] = None
        elif isinstance(g, dict) and "id" in g:
            out[k] = {"id": _int(g.get("id")), "name": str(g.get("name") or "")[:80]}
        else:
            return None
    return out


async def api_admin_panel_add(request):
    """دو مرحله مثل جادوی ap_* ربات. step=test: اتصال و خواندن پروتکل‌ها و گروه‌ها.
    step=save: ثبت پنل با گروه سرویس‌ها، موقعیت و سقف کاربر."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    b = await _body(request)
    d = {k: str(b.get(k) or "").strip() for k in ("name", "url", "username", "password", "location")}
    if not d["name"] or not d["url"].startswith("http") or not d["username"] or not d["password"]:
        return _err("fields")
    d["url"] = d["url"].rstrip("/")
    try:
        client = ns["TifusiPanelAPI"](d["url"], d["username"], d["password"])
        await asyncio.to_thread(client.login)
        protocols = await asyncio.to_thread(client.list_protocols)
        groups = await asyncio.to_thread(client.list_groups)
    except Exception as e:
        return _err("panel", 502, detail=str(e)[:300])
    if b.get("step") != "save":
        return web.json_response({"ok": True, "protocols": protocols, "groups": groups, "insecure": bool(client.insecure),
                                  "services": [{"key": k, "name": ns["SERVICES"][k]} for k in ns["mappable_services"](protocols)]})
    mapping = _clean_map(b.get("map") or {})
    if mapping is None:
        return _err("map")
    max_users = _int(b.get("max_users"), 0) or ns["DEFAULT_PANEL_MAX_USERS"]
    draft = dict(d, max_users=max_users, status="active", protocols=protocols, tls_insecure=client.insecure)
    pid = ns["db"].add_panel(draft)
    ns["db"].set_service_map(pid, mapping)
    _admin_log(request, f"➕ پنل جدید «{d['name']}» اضافه شد ({d['location'] or '—'}، سقف {max_users})")
    return web.json_response({"ok": True, "panel": _panel_json(ns["db"].get_panel(pid))})


async def api_admin_plan_add(request):
    """{service, title, gb, days, price, users} — مثل plan_add_* ربات."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    b = await _body(request)
    service = b.get("service") or ""
    if service not in ns["SERVICES"]:
        return _err("service")
    title = (b.get("title") or "").strip()
    gb, days, price, users = _int(b.get("gb"), -1), _int(b.get("days"), -1), _int(b.get("price"), -1), _int(b.get("users"), 0)
    if not title or len(title) > 80 or gb < 0 or not 0 < days <= 3650 or not 0 < price <= 100_000_000 or not 0 <= users <= 5:
        return _err("fields")
    pid = ns["db"].add_plan(gb, days, price, title, users, service)
    _admin_log(request, f"➕ پلن جدید #{pid}: {ns['SERVICES'][service]} — {title} — {ns['fmt'](price)} تومان — {days} روز")
    return web.json_response({"ok": True, "plan": _plan_json(ns["db"].get_plan(pid))})


async def api_admin_plan_delete(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    b = await _body(request)
    p = ns["db"].get_plan(_int(b.get("id")))
    if not p:
        return _err("not_found", 404)
    ns["db"].delete_plan(p["id"])
    _admin_log(request, f"🗑 پلن #{p['id']} ({p['title'] or ''}) حذف شد")
    return web.json_response({"ok": True})


# تنظیماتی که از مینی‌اپ عوض می‌شوند؛ همان SETTING_KEYS ربات به‌علاوه‌ی چند کلید روشن/خاموش
SETTING_TOGGLES = [("test_enabled", "🎁 اکانت تست"), ("backup_auto", "💾 بکاپ خودکار روزانه")]
SETTING_EXTRA = [("support_username", "💬 یوزرنیم پشتیبانی (دایرکت)")]
# دامنه‌ی زاپاس لینک‌های اشتراک (public_sub_url در bot.py)؛ فقط همین گزینه‌ها، چون پنل باید آن‌ها را سرو کند
SUB_DOMAIN_KEY = "sub_domain_override"


def _sub_domain_choices():
    raw = ns["db"].setting("sub_backup_domains", "my.bomalo.ir") or ""
    return [d.strip().lower() for d in raw.split(",") if re.fullmatch(r"[a-z0-9.-]+\.[a-z]{2,}", d.strip().lower())]


async def api_admin_settings(request):
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    keys = ns["SETTING_KEYS"] + SETTING_EXTRA
    if request.method == "GET":
        return web.json_response({
            "subdomain": {"value": db.setting(SUB_DOMAIN_KEY, ""), "choices": _sub_domain_choices()},
            "items": [{"key": k, "label": l, "value": db.setting(k, ""),
                       "locked": k in ns["MAIN_ADMIN_SETTINGS"] and request["uid"] != ns["ADMIN_ID"]} for k, l in keys],
            "toggles": [{"key": k, "label": l, "on": db.setting(k, "1" if k == "backup_auto" else "0") == "1"}
                        for k, l in SETTING_TOGGLES]})
    b = await _body(request)
    key, value = b.get("key"), str(b.get("value") if b.get("value") is not None else "").strip()
    if key == SUB_DOMAIN_KEY:
        value = value.lower()
        if value and value not in _sub_domain_choices():
            return _err("domain")
        db.set_setting(SUB_DOMAIN_KEY, value)
        _panel_cache.clear()
        _admin_log(request, f"🌐 دامنه‌ی لینک‌های اشتراک شد: {value or 'دامنه‌ی اصلی'}")
        return web.json_response({"ok": True, "value": value})
    labels = dict(keys + SETTING_TOGGLES)
    if key not in labels:
        return _err("key")
    if key in ns["MAIN_ADMIN_SETTINGS"] and request["uid"] != ns["ADMIN_ID"]:
        return _err("main_only", 403)
    if key in dict(SETTING_TOGGLES):
        value = "1" if value in ("1", "true", "True") else "0"
    elif key in ("test_volume_gb", "test_days"):
        if _int(value, 0) <= 0:
            return _err("number")
        value = str(_int(value))
    elif key in ns["DAILY_TIMES"]:
        value = ns["parse_hhmm"](value)
        if not value:
            return _err("time")
    db.set_setting(key, value)
    if key in ns["DAILY_TIMES"]:
        ns["schedule_daily_jobs"](request.app["tg_app"].job_queue)
    shown = "روشن" if value == "1" and key in dict(SETTING_TOGGLES) else "خاموش" if key in dict(SETTING_TOGGLES) else value[:80]
    _admin_log(request, f"⚙️ تنظیم «{labels[key]}» شد: {shown}")
    return web.json_response({"ok": True, "value": value})


async def api_admin_admins(request):
    """GET: لیست. POST {action: add|del, id}: فقط ادمین اصلی (ADMIN_ID)، مثل دکمه‌های adm ربات."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db = ns["db"]
    main = ns["ADMIN_ID"]
    if request.method == "POST":
        if request["uid"] != main:
            return _err("main_only", 403)
        b = await _body(request)
        aid = _int(b.get("id"))
        ads = ns["get_admins"]()
        if b.get("action") == "add" and aid > 0 and aid != main and aid not in ads:
            ads.append(aid)
        elif b.get("action") == "del" and aid in ads:
            ads.remove(aid)
        else:
            return _err("action")
        db.set_setting("admins", json.dumps(ads))
        _admin_log(request, f"👑 ادمین {'اضافه' if b.get('action') == 'add' else 'حذف'} شد: {ns['who'](aid)}")

    def row(a):
        u = db.get_user(a)
        return {"id": a, "name": (u["full_name"] or "") if u else "", "uname": (u["username"] or "") if u else ""}
    return web.json_response({"main": row(main), "admins": [row(a) for a in ns["get_admins"]()],
                              "can_edit": request["uid"] == main})


async def api_admin_backup(request):
    """بکاپ همین الان، به همان جای بکاپ روزانه (کانال/گروه بکاپ، تاپیک بکاپ)."""
    if not _admin_only(request):
        return _err("forbidden", 403)
    db, bot = ns["db"], request.app["tg_app"].bot
    target = ns["_chat_target"](db.setting("backup_chat_id"))
    if target is None:
        return _err("no_target")
    try:
        ok = await ns["send_backup"](bot, target, "💾 بکاپ دستی از مینی‌اپ", thread_id=ns["group_thread"]("backup"))
    except Exception as e:
        return _err("send", 502, detail=str(e)[:200])
    _admin_log(request, "💾 بکاپ دستی گرفته شد")
    return web.json_response({"ok": bool(ok)})


# ---------- اکانت تست داخل مینی‌اپ ----------
async def api_test(request):
    """همان قانون send_test_account ربات (روشن بودن، سهمیه‌ی هر کاربر، اولین سرویس در دسترس)،
    با جواب JSON؛ کارت تحویل مثل خرید در چت فرستاده می‌شود."""
    uid = request["uid"]
    db = ns["db"]
    if db.setting("test_enabled", "0") != "1":
        return _err("disabled", 403)
    u = db.get_user(uid)
    limit = int((u["test_limit"] if u and u["test_limit"] is not None else 1))
    if db.one("SELECT COUNT(*) c FROM orders WHERE user_id=? AND price=0", (uid,))["c"] >= limit:
        return _err("quota", 409)
    service = next((x for x in ns["TEST_SERVICE_ORDER"] if ns["pick_panel"](x)), None)
    if not service:
        return _err("capacity", 503)
    lock = _buy_locks.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return _err("busy", 429)
    async with lock:
        plan = {"id": 0, "volume_gb": int(db.setting("test_volume_gb", "1") or 1),
                "days": int(db.setting("test_days", "1") or 1), "price": 0}
        try:
            order, panel = await asyncio.to_thread(ns["create_service_on_panel"], uid, plan, service, f"t{uid}")
        except Exception as e:
            log.warning("miniapp test account %s failed: %s", uid, e)
            return _err("failed", 502)
        app = request.app["tg_app"]
        ctx = SimpleNamespace(bot=app.bot, application=app, job_queue=app.job_queue, args=[])
        try:
            await ns["deliver_service"](ctx, uid, order, panel)
        except Exception as e:
            log.warning("miniapp test deliver failed: %s", e)
        await ns["notify_admin"](app.bot, f"🔑 اکانت تست از مینی‌اپ\n👤 کاربر: {uid}\n🧩 سرویس: {ns['SERVICES'][service]}")
        _panel_cache.pop(panel["id"], None)
    return web.json_response({"ok": True, "username": order["username"], "password": order["password"]})


# ---------- پل موقت: دکمه‌های مینی‌اپ همان مسیرهای امتحان‌پس‌داده‌ی ربات را در چت باز می‌کنند ----------
class ChatMessage:
    """جای update.message برای توابع منوی ربات: هر جوابی مستقیم در چت همان کاربر فرستاده می‌شود."""
    photo = None
    caption = None

    def __init__(self, bot, chat_id):
        self._bot, self.chat_id = bot, chat_id

    async def reply_text(self, text, **kw):
        return await self._bot.send_message(self.chat_id, text, **kw)

    async def reply_photo(self, photo, **kw):
        return await self._bot.send_photo(self.chat_id, photo, **kw)

    async def reply_document(self, document, **kw):
        return await self._bot.send_document(self.chat_id, document, **kw)

    async def delete(self):
        return True


GOTO_ACTIONS = {"buy", "renew_menu", "test", "services", "wallet", "support", "tutorial", "tariff"}


async def api_goto(request):
    uid = request["uid"]
    try:
        body = await request.json()
    except Exception:
        body = {}
    action = str(body.get("action") or "")
    app = request.app["tg_app"]
    msg = ChatMessage(app.bot, uid)
    db = ns["db"]
    if action == "renew":
        order = db.get_order(int(body.get("order_id") or 0))
        if not order or order["user_id"] != uid or order["status"] not in LIVE_ORDER_STATUSES:
            return web.json_response({"error": "not_found"}, status=404)
        coro = msg.reply_text(f"♻️ تمدید سرویس <b>{order['username']}</b>", parse_mode="HTML",
                              reply_markup=ns["InlineKeyboardMarkup"]([[ns["btn"]("♻️ تمدید این سرویس", f"renew:{order['id']}")]]))
    elif action in GOTO_ACTIONS:
        db.set_state(uid, "none")
        ctx = SimpleNamespace(bot=app.bot, application=app, job_queue=app.job_queue, args=[])
        coro = ns["run_menu_action"](msg, ctx, uid, action)
    else:
        return web.json_response({"error": "action"}, status=400)

    async def run():
        try:
            await coro
        except Exception as e:
            log.warning("miniapp goto %s for %s failed: %s", action, uid, e)
    asyncio.create_task(run())
    return web.json_response({"ok": True})


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-store"})


async def app_js(request):
    return web.FileResponse(STATIC_DIR / "app.js", headers={"Cache-Control": "no-store"})


async def start(application, bot_globals):
    """از post_init ربات صدا زده می‌شود."""
    ns.update(bot_globals)
    _APP["app"] = application
    app = web.Application(middlewares=[auth_mw], client_max_size=8 * 1024 * 1024)
    app.router.add_get("/", index)
    app.router.add_get("/app.js", app_js)
    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/customers", api_customers)
    app.router.add_get("/api/connect", api_connect)
    app.router.add_get("/api/qr", api_qr)
    app.router.add_get("/api/notifs", api_notifs)
    app.router.add_post("/api/notifs/seen", api_notifs_seen)
    app.router.add_get("/api/plans", api_plans)
    app.router.add_post("/api/goto", api_goto)
    app.router.add_post("/api/toggle", api_toggle)
    app.router.add_post("/api/buy", api_buy)
    app.router.add_get("/api/renew_plans", api_renew_plans)
    app.router.add_post("/api/renew", api_renew)
    app.router.add_get("/api/wallet", api_wallet)
    app.router.add_post("/api/charge", api_charge)
    app.router.add_get("/api/pending", api_pending)
    app.router.add_post("/api/pending/cancel", api_pending_cancel)
    app.router.add_post("/api/direct", api_direct)
    app.router.add_post("/api/direct/receipt", api_direct_receipt)
    app.router.add_post("/api/direct/cancel", api_direct_cancel)
    app.router.add_post("/api/test", api_test)
    app.router.add_get("/api/admin/summary", api_admin_summary)
    app.router.add_get("/api/admin/receipt_photo", api_admin_receipt_photo)
    app.router.add_post("/api/admin/receipt", api_admin_receipt)
    app.router.add_get("/api/admin/users", api_admin_users)
    app.router.add_get("/api/admin/user", api_admin_user)
    app.router.add_post("/api/admin/user", api_admin_user_action)
    app.router.add_get("/api/admin/plans", api_admin_plans)
    app.router.add_post("/api/admin/plan", api_admin_plan)
    app.router.add_get("/api/admin/tickets", api_admin_tickets)
    app.router.add_get("/api/admin/ticket_photo", api_admin_ticket_photo)
    app.router.add_post("/api/admin/ticket", api_admin_ticket)
    app.router.add_get("/api/admin/broadcast", api_admin_broadcast)
    app.router.add_post("/api/admin/broadcast", api_admin_broadcast)
    app.router.add_get("/api/admin/panels", api_admin_panels)
    app.router.add_post("/api/admin/panel", api_admin_panel)
    app.router.add_post("/api/admin/panel_add", api_admin_panel_add)
    app.router.add_post("/api/admin/plan_add", api_admin_plan_add)
    app.router.add_post("/api/admin/plan_delete", api_admin_plan_delete)
    app.router.add_get("/api/admin/settings", api_admin_settings)
    app.router.add_post("/api/admin/settings", api_admin_settings)
    app.router.add_get("/api/admin/admins", api_admin_admins)
    app.router.add_post("/api/admin/admins", api_admin_admins)
    app.router.add_post("/api/admin/backup", api_admin_backup)
    app["tg_app"] = application
    if (STATIC_DIR / "assets").is_dir():
        app.router.add_static("/assets/", STATIC_DIR / "assets", append_version=False)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    # shutdown_timeout کوتاه: موقع ری‌استارت ربات، درخواست‌های نیمه‌کاره حداکثر ۳ ثانیه صبر می‌کنند
    await web.TCPSite(runner, HOST, PORT, shutdown_timeout=3).start()
    application.bot_data["miniapp_runner"] = runner
    log.info("miniapp listening on %s:%s", HOST, PORT)
    await set_tester_buttons(application.bot)


async def stop(application):
    """از post_shutdown ربات: اتصال‌های باز (keep-alive ـه Caddy) را می‌بندد تا موقع خاموش شدن
    «Task was destroyed but it is pending» در لاگ نیاید."""
    runner = application.bot_data.pop("miniapp_runner", None)
    if runner:
        await runner.cleanup()
        log.info("miniapp stopped")


async def set_tester_buttons(bot):
    """دوره‌ی تست: دکمه‌ی منوی مینی‌اپ (کنار کادر پیام) فقط برای ادمین‌های اضافه‌شده (حساب‌های جواد).
    مشتری‌ها تا تأیید جواد چیزی نمی‌بینند."""
    from telegram import MenuButtonWebApp, WebAppInfo
    button = MenuButtonWebApp(text="Tifusi", web_app=WebAppInfo(url=MINIAPP_URL))
    if ns["db"].setting("miniapp_all", "0") == "1":
        # برای همه روشن است: دکمه‌ی منوی پیش‌فرض همه‌ی چت‌های ربات
        try:
            await bot.set_chat_menu_button(menu_button=button)
            log.info("miniapp default menu button set for everyone")
        except Exception as e:
            log.warning("miniapp default menu button failed: %s", e)
        return
    for uid in ns["get_admins"]():
        try:
            await bot.set_chat_menu_button(chat_id=uid, menu_button=button)
        except Exception as e:  # کسی که هنوز ربات را استارت نکرده
            log.info("miniapp menu button for %s skipped: %s", uid, e)
