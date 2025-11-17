#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Optimized Tag-All Bot (Railway-ready)
- TOKEN is read from environment variable "TOKEN"
- Lightweight, optimized callback handling
- Admin DM-only panel: Create / Rename / Delete / List groups
- Inline paginated member picker with ✔ marks
- Tagging in main group: @group, #group, @all, #all
- Preloaded members come from MEMBERS mapping (username or numeric id)
- Persistent SQLite storage (data.db)
"""

import os
import nest_asyncio
nest_asyncio.apply()

import asyncio
import logging
import sqlite3
from typing import List, Optional, Dict, Set, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ---------------- CONFIG ----------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set. Add TOKEN to Railway variables or export it locally.")

DB_FILE = "data.db"
MEMBER_PAGE = 14
GROUPS_PAGE = 14
MAX_MENTIONS_PER_MESSAGE = 200

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------- MEMBERS (provided) ----------------
# identifier -> display name. identifier is either username (without @) or numeric id as string.
MEMBERS = {
    "Y_35a": "ياسر",
    "Fbbhzoot": "يوسف عبدالمنعم",
    "llN5lx": "عبدالقادر",
    "xxaraaas": "اراس",
    "6395625150": "ابراهيم امجد",
    "2115600156": "زبير",
    "x320p": "عبدالرحمن (روميو)",
    "hhmr39": "مصطفى",
    "ki_4t": "عبدالله مشتاق",
    "abdulah_aljj": "عبدالله اسماعيل",
    "yo_glg": "يوسف ازهر",
    "karam199779": "كرم",
    "gli_894": "عبدالله زياد",
    "MLD38": "ميلاد",
    "s1_6ra": "سراج",
    "dmxv1": "حيدر",
    "jy5u_1": "جمرة",
    "i7obe": "عبدالوهاب",
    "yz_5m": "عبدالرحمن اياد",
    "MY7MY74477": "موسى (main)",
    "OBA3IDA": "عبيده",
    "saif_sa_cr7": "سيف",
    "mp8v1": "عبدالرحمن (A)",
    "jgfw1": "يمان",
    "c9z67": "احمد ازهر",
    "hasonppppp": "الحسن",
    "a_8lmf": "احمد عامر",
    "X_NN_R": "محمد",
    "My7my7447": "موسى (alt)",
    "dragon_freeze2": "مهند"
}

# ---------------- DB ----------------
_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
_cur = _conn.cursor()

_cur.executescript("""
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    user_id INTEGER UNIQUE,
    display_name TEXT
);
CREATE TABLE IF NOT EXISTS groups (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS group_members (
    group_name TEXT,
    member_id INTEGER,
    PRIMARY KEY(group_name, member_id)
);
""")
_conn.commit()

def preload_members():
    for raw, disp in MEMBERS.items():
        try:
            if raw.isdigit():
                _cur.execute("INSERT OR IGNORE INTO members(user_id, display_name) VALUES(?,?)", (int(raw), disp))
            else:
                uname = raw if raw.startswith("@") else "@" + raw
                _cur.execute("INSERT OR IGNORE INTO members(username, display_name) VALUES(?,?)", (uname, disp))
        except Exception:
            logger.exception("preload failed for %s", raw)
    _conn.commit()

preload_members()

# ---------------- helpers ----------------
def set_setting(k: str, v: str):
    _cur.execute("REPLACE INTO settings(key,value) VALUES(?,?)", (k, v))
    _conn.commit()

def get_setting(k: str) -> Optional[str]:
    r = _cur.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
    return r[0] if r else None

def list_members(offset: int = 0, limit: int = MEMBER_PAGE):
    _cur.execute("SELECT COUNT(*) FROM members")
    total = _cur.fetchone()[0]
    _cur.execute("SELECT id, username, display_name FROM members ORDER BY display_name LIMIT ? OFFSET ?", (limit, offset))
    return _cur.fetchall(), total

def get_member(mid: int) -> Optional[Dict[str, Any]]:
    r = _cur.execute("SELECT id, username, user_id, display_name FROM members WHERE id=?", (mid,)).fetchone()
    if not r: return None
    return {"id": r[0], "username": r[1], "user_id": r[2], "display": r[3]}

def create_group(name: str, mids: List[int]):
    _cur.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)", (name,))
    for m in mids:
        _cur.execute("INSERT OR IGNORE INTO group_members(group_name, member_id) VALUES(?,?)", (name, m))
    _conn.commit()

def get_groups(offset: int = 0, limit: int = GROUPS_PAGE):
    _cur.execute("SELECT COUNT(*) FROM groups")
    total = _cur.fetchone()[0]
    _cur.execute("SELECT name FROM groups ORDER BY name LIMIT ? OFFSET ?", (limit, offset))
    return [r[0] for r in _cur.fetchall()], total

def get_group_mids(name: str) -> List[int]:
    _cur.execute("SELECT member_id FROM group_members WHERE group_name=? ORDER BY member_id", (name,))
    return [r[0] for r in _cur.fetchall()]

def remove_group(name: str):
    _cur.execute("DELETE FROM group_members WHERE group_name=?", (name,))
    _cur.execute("DELETE FROM groups WHERE name=?", (name,))
    _conn.commit()

def rename_group(old: str, new: str):
    _cur.execute("UPDATE groups SET name=? WHERE name=?", (new, old))
    _cur.execute("UPDATE group_members SET group_name=? WHERE group_name=?", (new, old))
    _conn.commit()

# ---------------- utils ----------------
async def is_admin(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    main = get_setting("main_group_id")
    if not main:
        return False
    try:
        m = await context.bot.get_chat_member(int(main), user_id)
        return m.status in ("administrator", "creator")
    except Exception:
        return False

# ---------------- bot handlers ----------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Tag-All Bot — DM /admin to manage groups.")

async def setmain_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ("group","supergroup"):
        return await update.message.reply_text("Run /setmain inside the main group.")
    set_setting("main_group_id", str(chat.id))
    await update.message.reply_text("Main group set.")

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not await is_admin(user.id, context):
        return await update.message.reply_text("Admins only.")
    kb = [
        [InlineKeyboardButton("➕ Create Group", callback_data="adm_create")],
        [InlineKeyboardButton("✏️ Rename Group", callback_data="adm_rename")],
        [InlineKeyboardButton("🗑 Delete Group", callback_data="adm_delete")],
        [InlineKeyboardButton("📚 List Groups", callback_data="adm_list:0")],
    ]
    await update.message.reply_text("Admin Menu:", reply_markup=InlineKeyboardMarkup(kb))

# optimized keyboard generation (compact, no heavy objects)
def build_member_kb(selected: Set[int], page: int):
    offset = page * MEMBER_PAGE
    rows, total = list_members(offset, MEMBER_PAGE)
    kb = []
    for mid, uname, disp in rows:
        prefix = "✔ " if mid in selected else ""
        label = f"{prefix}{disp}" + (f" ({uname})" if uname else "")
        kb.append([InlineKeyboardButton(label, callback_data=f"sel:{mid}:{page}")])
    nav = []
    if offset > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"m:{page-1}"))
    if offset + MEMBER_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"m:{page+1}"))
    if nav:
        kb.append(nav)
    kb.append([InlineKeyboardButton("✅ Done", callback_data="done")])
    return InlineKeyboardMarkup(kb)

# --- create flow ---
async def admin_create_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["create"] = {"sel": set(), "page": 0}
    kb = build_member_kb(set(), 0)
    await q.message.reply_text("Select users to add (toggle):", reply_markup=kb)

async def member_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    # pattern sel:{mid}:{page}
    try:
        _, mid_s, page_s = q.data.split(":")
        mid = int(mid_s); page = int(page_s)
    except Exception:
        return await q.message.reply_text("Bad selection")
    sess = context.user_data.setdefault("create", {"sel": set(), "page": 0})
    sel = sess["sel"]
    if mid in sel: sel.remove(mid)
    else: sel.add(mid)
    sess["page"] = page
    kb = build_member_kb(sel, page)
    try:
        await q.message.edit_text("Select users to add (toggle):", reply_markup=kb)
    except Exception:
        await q.message.reply_text("Select users to add (toggle):", reply_markup=kb)

async def member_page_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, page_s = q.data.split(":")
        page = int(page_s)
    except Exception:
        page = 0
    sess = context.user_data.setdefault("create", {"sel": set(), "page": 0})
    sess["page"] = page
    kb = build_member_kb(sess["sel"], page)
    try:
        await q.message.edit_text("Select users to add (toggle):", reply_markup=kb)
    except Exception:
        await q.message.reply_text("Select users to add (toggle):", reply_markup=kb)

async def done_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    sess = context.user_data.get("create")
    if not sess or not sess.get("sel"):
        return await q.message.reply_text("No users selected.")
    context.user_data["pending"] = list(sess["sel"])
    context.user_data.pop("create", None)
    context.user_data["await_name"] = True
    await q.message.reply_text("Send group name (no spaces):")

async def finalize_group_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_name"):
        return False
    name = update.message.text.strip().lower()
    if not name:
        return await update.message.reply_text("Invalid name.")
    mids = context.user_data.pop("pending", [])
    context.user_data.pop("await_name", None)
    create_group(name, mids)
    await update.message.reply_text(f"Group '{name}' created with {len(mids)} members.")
    return True

# --- rename ---
async def rename_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    groups, total = get_groups(0, GROUPS_PAGE)
    if not groups:
        return await q.message.reply_text("No groups to rename.")
    kb = [[InlineKeyboardButton(g, callback_data=f"ren:{g}")] for g in groups]
    await q.message.reply_text("Choose a group to rename:", reply_markup=InlineKeyboardMarkup(kb))

async def rename_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, g = q.data.split(":",1)
    except:
        return await q.message.reply_text("Bad selection")
    context.user_data["rename_old"] = g
    context.user_data["await_rename"] = True
    await q.message.reply_text(f"Send new name for '{g}':")

async def rename_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("await_rename"):
        return
    new = update.message.text.strip().lower()
    old = context.user_data.pop("rename_old","")
    context.user_data.pop("await_rename", None)
    rename_group(old, new)
    await update.message.reply_text(f"Renamed '{old}' → '{new}'")

# --- delete ---
async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    groups, total = get_groups(0, GROUPS_PAGE)
    if not groups:
        return await q.message.reply_text("No groups to delete.")
    kb = [[InlineKeyboardButton(g, callback_data=f"del:{g}")] for g in groups]
    await q.message.reply_text("Choose a group to delete:", reply_markup=InlineKeyboardMarkup(kb))

async def delete_pick_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, g = q.data.split(":",1)
    except:
        return await q.message.reply_text("Bad selection")
    remove_group(g)
    await q.message.reply_text(f"Deleted '{g}'")

# --- list & view ---
async def list_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, page_s = q.data.split(":",1)
        page = int(page_s)
    except:
        page = 0
    groups, total = get_groups(page * GROUPS_PAGE, GROUPS_PAGE)
    if not groups:
        return await q.message.reply_text("No groups found.")
    kb = [[InlineKeyboardButton(g, callback_data=f"view:{g}")] for g in groups]
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅ Prev", callback_data=f"adm_list:{page-1}"))
    if (page + 1) * GROUPS_PAGE < total:
        nav.append(InlineKeyboardButton("Next ➡", callback_data=f"adm_list:{page+1}"))
    if nav:
        kb.append(nav)
    await q.message.reply_text("Groups:", reply_markup=InlineKeyboardMarkup(kb))

async def view_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        _, g = q.data.split(":",1)
    except:
        return await q.message.reply_text("Bad selection")
    mids = get_group_mids(g)
    lines = []
    for mid in mids:
        rec = get_member(mid)
        if not rec: continue
        if rec.get("username"):
            lines.append(f"{rec['display']} ({rec['username']})")
        elif rec.get("user_id"):
            lines.append(f"{rec['display']} (id:{rec['user_id']})")
        else:
            lines.append(rec['display'])
    await q.message.reply_text("\n".join(lines) or "No members in this group.")

# --- mention listener ---
async def mention_listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    text = update.message.text.strip()
    tokens = text.split()
    for token in tokens:
        if token.startswith("@") or token.startswith("#"):
            key = token[1:].lower()
            if key in ("all","everyone"):
                _cur.execute("SELECT username, user_id, display_name FROM members")
                rows = _cur.fetchall()
                mentions = []
                for u, uid, d in rows:
                    if u:
                        mentions.append(u)
                    elif uid:
                        mentions.append(f'<a href="tg://user?id={uid}">{d}</a>')
                for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                    await update.message.reply_html(" ".join(mentions[i:i+MAX_MENTIONS_PER_MESSAGE]))
                return
            _cur.execute("SELECT name FROM groups WHERE lower(name)=?", (key,))
            if _cur.fetchone():
                mids = get_group_mids(key)
                mentions = []
                for mid in mids:
                    rec = get_member(mid)
                    if not rec:
                        continue
                    if rec.get("username"):
                        mentions.append(rec['username'])
                    elif rec.get("user_id"):
                        mentions.append(f'<a href="tg://user?id={rec["user_id"]}">{rec["display"]}</a>')
                for i in range(0, len(mentions), MAX_MENTIONS_PER_MESSAGE):
                    await update.message.reply_html(" ".join(mentions[i:i+MAX_MENTIONS_PER_MESSAGE]))
                return

# --- message handler (DM finals) ---
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("await_name"):
        done = await finalize_group_name(update, context)
        if done:
            return
    if context.user_data.get("await_rename"):
        await rename_msg(update, context)
        return
    return

# ---------------- build app ----------------
def build_app(token: str):
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("setmain", setmain_cmd))
    app.add_handler(CommandHandler("admin", admin_cmd))

    # admin callbacks
    app.add_handler(CallbackQueryHandler(admin_create_cb, pattern=r"^adm_create$"))
    app.add_handler(CallbackQueryHandler(rename_start, pattern=r"^adm_rename$"))
    app.add_handler(CallbackQueryHandler(delete_start, pattern=r"^adm_delete$"))
    app.add_handler(CallbackQueryHandler(list_cb, pattern=r"^adm_list:"))
    app.add_handler(CallbackQueryHandler(member_select_cb, pattern=r"^sel:"))
    app.add_handler(CallbackQueryHandler(member_page_cb, pattern=r"^m:"))
    app.add_handler(CallbackQueryHandler(done_cb, pattern=r"^done$"))
    app.add_handler(CallbackQueryHandler(view_cb, pattern=r"^view:"))
    app.add_handler(CallbackQueryHandler(rename_pick_cb, pattern=r"^ren:"))
    app.add_handler(CallbackQueryHandler(delete_pick_cb, pattern=r"^del:"))

    # message handlers
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mention_listener))

    return app

# ---------------- main ----------------
if __name__ == "__main__":
    app = build_app(TOKEN)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(app.run_polling())
    except RuntimeError:
        asyncio.run(app.run_polling())
