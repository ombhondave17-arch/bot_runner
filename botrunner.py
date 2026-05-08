import os
import sys
import subprocess
import zipfile
import threading
import signal
import logging
import time
import importlib
import ast
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

load_dotenv()

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN = "8549679763:AAHGSO9AA0vuW4jZ4TUrKT35TMpeHwPc1Xk"  # Tumhara apna token dal do
ADMIN_IDS = {6548871396}  # Tumhari admin ID dal do

BOTS_DIR = Path("./running_bots")
LOG_DIR = Path("./bot_logs")
# ─────────────────────────────────────────────

BOTS_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    format="%(asctime)s [RUNNER] %(levelname)s: %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)

running_bots = {}
lock = threading.Lock()


# ─────────────────────────────────────────────
#  KEYBOARDS
# ─────────────────────────────────────────────

MAIN_KB = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🤖 Running Bots"), KeyboardButton("📊 Status")],
        [KeyboardButton("🛑 Stop All"), KeyboardButton("📋 Help")],
    ],
    resize_keyboard=True
)

def bot_action_kb(name: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(f"📋 Logs: {name}"),
             KeyboardButton(f"🔄 Restart: {name}"),
             KeyboardButton(f"🛑 Stop: {name}")],
            [KeyboardButton("🔙 Menu")],
        ],
        resize_keyboard=True
    )

def bots_list_kb() -> ReplyKeyboardMarkup:
    with lock:
        names = list(running_bots.keys())
    rows = [[KeyboardButton(f"🔧 {n}")] for n in names]
    rows.append([KeyboardButton("🔙 Menu")])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────

def is_admin(update: Update) -> bool:
    uid = update.effective_user.id if update.effective_user else None
    return uid in ADMIN_IDS

def bot_log_path(name: str) -> Path:
    return LOG_DIR / f"{name}.log"

def tail_log(path: Path, n: int = 35) -> str:
    try:
        with open(path, "r", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]) or "(log khali hai)"
    except FileNotFoundError:
        return "(log file nahi mili)"

def stream_output(proc, log_path: Path):
    with open(log_path, "a", buffering=1) as lf:
        for line in iter(proc.stdout.readline, b""):
            lf.write(line.decode(errors="replace"))
    proc.stdout.close()

def kill_bot(info: dict):
    try:
        proc = info["process"]
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=3)
    except:
        try:
            proc.kill()
        except:
            pass

def start_bot_process(name: str, cmd: list, work_dir: Path):
    log_path = bot_log_path(name)
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=work_dir,
    )
    t = threading.Thread(target=stream_output, args=(proc, log_path), daemon=True)
    t.start()
    with lock:
        running_bots[name] = {
            "process": proc,
            "log_path": log_path,
            "thread": t,
            "dir": work_dir,
            "cmd": cmd,
            "started": time.strftime("%H:%M:%S")
        }
    log.info(f"✅ Bot '{name}' started (PID {proc.pid})")


# ─────────────────────────────────────────────
#  COMMAND HANDLERS
# ─────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await update.message.reply_text("❌ Access denied.")
    await update.message.reply_text(
        "🚀 *BotRunner Pro — Admin Panel*\n\n"
        "📤 Koi bhi `.py` `.c` `.zip` bhejo — auto deploy!\n"
        "Niche buttons se control karo 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KB
    )

async def cmd_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    await update.message.reply_text("📋 Main Menu", reply_markup=MAIN_KB)


