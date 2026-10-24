"""ربات تلگرام شخصی برای گفتگو با Codex CLI روی همین سرور — فقط برای OWNER_ID."""
import asyncio
import json
import logging
import os
import re
import tempfile
import time
from pathlib import Path

from telegram import InlineKeyboardButton as Btn, InlineKeyboardMarkup as Kb, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TG_TOKEN"]
OWNER_ID = int(os.environ["OWNER_ID"])
CODEX = os.environ.get("CODEX_BIN", "codex")
WORKDIR = os.environ.get("WORKDIR", "/root")
MODELS = ['gpt-6.1-sol', 'gpt-6-astra', 'gpt-6-sol', 'gpt-6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra', 'gpt-5.6-luna']
STATE = Path(__file__).with_name("state.json")
INBOX = Path(__file__).with_name("inbox")
INBOX.mkdir(exist_ok=True)
TIMEOUT = 30 * 60
SEND_HINT = ("اگر کاربر عکس یا فایلی خواست، مسیر کامل فایل را در یک خط جدا به شکل "
             "`SEND: /مسیر/کامل/فایل` بنویس. سرور پنل Tifusi با `ssh panel` در دسترس است (Docker: tifusi-panel, tifusi-dashboard, tifusi-node, tifusi-mysql). "
             "همیشه فارسی و کوتاه جواب بده.")

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("codex_tg")
lock = asyncio.Lock()
running = {"proc": None}


def load():
    try:
        st = json.loads(STATE.read_text())
    except (OSError, ValueError):
        st = {}
    st.setdefault("sessions", {})
    st.setdefault("current", None)
    st.setdefault("model", None)
    return st


def save(st):
    STATE.write_text(json.dumps(st, ensure_ascii=False, indent=1))


def main_kb():
    return Kb([[Btn("🆕 جلسه‌ی جدید", callback_data="new"), Btn("📂 جلسه‌ها", callback_data="list")],
               [Btn("🤖 مدل", callback_data="models"), Btn("⛔️ توقف", callback_data="stop")]])


def models_kb(st):
    rows = [[Btn(("✅ " if m == st["model"] else "") + m, callback_data=f"model:{m}")] for m in MODELS]
    rows.append([Btn(("✅ " if not st["model"] else "") + "پیش‌فرض Codex", callback_data="model:")])
    return Kb(rows)


def sessions_kb(st):
    rows = []
    for sid, s in sorted(st["sessions"].items(), key=lambda kv: kv[1]["ts"], reverse=True)[:15]:
        rows.append([Btn(("🟢 " if sid == st["current"] else "") + s["title"][:30], callback_data=f"open:{sid}"),
                     Btn("🗑", callback_data=f"del:{sid}")])
    rows.append([Btn("🆕 جلسه‌ی جدید", callback_data="new")])
    return Kb(rows)


def owner(update):
    return update.effective_user and update.effective_user.id == OWNER_ID


def thread_id_from(events):
    for ev in events:
        if isinstance(ev, dict) and ev.get("type") == "thread.started" and ev.get("thread_id"):
            return ev["thread_id"]
    return None


def error_from(events):
    """آخرین پیام خطای Codex از رویدادها؛ برای محدودیت مصرف متن فارسی کوتاه برمی‌گرداند."""
    msg = ""
    for ev in events:
        if isinstance(ev, dict) and ev.get("type") in ("error", "turn.failed"):
            msg = ev.get("message") or (ev.get("error") or {}).get("message") or msg
    if "usage limit" in msg:
        m = re.search(r"try again at ([^.]+)", msg)
        return "⏳ سقف مصرف اشتراک ChatGPT پر شده." + (f" دوباره بعد از {m.group(1)} امتحان کن." if m else "")
    return msg[:500]


