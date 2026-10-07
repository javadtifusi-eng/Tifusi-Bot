"""bot.py opens its SQLite database (vpn_bot.db, in the working directory) the
moment it is imported, so the suite moves into a throwaway directory first.
Everything that would reach Telegram or a panel is replaced by fakes that
record what happened; the money logic itself runs for real."""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

_cwd = os.getcwd()
os.chdir(tempfile.mkdtemp(prefix="tifusi-bot-tests-"))
try:
    import bot  # noqa: E402  creates vpn_bot.db right here
    import miniapp  # noqa: E402
finally:
    os.chdir(_cwd)

TABLES = ("users", "orders", "receipts", "plans", "settings", "tickets", "direct_orders", "notifications", "panels")


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kw):
        self.sent.append((chat_id, text))

    async def send_photo(self, chat_id, *a, **kw):
        self.sent.append((chat_id, "<photo>"))


class FakeApp:
    def __init__(self):
        self.bot = FakeBot()
        self.job_queue = None


class World:
    """What the fakes saw, plus knobs to make the panel fail."""

    def __init__(self):
        self.created = []
        self.delivered = []
        self.admin_notes = []
        self.panel_fails = False


@pytest.fixture
def world(monkeypatch):
    db = bot.db
    for t in TABLES:
        try:
            db.x(f"DELETE FROM {t}")
        except Exception:
            pass
    w = World()
    panel = {"id": 1, "name": "P1"}

    def create_service_on_panel(user_id, plan, service, username, panel_id=None, ipsec_password=None):
        if w.panel_fails:
            raise bot.PanelError("panel down")
        oid = db.create_order({
            "user_id": user_id, "panel_id": 1, "plan_id": plan["id"], "protocol": service, "username": username,
            "password": ipsec_password or "", "price": plan["price"], "volume_gb": plan["volume_gb"],
            "days": plan["days"], "expire_at": int(time.time()) + plan["days"] * 86400,
            "sub_url": f"https://sub.example/sub/{username}", "app_code": "",
        })
        w.created.append((user_id, username, plan["price"]))
        return db.get_order(oid), panel

    async def deliver_service(context, chat_id, order, p, quiet=False):
        w.delivered.append(order["username"])

    async def notify_admin(_bot, text, reply_markup=None):
        w.admin_notes.append(text)

    async def noop_async(*a, **k):
        return None

    class Client:
        def find_user(self, name):
            return None

    monkeypatch.setattr(bot, "create_service_on_panel", create_service_on_panel)
    monkeypatch.setattr(bot, "deliver_service", deliver_service)
    monkeypatch.setattr(bot, "notify_admin", notify_admin)
    monkeypatch.setattr(bot, "notify_group", lambda *a, **k: None)
    monkeypatch.setattr(bot, "close_receipt_for_others", noop_async)
    monkeypatch.setattr(bot, "send_receipt_to_admins", noop_async)
    monkeypatch.setattr(bot, "pick_panel", lambda service, prefer=None: panel)
    monkeypatch.setattr(bot, "panel_client", lambda p: Client())
    monkeypatch.setattr(bot, "ADMIN_ID", 1)
    miniapp.ns.update(vars(bot))
    app = FakeApp()
    miniapp._APP["app"] = app
    w.app = app
    yield w
    miniapp._APP.pop("app", None)


@pytest.fixture
def plan(world):
    pid = bot.db.add_plan(30, 30, 200_000, title="30 گیگ", service="xray")
    return bot.db.get_plan(pid)


def customer(uid=1001, balance=0):
    bot.db.ensure_user(uid, "cust", "Customer")
    if balance:
        bot.db.add_balance(uid, balance)
    return uid