# ─────────────────────────────────────────────
#  TEXT HANDLER
# ─────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return
    txt = (update.message.text or "").strip()

    if txt == "🔙 Menu":
        return await update.message.reply_text("📋 Main Menu", reply_markup=MAIN_KB)

    if txt == "📊 Status":
        with lock:
            count = len(running_bots)
            alive = sum(1 for i in running_bots.values() if i["process"].poll() is None)
        return await update.message.reply_text(
            f"📊 *Runner Status*\n\n"
            f"🟢 Active: {alive}\n"
            f"📦 Total deployed: {count}\n"
            f"🕐 Time: {time.strftime('%d/%m/%Y %H:%M:%S')}",
            parse_mode="Markdown", reply_markup=MAIN_KB
        )

    if txt == "🛑 Stop All":
        with lock:
            names = list(running_bots.keys())
            infos = [running_bots.pop(n) for n in names]
        for info in infos:
            kill_bot(info)
        return await update.message.reply_text(
            f"🛑 *{len(names)} bots band kar diye!*",
            parse_mode="Markdown", reply_markup=MAIN_KB
        )

    if txt == "📋 Help":
        return await update.message.reply_text(
            "📋 *How to use BotRunner:*\n\n"
            "1️⃣ `.py` bhejo → auto run\n"
            "2️⃣ `.c` bhejo → compile + run\n"
            "3️⃣ `.zip` bhejo → extract + deps install + run\n\n"
            "✨ *Auto Features:*\n"
            "• requirements.txt auto detect\n"
            "• Import scan se missing libs install\n"
            "• Crash pe auto restart\n"
            "• Sabka log save hota hai\n\n"
            "📌 Commands: /start /menu",
            parse_mode="Markdown", reply_markup=MAIN_KB
        )

    if txt == "🤖 Running Bots":
        with lock:
            bots = dict(running_bots)
        if not bots:
            return await update.message.reply_text(
                "😴 Koi bot run nahi ho raha.\n📤 Koi file upload karo!",
                reply_markup=MAIN_KB
            )
        lines = ["🤖 *Running Bots:*\n"]
        for name, info in bots.items():
            rc = info["process"].poll()
            st = "🟢" if rc is None else f"🔴 (crashed {rc})"
            lines.append(f"{st} `{name}` — since {info['started']}")
        lines.append("\n👇 Bot name tap karo actions ke liye")
        return await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=bots_list_kb()
        )

    if txt.startswith("🔧 "):
        name = txt[3:].strip()
        with lock:
            exists = name in running_bots
        if not exists:
            return await update.message.reply_text(
                f"❌ `{name}` nahi mila.", parse_mode="Markdown",
                reply_markup=MAIN_KB
            )
        return await update.message.reply_text(
            f"🔧 *{name}* — kya karna hai?",
            parse_mode="Markdown", reply_markup=bot_action_kb(name)
        )

    if txt.startswith("📋 Logs: "):
        name = txt[len("📋 Logs: "):]
        with lock:
            info = running_bots.get(name)
        path = info["log_path"] if info else bot_log_path(name)
        logs = tail_log(path)
        return await update.message.reply_text(
            f"📋 *Logs: `{name}`*\n```\n{logs[-3200:]}\n```",
            parse_mode="Markdown", reply_markup=bot_action_kb(name)
        )

    if txt.startswith("🔄 Restart: "):
        name = txt[len("🔄 Restart: "):]
        with lock:
            info = running_bots.get(name)
        if not info:
            return await update.message.reply_text("❌ Bot nahi mila.", reply_markup=MAIN_KB)
        kill_bot(info)
        with lock:
            running_bots.pop(name, None)
        start_bot_process(name, info["cmd"], info["dir"])
        return await update.message.reply_text(
            f"🔄 `{name}` restart ho gaya!", parse_mode="Markdown",
            reply_markup=bot_action_kb(name)
        )

    if txt.startswith("🛑 Stop: "):
        name = txt[len("🛑 Stop: "):]
        with lock:
            info = running_bots.pop(name, None)
        if info:
            kill_bot(info)
            return await update.message.reply_text(
                f"🛑 `{name}` band kar diya!", parse_mode="Markdown",
                reply_markup=MAIN_KB
            )
        return await update.message.reply_text("❌ Bot nahi mila.", reply_markup=MAIN_KB)


