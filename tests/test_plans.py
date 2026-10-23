"""The four plans (V2Ray, IKEv2 with the Tifusi app, L2TP, PPTP) and what each one gives."""

import asyncio

import pytest

import bot
import miniapp


def test_four_separate_plans_in_the_shop_in_order():
    assert list(miniapp.SHOP_SERVICES) == ["xray", "ikev2", "l2tp", "pptp"]
    for service in ("ikev2", "l2tp", "pptp"):
        assert bot.SERVICE_PROTOCOLS[service] == [service], "a buyer connects with what they bought and nothing else"


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
    # each customer gets a download with their own subscription inside the APK
    assert asyncio.run(miniapp._order_connect(order))["app_url"] == bot.tifusi_app_url(order["sub_url"])


def test_renew_rounds_the_new_limit_up_to_whole_gigabytes():
    """Usage 0.53 GB + a 40 GB renewal shows as 41 GB on the panel, not 40.53…"""
    api = bot.TifusiPanelAPI("https://panel.example", "admin", "pw")
    sent = {}
    api.find_user = lambda name: {"id": 7, "used_traffic": 569_000_000, "protocols": ["ikev2"]}
    api._call = lambda path, method, json=None: sent.setdefault("body", json) or {}
    api._with_links = lambda user: user
    api.renew_user("u", 40, 2_000_000_000)
    assert sent["body"]["data_limit"] == 41 * 1024 ** 3
    api.find_user = lambda name: {"id": 7, "used_traffic": 0, "protocols": ["ikev2"]}
    sent.clear()
    api.renew_user("u", 40, 2_000_000_000)
    assert sent["body"]["data_limit"] == 40 * 1024 ** 3


@pytest.mark.parametrize("limit,used,extra,expected", [
    (10, 0, 10, 20),
    (20, 10, 10, 30),
    (10, 10, 10, 20),
    (10, 12, 10, 22),
    (10, 3, 0, None),
])
def test_renew_preserves_remaining_traffic(limit, used, extra, expected):
    gb = 1024 ** 3
    api = bot.TifusiPanelAPI("https://panel.example", "admin", "pw")
    user = {"id": 7, "data_limit": limit * gb, "used_traffic": used * gb}
    api.find_user = lambda name: dict(user)
    sent = {}

    def call(path, method, json=None):
        assert path == "/api/users/7" and method == "put"
        sent.update(json)
        return {**user, **json}

    api._call = call
    api._with_links = lambda value: value
    result = api.renew_user("u", extra, 2_000_000_000)
    assert sent["data_limit"] == (expected * gb if expected is not None else None)
    assert "used_traffic" not in sent
    assert result["used_traffic"] == used * gb


def test_connect_carries_the_panels_short_link_for_ikev2(world, monkeypatch):
    """The short link (guide page + app download + one-tap import) goes into the share text instead of the long sub link."""
    order = {"id": 1, "username": "u", "password": "", "sub_url": "https://panel.example/sub/abc", "panel_id": 3,
             "protocol": "ikev2"}
    links = {"share_url": "https://panel.example/app/s/uK7Q3MZP2", "ikev2_configs": [{"server": "vpn.example", "password": "p"}]}
    monkeypatch.setitem(miniapp.ns, "db", type("D", (), {"get_panel": staticmethod(lambda pid: {"id": pid})})())
    monkeypatch.setitem(miniapp.ns, "panel_client", lambda panel: type("C", (), {"links": staticmethod(lambda name: links)})())
    assert asyncio.run(miniapp._order_connect(order))["share"] == "https://panel.example/app/s/uK7Q3MZP2"
    links = {"share_url": "https://panel.example/app/s/uK7Q3MZP2", "l2tp_configs": [{"server": "vpn.example", "password": "p"}]}
    l2tp = asyncio.run(miniapp._order_connect({**order, "protocol": "l2tp"}))
    assert l2tp["share"] is None and l2tp["app_url"] is None, "the app and its short link are IKEv2 only"


