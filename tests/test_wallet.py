"""Wallet money paths: spending is atomic and never goes negative, personal
discounts reach every price, a failed panel refunds, and a purchase that
couldn't be paid is kept for after the next charge."""

import asyncio

import bot
import miniapp
from tests.conftest import customer


def test_try_spend_is_atomic_and_never_negative(world):
    uid = customer(balance=100_000)
    assert bot.db.try_spend(uid, 60_000) is True
    assert bot.db.get_balance(uid) == 40_000
    assert bot.db.try_spend(uid, 60_000) is False, "not enough left"
    assert bot.db.get_balance(uid) == 40_000, "a refused spend takes nothing"
    assert bot.db.try_spend(uid, 40_000) is True and bot.db.get_balance(uid) == 0


def test_double_tap_cannot_spend_twice(world):
    uid = customer(balance=200_000)
    results = [bot.db.try_spend(uid, 200_000) for _ in range(5)]
    assert results.count(True) == 1 and bot.db.get_balance(uid) == 0


def test_discount_applies_and_is_clamped(world, plan):
    uid = customer()
    assert bot.user_plan(plan["id"], uid)["price"] == 200_000
    bot.db.x("UPDATE users SET discount_pct=25 WHERE id=?", (uid,))
    assert bot.user_plan(plan["id"], uid)["price"] == 150_000
    bot.db.x("UPDATE users SET discount_pct=250 WHERE id=?", (uid,))
    assert bot.user_plan(plan["id"], uid)["price"] == 0, "discount is capped at 100%"
    bot.db.x("UPDATE users SET discount_pct=-30 WHERE id=?", (uid,))
    assert bot.user_plan(plan["id"], uid)["price"] == 200_000, "a negative discount never raises the price"
    assert bot.user_plan(999_999, uid) is None


def test_free_pass_ids():
    assert bot.has_free_pass(105455518) and bot.has_free_pass(8178830447) and bot.has_free_pass(8579077076)
    assert not bot.has_free_pass(10545518), "the typo'd id is not a free pass"


def Query():
    # The mini app's stand-in for a callback query: records edits instead of calling Telegram.
    return miniapp._AdminQuery()


class Ctx:
    def __init__(self, app):
        self.bot = app.bot


def _buy_data(plan, username="ali123"):
    return {"plan_id": plan["id"], "protocol": "xray", "username": username, "panel_id": None, "ipsec_password": None}


def test_wallet_purchase_success(world, plan):
    uid = customer(balance=250_000)
    asyncio.run(bot.finalize_wallet_purchase(Query(), Ctx(world.app), uid, _buy_data(plan)))
    assert bot.db.get_balance(uid) == 50_000
    assert world.created == [(uid, "ali123", 200_000)] and world.delivered == ["ali123"]
    assert bot.load_pending_buy(uid) is None


def test_wallet_purchase_insufficient_saves_pending(world, plan):
    uid = customer(balance=50_000)
    asyncio.run(bot.finalize_wallet_purchase(Query(), Ctx(world.app), uid, _buy_data(plan)))
    assert bot.db.get_balance(uid) == 50_000 and world.created == []
    pending = bot.load_pending_buy(uid)
    assert pending["plan_id"] == plan["id"] and pending["username"] == "ali123"


def test_wallet_purchase_panel_failure_refunds(world, plan):
    uid = customer(balance=200_000)
    world.panel_fails = True
    asyncio.run(bot.finalize_wallet_purchase(Query(), Ctx(world.app), uid, _buy_data(plan)))
    assert bot.db.get_balance(uid) == 200_000, "the money comes back when the panel can't build the service"
    assert world.created == []


def test_pending_buy_expires(world, plan, monkeypatch):
    uid = customer()
    bot.save_pending_buy(uid, _buy_data(plan))
    assert bot.load_pending_buy(uid) is not None
    real_now = bot.now()
    monkeypatch.setattr(bot, "now", lambda: real_now + bot.PENDING_BUY_TTL + 1)
    assert bot.load_pending_buy(uid) is None