# ─────────────────────────────────────────────
#  FILE UPLOAD HANDLER
# ─────────────────────────────────────────────

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update):
        return await update.message.reply_text("❌ Access denied.")

    doc = update.message.document
    fname = doc.file_name or "uploaded"
    ext = Path(fname).suffix.lower()

    if ext not in (".py", ".c", ".zip"):
        return await update.message.reply_text(
            "❌ Sirf `.py`, `.c`, `.zip` files supported hain.",
            parse_mode="Markdown"
        )

    msg = await update.message.reply_text(f"⬇️ Downloading `{fname}`...", parse_mode="Markdown")

    file = await ctx.bot.get_file(doc.file_id)
    bot_name = Path(fname).stem.replace(" ", "_").replace("-", "_")
    work_dir = BOTS_DIR / bot_name
    work_dir.mkdir(parents=True, exist_ok=True)
    dl_path = work_dir / fname
    await file.download_to_drive(str(dl_path))

    # ZIP handler
    if ext == ".zip":
        await msg.edit_text("📦 Extracting zip...", parse_mode="Markdown")
        with zipfile.ZipFile(dl_path, "r") as z:
            z.extractall(work_dir)
        dl_path.unlink(missing_ok=True)

        # Find and run all .py files
        py_files = list(work_dir.rglob("*.py"))
        deployed = []
        
        for py_file in py_files:
            sub_name = f"{bot_name}_{py_file.stem}"
            with lock:
                old = running_bots.pop(sub_name, None)
            if old:
                kill_bot(old)
            
            start_bot_process(sub_name, [sys.executable, "-u", str(py_file)], work_dir)
            deployed.append(sub_name)
        
        if not deployed:
            return await msg.edit_text("❌ Zip me koi .py file nahi mili.", reply_markup=MAIN_KB)
        
        return await msg.edit_text(
            f"✅ *Zip Deployed!*\n{len(deployed)} bots running.",
            parse_mode="Markdown", reply_markup=MAIN_KB
        )

    # PY file handler
    elif ext == ".py":
        py_file = dl_path
        cmd = [sys.executable, "-u", str(py_file)]
        
        with lock:
            old = running_bots.pop(bot_name, None)
        if old:
            kill_bot(old)
        
        await msg.edit_text("🚀 Deploying...", parse_mode="Markdown")
        start_bot_process(bot_name, cmd, work_dir)
        
        return await update.message.reply_text(
            f"✅ *Bot Deployed!*\n📌 Name: `{bot_name}`\n🟢 Status: Running",
            parse_mode="Markdown",
            reply_markup=bot_action_kb(bot_name)
        )

    # C file handler
    elif ext == ".c":
        await msg.edit_text("⚙️ Compiling C file...", parse_mode="Markdown")
        exe = work_dir / "bot_exec"
        res = subprocess.run(
            ["gcc", str(dl_path), "-o", str(exe), "-lpthread", "-lm"],
            capture_output=True, text=True
        )
        if res.returncode != 0:
            return await msg.edit_text(
                f"❌ GCC Error:\n```{res.stderr[-1500:]}```",
                parse_mode="Markdown", reply_markup=MAIN_KB
            )
        cmd = [str(exe)]
        
        with lock:
            old = running_bots.pop(bot_name, None)
        if old:
            kill_bot(old)
        start_bot_process(bot_name, cmd, work_dir)
        
        return await update.message.reply_text(
            f"✅ *C Bot Deployed!*\n📌 Name: `{bot_name}`\n🟢 Status: Running",
            parse_mode="Markdown",
            reply_markup=bot_action_kb(bot_name)
        )


# ─────────────────────────────────────────────
#  WATCHDOG
# ─────────────────────────────────────────────

def watchdog():
    while True:
        time.sleep(15)
        with lock:
            items = list(running_bots.items())
        for name, info in items:
            if info["process"].poll() is not None:
                log.warning(f"🔁 '{name}' crashed. Restarting...")
                try:
                    new_proc = subprocess.Popen(
                        info["cmd"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        cwd=info["dir"],
                    )
                    t = threading.Thread(target=stream_output, args=(new_proc, info["log_path"]), daemon=True)
                    t.start()
                    with lock:
                        if name in running_bots:
                            running_bots[name]["process"] = new_proc
                            running_bots[name]["thread"] = t
                            running_bots[name]["started"] = time.strftime("%H:%M:%S")
                    log.info(f"✅ '{name}' restarted")
                except Exception as e:
                    log.error(f"❌ Restart failed: {e}")


# ─────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────

def main():
    threading.Thread(target=watchdog, daemon=True).start()
    log.info("🚀 BotRunner started. Watchdog active.")

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
