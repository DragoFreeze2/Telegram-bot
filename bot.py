#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Safe Telegram Tag-All bot (rewritten)
- Uses aiosqlite for async DB access
- Admin-only group creation/delete/list/view
- Safe mention handling with batching, cooldowns, RetryAfter handling
- Single router for text messages (handles name input vs mention commands)
"""

import os
import asyncio
import logging
import html
from typing import List, Set, Optional

import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, TelegramError
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ------------- CONFIG (via env) -------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN env var required")

DB_FILE = os.getenv("DB_FILE", "data.db")
MEMBER_PAGE = int(os.getenv("MEMBER_PAGE", "14"))
GROUPS_PAGE = int(os.getenv("GROUPS_PAGE", "14"))
MAX_MENTIONS_PER_MESSAGE = int(os.getenv("MAX_MENTIONS_PER_MESSAGE", "200"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))         # mentions per batch message
BATCH_DELAY = float(os.getenv("BATCH_DELAY", "1.2"))    # seconds between batches
CHAT_COOLDOWN = int(os.getenv("CHAT_COOLDOWN", "60"))   # seconds between /tagall usage per chat
GLOBAL_ADMINS = {int(x) for x in os.getenv("GLOBAL_ADMINS", "").split(",") if x.strip().isdigit()}

# ------------- Logging -------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ------------- Hard-coded MEMBERS (numeric IDs -> display name) -------------
# Replaced per your list (IDs and names)
MEMBERS = {
    "6395625150": "ابراهيم امجد",
    "2115600156": "زبير",
    "1448623963": "مهند",
    "2110875615": "يوسف عبدالمنعم",
    "1072403131": "عبدالرحمن اياد",
    "1495497154": "ياسر",
    "5568242014": "مصطفى",
    "1404572366": "ميلاد",
    "6346092493": "عبدالرحمن (روميو)",
    "2139449693": "عبدالله مشتاق",
    "5400293211": "عبدالله اسماعيل",
    "1262182930": "سراج",
    "5636797689": "حيدر",
    "632178074": "جمره",
    "940500731": "عبدالوهاب",
    "6330943571": "موسى",
    "1444352226": "عبيده",
    "7629805625": "سيف",
    "7080035408": "عبدالرحمن (A)",
    "911996257": "يمان",
}

# ------------- Runtime state -------------
db_lock = asyncio.Lock()
_last_tag_timestamp = {}  # chat_id -> last unix time

# ------------- Database helpers -------------
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS settings(
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS members(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    user_id INTEGER UNIQUE,
    display_name TEXT
);

CREATE TABLE IF NOT EXISTS groups(name TEXT PRIMARY KEY);

CREATE TABLE IF NOT EXISTS group_members(
    group_name TEXT,
    member_id INTEGER,
    PRIMARY KEY(group_name, member_id)
);
"""

async def init_db():
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.executescript(CREATE_SQL)
            await db.commit()
            # preload static members (numeric ids are provided as strings)
            for raw, disp in MEMBERS.items():
                try:
                    if str(raw).isdigit():
                        await db.execute(
                            "INSERT OR IGNORE INTO members(user_id,display_name) VALUES(?,?)",
                            (int(raw), disp)
                        )
                    else:
                        uname = raw if raw.startswith("@") else f"@{raw}"
                        await db.execute(
                            "INSERT OR IGNORE INTO members(username,display_name) VALUES(?,?)",
                            (uname, disp)
                        )
                except Exception:
                    logger.exception("Preload failed for %s", raw)
            await db.commit()

async def set_setting(key: str, val: str):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("REPLACE INTO settings(key,value) VALUES(?,?)", (key, val))
            await db.commit()

async def get_setting(key: str) -> Optional[str]:
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
            row = await cur.fetchone()
            return row[0] if row else None

async def list_members(offset: int, limit: int):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT COUNT(*) FROM members")
            total = (await cur.fetchone())[0]
            cur = await db.execute(
                "SELECT id,username,display_name FROM members ORDER BY display_name LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = await cur.fetchall()
            return rows, total

async def get_member(mid: int):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT id,username,user_id,display_name FROM members WHERE id=?", (mid,))
            r = await cur.fetchone()
            if not r:
                return None
            return {"id": r[0], "username": r[1], "user_id": r[2], "display": r[3]}

async def create_group(name: str, mids: List[int]):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (name,))
            for mid in mids:
                await db.execute(
                    "INSERT OR IGNORE INTO group_members(group_name,member_id) VALUES(?,?)",
                    (name, mid)
                )
            await db.commit()