def _old_order(monkeypatch, last_protocol, protocols=("ikev2", "l2tp", "pptp")):
    """An order from when one account carried IKEv2 + L2TP + PPTP together."""
    order = {"id": 1, "username": "negar", "password": "", "sub_url": "https://panel.example/sub/abc", "panel_id": 3,
             "protocol": "ikev2"}
    links = {"user": {"username": "negar", "protocols": list(protocols) if protocols else None},
             "share_url": "https://panel.example/app/s/negarK7Q3MZP2", "last_protocol": last_protocol,
             "ikev2_configs": [{"server": "ike.example", "password": "123456", "install_url": "https://panel.example/sub/abc/ikev2"}],
             "l2tp_configs": [{"server": "l2tp.example", "password": "123456", "psk": "secret"}],
             "pptp_configs": [{"server": "pptp.example"}]}
    monkeypatch.setitem(miniapp.ns, "db", type("D", (), {"get_panel": staticmethod(lambda pid: {"id": pid})})())
    monkeypatch.setitem(miniapp.ns, "panel_client", lambda panel: type("C", (), {"links": staticmethod(lambda name: links)})())
    return order


def test_an_old_combined_order_shows_only_what_the_customer_connects_with(world, monkeypatch):
    order = _old_order(monkeypatch, "l2tp")
    x = asyncio.run(miniapp._order_connect(order))
    assert x["narrowed"] == "l2tp" and x["l2tp"]["server"] == "l2tp.example" and x["l2tp"]["secret"] == "secret"
    assert x["ikev2"] is None and x["pptp"] is None
    assert x["app_url"] is None and x["share"] is None, "no Tifusi app for someone on L2TP"

    x = asyncio.run(miniapp._order_connect(_old_order(monkeypatch, "ikev2")))
    assert x["narrowed"] == "ikev2" and x["l2tp"] is None and x["pptp"] is None
    assert x["app_url"] == bot.tifusi_app_url(order["sub_url"]) and x["share"] and x["ikev2"]["install"].endswith("/ikev2")

    everything = asyncio.run(miniapp._order_connect(order, show_all=True))
    assert everything["narrowed"] is None and all(everything[k] for k in ("ikev2", "l2tp", "pptp"))


def test_an_order_nobody_has_connected_with_yet_shows_everything(world, monkeypatch):
    for last in (None, "xray"):
        x = asyncio.run(miniapp._order_connect(_old_order(monkeypatch, last)))
        assert x["narrowed"] is None and all(x[k] for k in ("ikev2", "l2tp", "pptp")), last
    unrestricted = asyncio.run(miniapp._order_connect(_old_order(monkeypatch, "pptp", protocols=None)))
    assert unrestricted["narrowed"] is None and unrestricted["ikev2"], "an account with no protocol limit is left alone"


def test_a_users_special_gb_price_and_days_apply_only_to_them(world):
    """One customer: every volume plan at 5,000 a GB and 35 days; everyone else keeps the plan as it is."""
    db = bot.db
    pid = db.add_plan(20, 30, 140000, title="20 گیگ", user_limit=1, service="ikev2")
    db.ensure_user(101, "special", "special")
    db.ensure_user(102, "other", "other")
    db.x("UPDATE users SET gb_price=5000, plan_days=35, discount_pct=50 WHERE id=101")
    special, normal = bot.user_plan(pid, 101), bot.user_plan(pid, 102)
    assert (special["price"], special["days"]) == (100000, 35)  # the special price replaces the discount
    assert (normal["price"], normal["days"]) == (140000, 30)
    db.x("UPDATE users SET gb_price=0, plan_days=0 WHERE id=101")
    assert (bot.user_plan(pid, 101)["price"], bot.user_plan(pid, 101)["days"]) == (70000, 30)


def test_mini_app_sells_only_ikev2_then_xray():
    assert miniapp.SHOP_FOR_SALE == ("ikev2", "xray"), "IKEv2 first is the default; L2TP/PPTP are not sold"
