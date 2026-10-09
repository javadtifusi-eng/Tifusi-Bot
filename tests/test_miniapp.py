"""Mini App API: Telegram's initData signature, buying from the wallet (and
the pending purchase finished automatically after a charge), Free Pass, and
the direct (card-to-card through a ticket) order."""

import asyncio
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import bot
import miniapp
from tests.conftest import customer

TOKEN = "123456:TEST-TOKEN"


def init_data(uid, token=TOKEN, age=0):
    pairs = {"auth_date": str(int(time.time()) - age), "query_id": "q1",
             "user": json.dumps({"id": uid, "first_name": "Ali", "username": "ali"})}
    check = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    pairs["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(pairs)


def test_init_data_signature():
    uid, _ = miniapp.verify_init_data(init_data(42), TOKEN)
    assert uid == 42
    assert miniapp.verify_init_data(init_data(42, token="999:OTHER"), TOKEN) is None, "signed by another bot"
    assert miniapp.verify_init_data(init_data(42, age=miniapp.INIT_DATA_MAX_AGE + 60), TOKEN) is None, "too old"
    tampered = init_data(42).replace("%22id%22%3A+42", "%22id%22%3A+43")
    assert miniapp.verify_init_data(tampered, TOKEN) is None
    assert miniapp.verify_init_data("", TOKEN) is None


def _run(world, coro_fn):
    async def go():
        app = web.Application(middlewares=[miniapp.auth_mw])
        for path, handler in (("/api/buy", miniapp.api_buy), ("/api/direct", miniapp.api_direct),
                              ("/api/direct/cancel", miniapp.api_direct_cancel), ("/api/pending", miniapp.api_pending)):
            (app.router.add_get if path == "/api/pending" else app.router.add_post)(path, handler)
        app["tg_app"] = world.app
        async with TestClient(TestServer(app)) as client:
            return await coro_fn(client)
    return asyncio.run(go())


@pytest.fixture(autouse=True)
def token(world, monkeypatch):
    monkeypatch.setitem(miniapp.ns, "BOT_TOKEN", TOKEN)


def _h(uid):
    return {"X-Init-Data": init_data(uid)}


def test_api_rejects_unsigned(world):
    async def go(c):
        return (await c.post("/api/buy", json={})).status
    assert _run(world, go) == 401


def test_buy_from_wallet(world, plan):
    uid = customer(2001, balance=500_000)

    async def go(c):
        r = await c.post("/api/buy", json={"service": "xray", "plan_id": plan["id"], "qty": 2, "username": "shop"}, headers=_h(uid))
        return r.status, await r.json()
    status, body = _run(world, go)
    assert status == 200 and body["ok"] and [m["username"] for m in body["made"]] == ["shop", "shop2"]
    assert body["made"][0]["sub"].startswith("https://"), "V2Ray gets its subscription link"
    assert bot.db.get_balance(uid) == 100_000


def test_buy_without_balance_is_kept_then_finished_after_charge(world, plan):
    uid = customer(2002, balance=50_000)

    async def go(c):
        r = await c.post("/api/buy", json={"service": "xray", "plan_id": plan["id"], "username": "later1"}, headers=_h(uid))
        return r.status, await r.json()
    status, body = _run(world, go)
    assert status == 402 and body["pending"] and body["need"] == 150_000
    assert world.created == [] and bot.db.get_balance(uid) == 50_000

    # The admin approves a charge; the saved purchase completes by itself.
    rid = bot.db.create_receipt(uid, 200_000, "wallet_charge", "p")
    q = miniapp._AdminQuery()
    asyncio.run(bot.rc_approve(q, type("C", (), {"bot": world.app.bot})(), rid))
    assert world.created == [(uid, "later1", 200_000)]
    assert bot.db.get_balance(uid) == 50_000, "250k after the charge, minus the 200k plan"
    assert miniapp._pending(uid) is None


def test_free_pass_buys_without_paying(world, plan):
    uid = customer(105455518, balance=0)

    async def go(c):
        r = await c.post("/api/buy", json={"service": "xray", "plan_id": plan["id"], "username": "admin1"}, headers=_h(uid))
        return r.status, await r.json()
    status, body = _run(world, go)
    assert status == 200 and body["ok"]
    assert world.created == [(uid, "admin1", 0)], "a free pass order is recorded at price 0 (not revenue)"
    assert bot.db.get_balance(uid) == 0


def test_buy_validation(world, plan):
    uid = customer(2003, balance=10**7)

    async def go(c):
        bad_plan = await c.post("/api/buy", json={"service": "xray", "plan_id": 999}, headers=_h(uid))
        bad_name = await c.post("/api/buy", json={"service": "xray", "plan_id": plan["id"], "username": "1bad"}, headers=_h(uid))
        bad_service = await c.post("/api/buy", json={"service": "pptp", "plan_id": plan["id"]}, headers=_h(uid))
        return [bad_plan.status, bad_name.status, bad_service.status]
    assert _run(world, go) == [400, 400, 400]
    assert world.created == [] and bot.db.get_balance(uid) == 10**7


def test_direct_order_creates_ticket_and_no_account(world, plan):
    uid = customer(2004)

    async def go(c):
        r = await c.post("/api/direct", json={"service": "xray", "plan_id": plan["id"], "username": "cardpay"}, headers=_h(uid))
        body = await r.json()
        cancel = await c.post("/api/direct/cancel", json={"id": body["direct"]["id"]}, headers=_h(uid))
        again = await c.post("/api/direct/cancel", json={"id": body["direct"]["id"]}, headers=_h(uid))
        return r.status, body, cancel.status, again.status
    status, body, cancel, again = _run(world, go)
    assert status == 200 and body["direct"]["status"] == "open" and body["direct"]["amount"] == 200_000
    assert world.created == [], "no account until a receipt is approved"
    ticket = bot.db.get_ticket(body["direct"]["ticket"])
    assert "cardpay" in ticket["message"]
    assert cancel == 200 and again == 404
    assert bot.db.get_ticket(ticket["id"])["status"] == "closed"


def _run_settings(world, coro_fn):
    async def go():
        app = web.Application(middlewares=[miniapp.auth_mw])
        app.router.add_get("/api/admin/settings", miniapp.api_admin_settings)
        app.router.add_post("/api/admin/settings", miniapp.api_admin_settings)
        app["tg_app"] = world.app
        async with TestClient(TestServer(app)) as client:
            return await coro_fn(client)
    return asyncio.run(go())


def test_card_and_backup_target_are_main_admin_only(world):
    """A secondary admin changing the card number or the backup chat could send customers' money or the
    whole database to themselves; only ADMIN_ID (1) may change them, other settings stay open to admins."""
    bot.db.set_setting("admins", json.dumps([7]))
    bot.db.set_setting("card_number", "6037-main")

    async def go(c):
        out = {}
        for uid in (7, 1):
            for key in ("card_number", "card_name", "backup_chat_id", "faq_text"):
                r = await c.post("/api/admin/settings", json={"key": key, "value": f"{key}-{uid}"}, headers=_h(uid))
                out[(uid, key)] = r.status
        r = await c.get("/api/admin/settings", headers=_h(7))
        out["locked"] = {x["key"] for x in (await r.json())["items"] if x["locked"]}
        out["customer"] = (await c.post("/api/admin/settings", json={"key": "faq_text", "value": "x"},
                                        headers=_h(customer(3001)))).status
        return out
    out = _run_settings(world, go)
    for key in ("card_number", "card_name", "backup_chat_id"):
        assert out[(7, key)] == 403, key
        assert out[(1, key)] == 200, key
    assert out[(7, "faq_text")] == 200
    assert out["locked"] == {"card_number", "card_name", "backup_chat_id"}
    assert out["customer"] == 403
    assert bot.db.setting("card_number") == "card_number-1"