async def ask_codex(prompt, sid, model=None, on_progress=None):
    """codex exec را اجرا می‌کند و (متن جواب، شناسه‌ی جلسه) برمی‌گرداند."""
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
        out_path = tmp.name
    base = ["--json", "-o", out_path, "--skip-git-repo-check", "-c", 'sandbox_mode="danger-full-access"',
            "-c", "sandbox_workspace_write.network_access=true"]
    if model:
        base += ["-c", f'model="{model}"']
    full = f"{SEND_HINT}\n\n{prompt}"
    cmd = [CODEX, "exec", "resume", *base, sid, full] if sid else [CODEX, "exec", *base, full]
    proc = await asyncio.create_subprocess_exec(*cmd, cwd=WORKDIR, stdin=asyncio.subprocess.DEVNULL,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    running["proc"] = proc
    events, output = [], []

    async def consume():
        # Drain continuously: command output may contain long JSON records.
        buffer = b""
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            buffer += chunk
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                output.append(line[-2000:])
                try:
                    event = json.loads(line)
                except (ValueError, UnicodeDecodeError):
                    continue
                events.append(event)
                item = event.get("item") or {}
                if (on_progress and event.get("type") == "item.completed"
                        and item.get("type") == "agent_message"):
                    try:
                        await on_progress(item.get("text") or "")
                    except Exception:
                        log.warning("Progress delivery failed")
        await proc.wait()

    try:
        await asyncio.wait_for(consume(), TIMEOUT)
    except asyncio.TimeoutError:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        Path(out_path).unlink(missing_ok=True)
        return "⏱ بیش از ۳۰ دقیقه طول کشید و متوقف شد.", sid
    finally:
        running["proc"] = None
    if proc.returncode and proc.returncode < 0:
        Path(out_path).unlink(missing_ok=True)
        return "⛔️ متوقف شد.", sid
    out = b"\n".join(output[-10:])
    sid = thread_id_from(events) or sid
    try:
        text = Path(out_path).read_text().strip()
    finally:
        Path(out_path).unlink(missing_ok=True)
    if not text:
        text = "❌ جوابی نیامد:\n" + (error_from(events) or out.decode(errors="replace")[-500:])
    return text, sid


async def keep_typing(chat):
    while True:
        await chat.send_action(ChatAction.TYPING)
        await asyncio.sleep(4)


async def run_prompt(update: Update, prompt: str):
    if lock.locked():
        await update.message.reply_text("⏳ هنوز روی پیام قبلی کار می‌کنم…", reply_markup=main_kb())
    async with lock:
        st = load()
        started = st["current"]
        status = await update.message.reply_text(f"⏳ Codex ({st['model'] or 'پیش‌فرض'}) در حال کار…")
        typing = asyncio.create_task(keep_typing(update.effective_chat))
        t0 = time.time()
        last_progress = [0.0, ""]

        async def show_progress(message):
            # Only assistant messages; never expose reasoning, commands or tool output.
            message = re.sub(r"^SEND: .*?$", "", message, flags=re.M).strip()
            if not message or message == last_progress[1]:
                return
            if time.monotonic() - last_progress[0] < 3:
                return
            await status.edit_text("⏳ " + message[:3500])
            last_progress[:] = [time.monotonic(), message]

        try:
            text, sid = await ask_codex(prompt, started, st["model"], show_progress)
        finally:
            typing.cancel()
        st = load()
        if sid:
            entry = st["sessions"].get(sid) or {"title": prompt.strip().replace("\n", " ")[:40]}
            entry["ts"] = time.time()
            st["sessions"][sid] = entry
            st["current"] = sid
            save(st)
        try:
            await status.delete()
        except Exception:
            pass
        files = re.findall(r"^SEND: (\S+)$", text, re.M)
        text = re.sub(r"^SEND: \S+\n?", "", text, flags=re.M).strip() or "(بدون متن)"
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for i, chunk in enumerate(chunks):
            await update.message.reply_text(chunk + (f"\n\n— Codex · {time.time() - t0:.0f} ثانیه" if i == len(chunks) - 1 else ""))
        for f in files:
            p = Path(f)
            if p.is_file() and p.stat().st_size <= 45 * 1024 * 1024:
                with p.open("rb") as fh:
                    if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                        await update.message.reply_photo(fh, caption=p.name)
                    else:
                        await update.message.reply_document(fh, caption=p.name)
            else:
                await update.message.reply_text(f"❌ فایل پیدا نشد یا خیلی بزرگه: {f}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if owner(update):
        await run_prompt(update, update.message.text)


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not owner(update):
        return
    photo = update.message.photo[-1]
    path = INBOX / f"{photo.file_unique_id}.jpg"
    await (await photo.get_file()).download_to_drive(path)
    caption = update.message.caption or "این عکس را ببین و توضیح بده."
    await run_prompt(update, f"{caption}\n\n(عکس روی سرور ذخیره شد: {path})")


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if owner(update):
        await update.message.reply_text("🤖 Codex روی سرور\n\nپیامت را بفرست.", reply_markup=main_kb())


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not owner(update):
        await q.answer()
        return
    st = load()
    action, _, arg = q.data.partition(":")
    if action == "new":
        st["current"] = None
        save(st)
        await q.answer("🆕 جلسه‌ی جدید")
        await q.message.reply_text("🆕 جلسه‌ی جدید. پیام اول را بفرست.")
    elif action == "list":
        await q.answer()
        await q.message.reply_text("📂 جلسه‌ها" if st["sessions"] else "📂 هنوز جلسه‌ای نیست.", reply_markup=sessions_kb(st))
    elif action == "open" and arg in st["sessions"]:
        st["current"] = arg
        save(st)
        await q.answer("✅ جلسه باز شد")
    elif action == "del" and arg in st["sessions"]:
        st["sessions"].pop(arg)
        if st["current"] == arg:
            st["current"] = None
        save(st)
        await q.answer("🗑 حذف شد")
        await q.edit_message_reply_markup(sessions_kb(st))
    elif action == "models":
        await q.answer()
        await q.message.reply_text("🤖 مدل را انتخاب کن", reply_markup=models_kb(st))
    elif action == "model" and (not arg or arg in MODELS):
        st["model"] = arg or None
        save(st)
        await q.answer(f"✅ {arg or 'پیش‌فرض'}")
        await q.edit_message_reply_markup(models_kb(st))
    elif action == "stop":
        proc = running["proc"]
        if proc and proc.returncode is None:
            proc.terminate()
            await q.answer("⛔️ متوقف شد")
        else:
            await q.answer("کاری در حال اجرا نیست")
    else:
        await q.answer("❌ پیدا نشد")


def main():
    app = Application.builder().token(TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "menu"], on_start))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO & ~filters.COMMAND, on_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("codex-tg started")
    app.run_polling()


if __name__ == "__main__":
    main()
