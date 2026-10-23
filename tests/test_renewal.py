"""Renewal entry points share byte-exact carryover and retain cumulative usage."""

import asyncio
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import bot
import miniapp
from tests.conftest import customer
from tests.test_miniapp import TOKEN, init_data

GIB = 1024 ** 3


@pytest.mark.parametrize("entry", ["miniapp", "bot_button", "admin"])
@pytest.mark.parametrize("old_limit,old_used", [
    pytest.param(20 * GIB + 123, 7 * GIB + 12, id="leftover"),
    pytest.param(0, 0, id="zero-leftover"),
    pytest.param(10 * GIB, 10 * GIB, id="fully-used"),
    pytest.param(10 * GIB, 12 * GIB + 1, id="overused"),
])
def test_renewal_carries_remaining_traffic(entry, old_limit, old_used, world, plan, monkeypatch):
    uid = customer(balance=500_000)
    pid = bot.db.add_panel({"name": "P1", "url": "https://panel.example", "protocols": {"vless": 1}})
    expires = bot.now() + 86400
    oid = bot.db.create_order({
        "user_id": uid, "panel_id": pid, "plan_id": plan["id"], "protocol": "xray",
        "username": "renew_me", "volume_gb": 20, "expire_at": expires,
        "sub_url": "https://panel.example/sub/original",
    })
    panel_user = {"id": 7, "username": "renew_me", "data_limit": old_limit,
                  "used_traffic": old_used, "protocols": ["vless"]}
    updates = []
    api = bot.TifusiPanelAPI("https://panel.example", "admin", "pw")
    monkeypatch.setattr(api, "find_user", lambda name: dict(panel_user))

    def call(path, method="get", json=None):
        if path == "/api/users/7/links" and method == "get":
            return {"subscription_url": "https://panel.example/sub/original", "app_code": "original"}
        assert path == "/api/users/7" and method == "put", "renew the existing user without a reset"
        updates.append(dict(json))
        panel_user.update(json)
        return dict(panel_user)

    monkeypatch.setattr(api, "_call", call)
    monkeypatch.setattr(bot, "panel_client", lambda panel: api)
    miniapp.ns.update(vars(bot))
    monkeypatch.setitem(miniapp.ns, "BOT_TOKEN", TOKEN)
    ctx = SimpleNamespace(bot=world.app.bot)

    async def renew():
        if entry == "miniapp":
            app = web.Application(middlewares=[miniapp.auth_mw])
            app.router.add_post("/api/renew", miniapp.api_renew)
            app["tg_app"] = world.app
            async with TestClient(TestServer(app)) as client:
                response = await client.post(
                    "/api/renew", json={"order_id": oid, "plan_id": plan["id"]},
                    headers={"X-Init-Data": init_data(uid)},
                )
                assert response.status == 200, await response.text()
                assert (await response.json())["ok"]
        elif entry == "bot_button":
            query = miniapp._AdminQuery()
            query.data = f"rnw:w:{oid}:{plan['id']}"
            update = SimpleNamespace(callback_query=query, effective_user=SimpleNamespace(
                id=uid, username="cust", full_name="Customer"))
            await bot.on_callback(update, ctx)
        else:
            rid = bot.db.create_receipt(uid, plan["price"], "renew", "photo", {
                "order_id": oid, "plan_id": plan["id"],
            })
            await bot.rc_approve(miniapp._AdminQuery(), ctx, rid)
            assert bot.db.get_receipt(rid)["status"] == "approved"

    asyncio.run(renew())
    remaining = max(old_limit - old_used, 0)
    assert len(updates) == 1
    assert panel_user["used_traffic"] == old_used
    assert "used_traffic" not in updates[0]
    assert panel_user["data_limit"] - old_used == remaining + plan["volume_gb"] * GIB
    renewed = bot.db.get_order(oid)
    assert renewed["username"] == "renew_me" and renewed["sub_url"].endswith("/original")
    assert renewed["expire_at"] == expires + plan["days"] * 86400
    assert bot.db.get_balance(uid) == 500_000 - (0 if entry == "admin" else plan["price"])
