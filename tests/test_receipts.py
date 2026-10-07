"""Card-to-card receipts: nothing is credited or built without an admin's
approval, an approval counts once, and every failure after approval refunds."""

import asyncio
import json

import bot
import miniapp
from tests.conftest import customer


def _approve(world, rid):
    q = miniapp._AdminQuery()
    asyncio.run(bot.rc_approve(q, type("C", (), {"bot": world.app.bot})(), rid))
    return q.notes


def _reject(world, rid):
    q = miniapp._AdminQuery()
    asyncio.run(bot.rc_reject(q, type("C", (), {"bot": world.app.bot})(), rid))
    return q.notes


def test_charge_needs_approval_and_counts_once(world):
    uid = customer()
    rid = bot.db.create_receipt(uid, 300_000, "wallet_charge", "photo-1")
    assert bot.db.get_balance(uid) == 0, "a receipt alone credits nothing"
    _approve(world, rid)
    assert bot.db.get_balance(uid) == 300_000
    assert bot.db.get_receipt(rid)["status"] == "approved"
    notes = _approve(world, rid)  # a second admin taps approve too
    assert bot.db.get_balance(uid) == 300_000, "approving twice must not credit twice"
    assert any("قبلاً" in n for n in notes)


def test_reject_credits_nothing_and_closes(world):
    uid = customer()
    rid = bot.db.create_receipt(uid, 300_000, "wallet_charge", "photo-1")
    _reject(world, rid)
    assert bot.db.get_balance(uid) == 0 and bot.db.get_receipt(rid)["status"] == "rejected"
    _approve(world, rid)
    assert bot.db.get_balance(uid) == 0, "a rejected receipt can't be approved afterwards"


def test_purchase_receipt_builds_at_the_paid_price(world, plan):
    uid = customer()
    meta = {"plan_id": plan["id"], "protocol": "xray", "username": "paid1", "panel_id": None}
    rid = bot.db.create_receipt(uid, 150_000, "purchase", "photo-2", meta)  # paid with a 25% discount
    _approve(world, rid)
    assert world.created == [(uid, "paid1", 150_000)], "the order records what the customer actually paid"
    assert bot.db.get_balance(uid) == 0


def test_purchase_receipt_panel_failure_refunds_to_wallet(world, plan):
    uid = customer()
    world.panel_fails = True
    did = bot.db.x("INSERT INTO direct_orders (user_id,ticket_id,plan_id,service,username,password,amount,status,created_at) "
                   "VALUES (?,?,?,?,?,?,?,'receipt',0)", (uid, 0, plan["id"], "xray", "direct1", "", 200_000))
    meta = {"plan_id": plan["id"], "protocol": "xray", "username": "direct1", "panel_id": None, "direct_order_id": did}
    rid = bot.db.create_receipt(uid, 200_000, "purchase", "photo-3", meta)
    _approve(world, rid)
    assert bot.db.get_balance(uid) == 200_000
    assert bot.db.one("SELECT status FROM direct_orders WHERE id=?", (did,))["status"] == "refunded"


def test_direct_order_done_after_approval(world, plan):
    uid = customer()
    did = bot.db.x("INSERT INTO direct_orders (user_id,ticket_id,plan_id,service,username,password,amount,status,created_at) "
                   "VALUES (?,?,?,?,?,?,?,'receipt',0)", (uid, 0, plan["id"], "xray", "direct2", "", 200_000))
    rid = bot.db.create_receipt(uid, 200_000, "purchase", "p", {"plan_id": plan["id"], "protocol": "xray",
                                                                "username": "direct2", "direct_order_id": did})
    _approve(world, rid)
    assert bot.db.one("SELECT status FROM direct_orders WHERE id=?", (did,))["status"] == "done"
    assert world.created == [(uid, "direct2", 200_000)]


def test_renew_receipt_for_inactive_order_refunds(world, plan):
    uid = customer()
    oid = bot.db.create_order({"user_id": uid, "panel_id": 1, "plan_id": plan["id"], "protocol": "xray",
                               "username": "old", "expire_at": 0})
    bot.db.update_order(oid, status="archived")
    rid = bot.db.create_receipt(uid, 200_000, "renew", "p", {"order_id": oid, "plan_id": plan["id"]})
    _approve(world, rid)
    assert bot.db.get_balance(uid) == 200_000


def test_purchase_with_deleted_plan_is_not_built(world, plan):
    uid = customer()
    rid = bot.db.create_receipt(uid, 200_000, "purchase", "p", {"plan_id": 424242, "protocol": "xray", "username": "x1"})
    notes = _approve(world, rid)
    assert world.created == [] and any("دستی" in n for n in notes)