async def list_groups(offset: int, limit: int):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT COUNT(*) FROM groups")
            total = (await cur.fetchone())[0]
            cur = await db.execute("SELECT name FROM groups ORDER BY name LIMIT ? OFFSET ?", (limit, offset))
            rows = await cur.fetchall()
            return [r[0] for r in rows], total

async def get_group_mids(name: str):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            cur = await db.execute("SELECT member_id FROM group_members WHERE group_name=?", (name,))
            rows = await cur.fetchall()
            return [r[0] for r in rows]

async def remove_group(name: str):
    async with db_lock:
        async with aiosqlite.connect(DB_FILE) as db:
            await db.execute("DELETE FROM group_members WHERE group_name=?", (name,))
            await db.execute("DELETE FROM groups WHERE name=?", (name,))
            await db.commit()

# ------------- Admin helpers -------------
async def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Returns True if user_id is in GLOBAL_ADMINS or is admin in the configured main group.
    """
    if user_id in GLOBAL_ADMINS:
        return True
    main = await get_setting("main_group_id")
    if not main:
        return False
    try:
        info = await context.bot.get_chat_member(int(main), user_id)
        return info.status in ("administrator", "creator")
    except TelegramError:
        logger.exception("Failed to check admin status for %s", user_id)
        return False

# ------------- Utility: safe send with RetryAfter handling -------------
async def safe_send_reply_html(msg_obj, text: str, disable_web_page_preview=True):
    """
    Sends a reply_html (or retries after RetryAfter). msg_obj is either Update.message or a Chat object wrapper that accepts reply_html.
    """
    try:
        return await msg_obj.reply_html(text, disable_web_page_preview=disable_web_page_preview)
    except RetryAfter as e:
        wait = e.retry_after + 1
        logger.info("RetryAfter encountered, sleeping %s seconds", wait)
        await asyncio.sleep(wait)
        return await safe_send_reply_html(msg_obj, text, disable_web_page_preview)
    except TelegramError:
        logger.exception("Failed to send message")
        # swallow to keep bot running
        return None

async def safe_send_chat_text(bot, chat_id: int, text: str):
    try:
        return await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
    except RetryAfter as e:
        wait = e.retry_after + 1
        logger.info("RetryAfter encountered for send_message, sleeping %s seconds", wait)
        await asyncio.sleep(wait)
        return await safe_send_chat_text(bot, chat_id, text)
    except TelegramError:
        logger.exception("Failed to send chat message")
        return None

# ------------- UI builders (member selection, groups) -------------
def build_member_kb(selected: Set[int], page: int, rows: List):
    """
    rows: list of (id, username, display_name)
    Returns InlineKeyboardMarkup
    """
    kb = []
    for mid, uname, disp in rows:
        sel = "✔ " if mid in selected else ""
        label = f"{sel}{disp} ({uname})" if uname else f"{sel}{disp}"
        kb.append([InlineKeyboardButton(label, callback_data=f"sel:{mid}:{page}")])
    nav = []
    # We cannot compute offsets/total here; the callback that calls this should add nav if needed
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("✅ Done", callback_data="finish")])
    return InlineKeyboardMarkup(kb)

# ------------- Handlers -------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running. Use /admin in DM (admins only).")

async def setmain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return await update.message.reply_text("Run /setmain inside the main group (group or supergroup).")
    await set_setting("main_group_id", str(chat.id))
    await update.message.reply_text("Main group saved!")

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id, context):
        return await update.message.reply_text("Admins only.")
    kb = [
        [InlineKeyboardButton("➕ Create Group", callback_data="create")],
        [InlineKeyboardButton("🗑 Delete Group", callback_data="delete")],
        [InlineKeyboardButton("📚 List Groups", callback_data="list:0")]
    ]
    await update.message.reply_text("Admin panel:", reply_markup=InlineKeyboardMarkup(kb))

# CALLBACK: create flow
async def cb_create(update, context):
    q = update.callback_query
    await q.answer()
    # only admins may create groups
    if not await is_admin(q.from_user.id, context):
        return await q.message.reply_text("Admins only.")
    # initialize selection data in user_data
    context.user_data["selected"] = set()
    context.user_data["page"] = 0
    # show first page members
    rows, total = await list_members(0, MEMBER_PAGE)
    kb = build_member_kb(context.user_data["selected"], 0, rows)
    # add nav buttons if needed
    nav = []
    if 0 > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"page:{0-1}"))
    if MEMBER_PAGE < total:
        nav.append(InlineKeyboardButton("➡", callback_data=f"page:{0+1}"))
    if nav:
        kb.inline_keyboard.insert(len(kb.inline_keyboard)-1, nav)  # before Done
    await q.message.reply_text("Select users:", reply_markup=kb)

async def cb_sel(update, context):
    q = update.callback_query
    await q.answer()
    try:
        _, mid_s, page_s = q.data.split(":")
        mid = int(mid_s); page = int(page_s)
    except Exception:
        return await q.message.reply_text("Invalid selection.")
    sel: set = context.user_data.get("selected", set())
    if mid in sel:
        sel.remove(mid)
    else:
        sel.add(mid)
    context.user_data["selected"] = sel
    context.user_data["page"] = page
    rows, total = await list_members(page * MEMBER_PAGE, MEMBER_PAGE)
    kb = build_member_kb(sel, page, rows)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"page:{page-1}"))
    if (page+1) * MEMBER_PAGE < total:
        nav.append(InlineKeyboardButton("➡", callback_data=f"page:{page+1}"))
    if nav:
        kb.inline_keyboard.insert(len(kb.inline_keyboard)-1, nav)
    try:
        await q.message.edit_text("Select users:", reply_markup=kb)
    except TelegramError:
        # message might not be editable; fallback to sending a fresh message
        await q.message.reply_text("Select users:", reply_markup=kb)

async def cb_page(update, context):
    q = update.callback_query
    await q.answer()
    try:
        _, page_s = q.data.split(":")
        page = int(page_s)
    except Exception:
        return await q.message.reply_text("Invalid page.")
    context.user_data["page"] = page
    sel = context.user_data.get("selected", set())
    rows, total = await list_members(page * MEMBER_PAGE, MEMBER_PAGE)
    kb = build_member_kb(sel, page, rows)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"page:{page-1}"))
    if (page+1) * MEMBER_PAGE < total:
        nav.append(InlineKeyboardButton("➡", callback_data=f"page:{page+1}"))
    if nav:
        kb.inline_keyboard.insert(len(kb.inline_keyboard)-1, nav)
    try:
        await q.message.edit_text("Select users:", reply_markup=kb)
    except TelegramError:
        await q.message.reply_text("Select users:", reply_markup=kb)

async def cb_finish(update, context):
    q = update.callback_query
    await q.answer()
    sel = context.user_data.get("selected", set())
    if not sel:
        return await q.message.reply_text("Empty selection.")
    context.user_data["final_sel"] = list(sel)
    context.user_data["ask_name"] = True
    await q.message.reply_text("Send group name (no spaces, lower-case recommended).")

async def msg_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # only run when in create flow (ask_name)
    if not context.user_data.get("ask_name"):
        return
    # only admins allowed to finalize group create
    if not await is_admin(update.effective_user.id, context):
        context.user_data.clear()
        return await update.message.reply_text("Admins only.")
    name = update.message.text.strip().lower().replace(" ", "_")
    # simple sane validation
    if not name.isalnum() and "_" not in name:
        await update.message.reply_text("Invalid group name. Use alphanumeric and underscores only.")
        return
    mids = context.user_data.get("final_sel", [])
    if not mids:
        context.user_data.clear()
        return await update.message.reply_text("No members selected.")
    await create_group(name, mids)
    context.user_data.clear()
    await update.message.reply_text(f"Created group: {name}")

# CALLBACK: delete group
async def cb_delete(update, context):
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id, context):
        return await q.message.reply_text("Admins only.")
    groups, _ = await list_groups(0, 999)
    if not groups:
        return await q.message.reply_text("No groups.")
    kb = [[InlineKeyboardButton(g, callback_data=f"del:{g}")] for g in groups]
    await q.message.reply_text("Delete which group?", reply_markup=InlineKeyboardMarkup(kb))

async def cb_delpick(update, context):
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id, context):
        return await q.message.reply_text("Admins only.")
    try:
        _, g = q.data.split(":", 1)
    except Exception:
        return await q.message.reply_text("Invalid selection.")
    await remove_group(g)
    await q.message.reply_text(f"Deleted {g}")

# CALLBACK: list groups
async def cb_list(update, context):
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id, context):
        return await q.message.reply_text("Admins only.")
    try:
        _, page_s = q.data.split(":")
        page = int(page_s)
    except Exception:
        page = 0
    groups, total = await list_groups(page * GROUPS_PAGE, GROUPS_PAGE)
    kb = []
    for g in groups:
        mids = await get_group_mids(g)
        kb.append([InlineKeyboardButton(f"{g} ({len(mids)})", callback_data=f"view:{g}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅", callback_data=f"list:{page-1}"))
    if (page+1) * GROUPS_PAGE < total:
        nav.append(InlineKeyboardButton("➡", callback_data=f"list:{page+1}"))
    if nav:
        kb.append(nav)
    await q.message.reply_text("Groups:", reply_markup=InlineKeyboardMarkup(kb))

async def cb_view(update, context):
    q = update.callback_query
    await q.answer()
    if not await is_admin(q.from_user.id, context):
        return await q.message.reply_text("Admins only.")
    try:
        _, g = q.data.split(":", 1)
    except Exception:
        return await q.message.reply_text("Invalid selection.")
    mids = await get_group_mids(g)
    lines = []
    for mid in mids:
        rec = await get_member(mid)
        if not rec:
            continue
        if rec["username"]:
            lines.append(f"{rec['display']} ({rec['username']})")
        else:
            # safe escape display
            safe = html.escape(rec["display"] or "")
            lines.append(f"{safe}")
    await q.message.reply_text("\n".join(lines) or "Empty.")

# ------------- Mention listener + router -------------
async def mention_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    # only react to group messages (safe)
    chat = update.effective_chat
    if chat.type not in ("group", "supergroup"):
        return

    text = update.message.text.lower()
    tokens = text.split()

    # ensure only admins can trigger mentions (prevents abuse)
    if not await is_admin(update.effective_user.id, context):
        return

    # process tokens, stop after first handled token to avoid multi-trigger spam
    for t in tokens:
        if not (t.startswith("@") or t.startswith("#")):
            continue
        key = t[1:].strip().lower()
        if not key:
            continue

        # @all or @everyone
        if key in ("all", "everyone"):
            # fetch all members (careful: can be many)
            rows = []
            async with db_lock:
                async with aiosqlite.connect(DB_FILE) as db:
                    cur = await db.execute("SELECT username,user_id,display_name FROM members")
                    rows = await cur.fetchall()
            mentions = []
            for u, uid, d in rows:
                if u:
                    mentions.append(u)
                elif uid:
                    safe = html.escape(d or "")
                    mentions.append(f'<a href="tg://user?id={uid}">{safe}</a>')
            # send in batches
            for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                chunk = mentions[i:i + MAX_MENTIONS_PER_MESSAGE]
                await safe_send_reply_html(update.message, " ".join(chunk))
                await asyncio.sleep(BATCH_DELAY)
            return

        # @group
        # ensure group exists
        async with db_lock:
            async with aiosqlite.connect(DB_FILE) as db:
                cur = await db.execute("SELECT name FROM groups WHERE name=?", (key,))
                exists = await cur.fetchone()
        if exists:
            mids = await get_group_mids(key)
            mentions = []
            for mid in mids:
                r = await get_member(mid)
                if not r:
                    continue
                if r["username"]:
                    mentions.append(r["username"])
                else:
                    safe = html.escape(r["display"] or "")
                    mentions.append(f'<a href="tg://user?id={r["user_id"]}">{safe}</a>')
            for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                chunk = mentions[i:i + MAX_MENTIONS_PER_MESSAGE]
                await safe_send_reply_html(update.message, " ".join(chunk))
                await asyncio.sleep(BATCH_DELAY)
            return

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Single entry point for text messages: either finishing a name input (msg_name)
    or passing to mention_listener
    """
    # msg_name must run first if user is in create flow
    if context.user_data.get("ask_name"):
        return await msg_name(update, context)
    # otherwise normal mention listener
    return await mention_listener(update, context)

# ------------- App builder -------------
def build_app():
    app = ApplicationBuilder().token(TOKEN).build()

    # simple commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setmain", setmain))
    app.add_handler(CommandHandler("admin", admin_panel))

    # callbackquery handlers
    app.add_handler(CallbackQueryHandler(cb_create, pattern="^create$"))
    app.add_handler(CallbackQueryHandler(cb_delete, pattern="^delete$"))
    app.add_handler(CallbackQueryHandler(cb_list, pattern="^list:"))
    app.add_handler(CallbackQueryHandler(cb_sel, pattern="^sel:"))
    app.add_handler(CallbackQueryHandler(cb_page, pattern="^page:"))
    app.add_handler(CallbackQueryHandler(cb_finish, pattern="^finish$"))
    app.add_handler(CallbackQueryHandler(cb_delpick, pattern="^del:"))
    app.add_handler(CallbackQueryHandler(cb_view, pattern="^view:"))

    # router for all text messages (handles msg_name + mention)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, router))

    return app

# ------------- Main -------------
async def main():
    await init_db()
    app = build_app()
    logger.info("Starting bot")
    # run polling
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    # keep running until killed
    await app.updater.idle()
    await app.stop()
    await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Stopping bot")