"""Money paths that need no mini app: the wallet ledger, purchases interrupted
by a restart, a panel reply lost after the panel had already done the work,
and receipt approval edge cases."""

import asyncio
import time

import bot
import pytest
from tests.conftest import customer


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)



# ---------------------------------------------------------------- wallet ledger

def test_every_wallet_move_is_logged_with_the_balance_after(world):
    uid = customer()
    bot.db.add_balance(uid, 300_000, "شارژ")
    assert bot.db.try_spend(uid, 200_000, "خرید alice")
    assert not bot.db.try_spend(uid, 200_000, "خرید bob")
    rows = bot.db.q("SELECT amount, reason, balance_after FROM wallet_log WHERE user_id=? ORDER BY id", (uid,))
    assert [(r["amount"], r["reason"], r["balance_after"]) for r in rows] == [
        (300_000, "شارژ", 300_000), (-200_000, "خرید alice", 100_000)], "a refused spend leaves no line"


def test_interrupted_purchase_is_reported_once_after_a_restart(world):
    uid = customer(balance=200_000)
    assert bot.db.try_spend(uid, 200_000, "خرید alice")
    bot.db.begin_op(uid, "buy", 200_000, "ikev2 alice")  # ... and the bot dies here
    run(bot.report_open_ops(world.app.bot))
    assert len(world.admin_notes) == 1 and "alice" in world.admin_notes[0] and "200,000" in world.admin_notes[0]
    run(bot.report_open_ops(world.app.bot))
    assert len(world.admin_notes) == 1, "not repeated on every start"



# ---------------------------------------------------------------- lost panel reply

def lost_reply_api(monkeypatch, existing):
    api = bot.TifusiPanelAPI("https://panel.example", "u", "tifusi_key")
    calls = []

    def _call(path, method="get", **kw):
        calls.append((method, path))
        if method in ("post", "put"):
            raise bot.PanelError("خطای اتصال: read timed out")  # no .status: the reply never came
        if path == "/api/users":
            return {"users": [existing] if existing else []}
        return {"subscription_url": "https://panel.example/sub/sek"}

    monkeypatch.setattr(api, "_call", _call)
    return api


def test_account_created_although_the_reply_was_lost_is_not_refunded(world, monkeypatch):
    now_iso = bot.datetime.datetime.now(bot.datetime.timezone.utc).isoformat()
    api = lost_reply_api(monkeypatch, {"id": 5, "username": "alice", "note": "Tifusi Bot", "created_at": now_iso, "secret": "sek"})
    res = api.add_user([], "alice", 10, int(time.time()) + 86400)
    assert res["user"]["id"] == 5 and res["subscription_url"].endswith("/sub/sek")


def test_lost_reply_never_adopts_somebody_elses_old_account(world, monkeypatch):
    old = (bot.datetime.datetime.now(bot.datetime.timezone.utc) - bot.datetime.timedelta(days=3)).isoformat()
    for existing in (None,
                     {"id": 5, "username": "alice", "note": "Tifusi Bot", "created_at": old, "secret": "sek"},
                     {"id": 5, "username": "alice", "note": "made by hand", "secret": "sek",
                      "created_at": bot.datetime.datetime.now(bot.datetime.timezone.utc).isoformat()}):
        api = lost_reply_api(monkeypatch, existing)
        with pytest.raises(bot.PanelError):
            api.add_user([], "alice", 10, int(time.time()) + 86400)


def test_a_real_refusal_from_the_panel_is_still_an_error(world, monkeypatch):
    api = bot.TifusiPanelAPI("https://panel.example", "u", "tifusi_key")

    def _call(path, method="get", **kw):
        err = bot.PanelError("username exists")
        err.status = 409
        raise err

    monkeypatch.setattr(api, "_call", _call)
    with pytest.raises(bot.PanelError):
        api.add_user([], "alice", 10, int(time.time()) + 86400)


def test_renewal_done_although_the_reply_was_lost_counts_as_done(world, monkeypatch):
    target = int(time.time()) + 30 * 86400
    state = {"expire": "2020-01-01T00:00:00+00:00"}
    api = bot.TifusiPanelAPI("https://panel.example", "u", "tifusi_key")

    def _call(path, method="get", **kw):
        if method == "put":
            state["expire"] = kw["json"]["expire"]  # the panel saved it, then the line dropped
            raise bot.PanelError("خطای اتصال: read timed out")
        if path == "/api/users":
            return {"users": [{"id": 5, "username": "alice", "data_limit": 0, "used_traffic": 0, "secret": "sek", **state}]}
        return {"subscription_url": "https://panel.example/sub/sek"}

    monkeypatch.setattr(api, "_call", _call)
    res = api.renew_user("alice", 10, target)
    assert res is not None and abs(bot.panel_expire_ts(res["user"]["expire"]) - target) <= 60

    def _call_not_saved(path, method="get", **kw):
        if method == "put":
            raise bot.PanelError("خطای اتصال: connection refused")
        if path == "/api/users":
            return {"users": [{"id": 5, "username": "alice", "data_limit": 0, "used_traffic": 0, "secret": "sek",
                               "expire": "2020-01-01T00:00:00+00:00"}]}
        return {}

    monkeypatch.setattr(api, "_call", _call_not_saved)
    with pytest.raises(bot.PanelError):
        api.renew_user("alice", 10, target)


# ---------------------------------------------------------------- receipts

class Msg:
    chat_id = 0
    photo = None

    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kw):
        self.replies.append(text)

    async def delete(self):
        return True

    async def edit_reply_markup(self, **kw):
        return True


class Query:
    def __init__(self):
        self.message = Msg()

    async def answer(self, *a, **k):
        return True


class Ctx:
    def __init__(self, app):
        self.bot, self.application, self.job_queue, self.args = app.bot, app, None, []


def test_charge_is_approved_even_when_the_customer_cannot_be_messaged(world, monkeypatch):
    uid = customer()
    rid = bot.db.create_receipt(uid, 150_000, "wallet_charge", "photo")

    async def tell(*a, **k):
        raise RuntimeError("Forbidden: bot was blocked by the user")

    monkeypatch.setattr(bot, "tell", tell)
    q = Query()
    run(bot.rc_approve(q, Ctx(world.app), rid))
    assert bot.db.get_balance(uid) == 150_000 and bot.db.get_receipt(rid)["status"] == "approved"
    assert any("تایید شد" in t for t in q.message.replies), "the admin sees success, not an error"
    run(bot.rc_approve(Query(), Ctx(world.app), rid))
    assert bot.db.get_balance(uid) == 150_000, "a second approval adds nothing"


def test_purchase_receipt_for_a_deleted_plan_goes_to_the_wallet(world):
    uid = customer()
    rid = bot.db.create_receipt(uid, 180_000, "purchase", "photo",
                                {"plan_id": 987_654, "protocol": "xray", "username": "alice"})
    q = Query()
    run(bot.rc_approve(q, Ctx(world.app), rid))
    assert bot.db.get_balance(uid) == 180_000 and world.created == []
    assert any("کیف پول" in t for t in q.message.replies)


def test_two_receipts_for_one_direct_order_have_one_winner(world):
    uid = customer()
    did = bot.db.x("INSERT INTO direct_orders (user_id,ticket_id,plan_id,service,username,password,amount,status,created_at) "
                   "VALUES (?,?,?,?,?,?,?,'open',?)", (uid, 0, 1, "xray", "alice", "", 1000, int(time.time())))
    assert [bot.db.claim_direct(did, "open", "uploading") for _ in range(3)] == [True, False, False]

