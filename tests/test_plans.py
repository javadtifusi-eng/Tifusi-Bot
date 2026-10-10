"""The three plans (V2Ray, L2TP · PPTP, IKEv2 with the Tifusi app) and what each one gives."""

import asyncio

import bot
import miniapp


def test_three_plans_in_the_shop_in_order():
    assert list(miniapp.SHOP_SERVICES) == ["xray", "l2tp", "ikev2"]
    assert bot.SERVICE_PROTOCOLS["ikev2"] == ["ikev2"]
    assert bot.SERVICE_PROTOCOLS["l2tp"] == ["l2tp", "pptp"]


def test_renew_never_takes_a_protocol_away():
    """An IKEv2 order bought when the plan was IKEv2 + L2TP + PPTP keeps L2TP and PPTP on renewal."""
    api = bot.TifusiPanelAPI("https://panel.example", "admin", "pw")
    sent = {}
    api.find_user = lambda name: {"id": 7, "used_traffic": 0, "protocols": ["ikev2", "l2tp", "pptp"]}

    def call(path, method, json=None):
        sent["body"] = json
        return {"subscription_url": "https://panel.example/sub/x", "app_code": None}

    api._call = call
    api._with_links = lambda user: user
    api.renew_user("old", 10, 2_000_000_000, protocols=["ikev2"])
    assert sent["body"]["protocols"] == ["ikev2", "l2tp", "pptp"]


def test_connect_offers_the_app_only_for_ikev2(world, monkeypatch):
    base = {"id": 1, "username": "u", "password": "", "sub_url": "https://panel.example/sub/abc", "panel_id": 0}
    assert asyncio.run(miniapp._order_connect({**base, "protocol": "xray"}))["app_url"] is None
    monkeypatch.setitem(miniapp.ns, "db", type("D", (), {"get_panel": staticmethod(lambda pid: None)})())
    order = {**base, "protocol": "ikev2"}
    assert asyncio.run(miniapp._order_connect(order))["app_url"] == bot.TIFUSI_APP_URL
