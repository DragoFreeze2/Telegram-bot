#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import nest_asyncio
nest_asyncio.apply()

import asyncio
import logging
import sqlite3
from typing import List, Optional, Dict, Set
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ------------------------------------
# CONFIG
# ------------------------------------
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN environment variable not set.")

DB_FILE = "data.db"
MEMBER_PAGE = 14
GROUPS_PAGE = 14
MAX_MENTIONS_PER_MESSAGE = 200

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------------------------
# STATIC MEMBER LIST (username or ID)
# ------------------------------------
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

# ------------------------------------
# DATABASE
# ------------------------------------
_conn = sqlite3.connect(DB_FILE, check_same_thread=False)
_cur = _conn.cursor()

_cur.executescript("""
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
""")
_conn.commit()

def preload_members():
    for raw, disp in MEMBERS.items():
        try:
            if raw.isdigit():
                _cur.execute("INSERT OR IGNORE INTO members(user_id,display_name) VALUES(?,?)",(int(raw),disp))
            else:
                uname = raw if raw.startswith("@") else f"@{raw}"
                _cur.execute("INSERT OR IGNORE INTO members(username,display_name) VALUES(?,?)",(uname,disp))
        except:
            pass
    _conn.commit()

preload_members()

def set_setting(key,val):
    _cur.execute("REPLACE INTO settings(key,value) VALUES(?,?)",(key,val))
    _conn.commit()

def get_setting(key):
    r=_cur.execute("SELECT value FROM settings WHERE key=?",(key,)).fetchone()
    return r[0] if r else None

def list_members(offset,limit):
    total=_cur.execute("SELECT COUNT(*) FROM members").fetchone()[0]
    rows=_cur.execute("SELECT id,username,display_name FROM members ORDER BY display_name LIMIT ? OFFSET ?",(limit,offset)).fetchall()
    return rows,total

def get_member(mid):
    r=_cur.execute("SELECT id,username,user_id,display_name FROM members WHERE id=?",(mid,)).fetchone()
    if not r: return None
    return {"id":r[0],"username":r[1],"user_id":r[2],"display":r[3]}

def create_group(name,mids):
    _cur.execute("INSERT OR IGNORE INTO groups(name) VALUES(?)",(name,))
    for mid in mids:
        _cur.execute("INSERT OR IGNORE INTO group_members(group_name,member_id) VALUES(?,?)",(name,mid))
    _conn.commit()

def list_groups(offset,limit):
    total=_cur.execute("SELECT COUNT(*) FROM groups").fetchone()[0]
    rows=_cur.execute("SELECT name FROM groups ORDER BY name LIMIT ? OFFSET ?",(limit,offset)).fetchall()
    return [r[0] for r in rows],total

def get_group_mids(name):
    rows=_cur.execute("SELECT member_id FROM group_members WHERE group_name=?",(name,)).fetchall()
    return [r[0] for r in rows]

def remove_group(name):
    _cur.execute("DELETE FROM group_members WHERE group_name=?",(name,))
    _cur.execute("DELETE FROM groups WHERE name=?",(name,))
    _conn.commit()

# ------------------------------------
# ADMIN CHECK
# ------------------------------------
async def is_admin(user_id,context):
    main=get_setting("main_group_id")
    if not main: return False
    try:
        info=await context.bot.get_chat_member(int(main),user_id)
        return info.status in ("administrator","creator")
    except:
        return False

# ------------------------------------
# /start
# ------------------------------------
async def start(update:Update,context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is running. Use /admin in DM.")

# ------------------------------------
# /setmain
# ------------------------------------
async def setmain(update:Update,context:ContextTypes.DEFAULT_TYPE):
    chat=update.effective_chat
    if chat.type not in ("group","supergroup"):
        return await update.message.reply_text("Run /setmain inside the main group.")
    set_setting("main_group_id",str(chat.id))
    await update.message.reply_text("Main group saved!")

# ------------------------------------
# /admin
# ------------------------------------
async def admin(update:Update,context:ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id,context):
        return await update.message.reply_text("Admins only.")
    kb=[
        [InlineKeyboardButton("➕ Create Group",callback_data="create")],
        [InlineKeyboardButton("🗑 Delete Group",callback_data="delete")],
        [InlineKeyboardButton("📚 List Groups",callback_data="list:0")]
    ]
    await update.message.reply_text("Admin panel:",reply_markup=InlineKeyboardMarkup(kb))

# ------------------------------------
# MEMBER SELECT UI
# ------------------------------------
def build_member_kb(selected,page):
    offset = page*MEMBER_PAGE
    rows,total=list_members(offset,MEMBER_PAGE)
    kb=[]
    for mid,uname,disp in rows:
        sel="✔ " if mid in selected else ""
        label=f"{sel}{disp} ({uname})" if uname else f"{sel}{disp}"
        kb.append([InlineKeyboardButton(label,callback_data=f"sel:{mid}:{page}")])
    nav=[]
    if offset>0: nav.append(InlineKeyboardButton("⬅",callback_data=f"page:{page-1}"))
    if offset+MEMBER_PAGE<total: nav.append(InlineKeyboardButton("➡",callback_data=f"page:{page+1}"))
    if nav: kb.append(nav)
    kb.append([InlineKeyboardButton("✅ Done",callback_data="finish")])
    return InlineKeyboardMarkup(kb)

# Create start
async def cb_create(update,context):
    q=update.callback_query; await q.answer()
    context.user_data["selected"]=set()
    context.user_data["page"]=0
    await q.message.reply_text("Select users:",reply_markup=build_member_kb(set(),0))

# Toggle selection
async def cb_sel(update,context):
    q=update.callback_query; await q.answer()
    _,mid_s,page_s=q.data.split(":")
    mid=int(mid_s); page=int(page_s)
    sel=context.user_data["selected"]
    if mid in sel: sel.remove(mid)
    else: sel.add(mid)
    context.user_data["page"]=page
    await q.message.edit_text("Select users:",reply_markup=build_member_kb(sel,page))

# Page nav
async def cb_page(update,context):
    q=update.callback_query; await q.answer()
    _,page_s=q.data.split(":")
    page=int(page_s)
    context.user_data["page"]=page
    sel=context.user_data["selected"]
    await q.message.edit_text("Select users:",reply_markup=build_member_kb(sel,page))

# Finish selection
async def cb_finish(update,context):
    q=update.callback_query; await q.answer()
    sel=context.user_data["selected"]
    if not sel: return await q.message.reply_text("Empty.")
    context.user_data["final_sel"]=list(sel)
    context.user_data["ask_name"]=True
    await q.message.reply_text("Send group name (no spaces).")

# Name input
async def msg_name(update,context):
    if not context.user_data.get("ask_name"): return
    name=update.message.text.strip().lower()
    mids=context.user_data["final_sel"]
    create_group(name,mids)
    context.user_data.clear()
    await update.message.reply_text(f"Created group {name}")

# ------------------------------------
# Delete group
# ------------------------------------
async def cb_delete(update,context):
    q=update.callback_query; await q.answer()
    groups,_=list_groups(0,999)
    if not groups: return await q.message.reply_text("No groups.")
    kb=[[InlineKeyboardButton(g,callback_data=f"del:{g}")] for g in groups]
    await q.message.reply_text("Delete which group?",reply_markup=InlineKeyboardMarkup(kb))

async def cb_delpick(update,context):
    q=update.callback_query; await q.answer()
    _,g=q.data.split(":",1)
    remove_group(g)
    await q.message.reply_text(f"Deleted {g}")

# ------------------------------------
# List Groups
# ------------------------------------
async def cb_list(update,context):
    q=update.callback_query; await q.answer()
    _,page_s=q.data.split(":")
    page=int(page_s)
    groups,total=list_groups(page*GROUPS_PAGE,GROUPS_PAGE)
    kb=[]
    for g in groups:
        mids=get_group_mids(g)
        kb.append([InlineKeyboardButton(f"{g} ({len(mids)})",callback_data=f"view:{g}")])
    nav=[]
    if page>0: nav.append(InlineKeyboardButton("⬅",callback_data=f"list:{page-1}"))
    if (page+1)*GROUPS_PAGE<total: nav.append(InlineKeyboardButton("➡",callback_data=f"list:{page+1}"))
    if nav: kb.append(nav)
    await q.message.reply_text("Groups:",reply_markup=InlineKeyboardMarkup(kb))

async def cb_view(update,context):
    q=update.callback_query; await q.answer()
    _,g=q.data.split(":",1)
    mids=get_group_mids(g)
    lines=[]
    for mid in mids:
        rec=get_member(mid)
        if rec["username"]: lines.append(f"{rec['display']} ({rec['username']})")
        else: lines.append(f"{rec['display']}")
    await q.message.reply_text("\n".join(lines) or "Empty.")

# ------------------------------------
# MENTION LISTENER
# ------------------------------------
async def mention_listener(update,context):
    if not update.message: return
    text=update.message.text.lower()
    tokens=text.split()

    for t in tokens:
        if not (t.startswith("@") or t.startswith("#")):
            continue

        key=t[1:]

        # @all
        if key in ("all","everyone"):
            rows=_cur.execute("SELECT username,user_id,display_name FROM members").fetchall()
            mentions=[]
            for u,uid,d in rows:
                if u:
                    mentions.append(u)
                elif uid:
                    mentions.append(f'<a href="tg://user?id={uid}">{d}</a>')
            for i in range(0,len(mentions),MAX_MENTIONS_PER_MESSAGE):
                await update.message.reply_html(" ".join(mentions[i:i+MAX_MENTIONS_PER_MESSAGE]))
            return

        # @group
        exists=_cur.execute("SELECT name FROM groups WHERE name=?",(key,)).fetchone()
        if exists:
            mids=get_group_mids(key)
            mentions=[]
            for mid in mids:
                r=get_member(mid)
                if r["username"]:
                    mentions.append(r["username"])
                else:
                    mentions.append(f'<a href="tg://user?id={r["user_id"]}">{r["display"]}</a>')
            for i in range(0,len(mentions),MAX_MENTIONS_PER_MESSAGE):
                await update.message.reply_html(" ".join(mentions[i:i+MAX_MENTIONS_PER_MESSAGE]))
            return

# ------------------------------------
# BUILD APP
# ------------------------------------
def build_app():
    app=ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("setmain",setmain))
    app.add_handler(CommandHandler("admin",admin))

    # callbacks
    app.add_handler(CallbackQueryHandler(cb_create,pattern="^create$"))
    app.add_handler(CallbackQueryHandler(cb_delete,pattern="^delete$"))
    app.add_handler(CallbackQueryHandler(cb_list,pattern="^list:"))
    app.add_handler(CallbackQueryHandler(cb_sel,pattern="^sel:"))
    app.add_handler(CallbackQueryHandler(cb_page,pattern="^page:"))
    app.add_handler(CallbackQueryHandler(cb_finish,pattern="^finish$"))
    app.add_handler(CallbackQueryHandler(cb_delpick,pattern="^del:"))
    app.add_handler(CallbackQueryHandler(cb_view,pattern="^view:"))

    # input for group name
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,msg_name))

    # main tag system
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,mention_listener))

    return app

# ------------------------------------
# MAIN
# ------------------------------------
if __name__=="__main__":
    app=build_app()
    asyncio.run(app.run_polling())