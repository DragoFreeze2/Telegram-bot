# Telegram Tag Group Bot – Webhook Version (Railway-Ready)
# python-telegram-bot v20+

import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from webapp_server import start_webapp

# ----------------------------------------------------------------------------------
# DATA STORAGE
# ----------------------------------------------------------------------------------
USER_STATE = {}            # {user_id: {step, temp}}
GROUP_MEMBERS = {}         # {chat_id: [(user_id, name)]}
TAG_GROUPS = {}            # {chat_id: {tag_name: [user_ids]}}
TEMP_SELECTION = {}        # {user_id: set(selected_ids)}

# Start webapp & pass accessors
start_webapp(lambda: GROUP_MEMBERS, lambda: TAG_GROUPS)

# ----------------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------------
def get_user_state(user_id):
    return USER_STATE.setdefault(user_id, {"step": None, "temp": {}})

# ----------------------------------------------------------------------------------
# /start (DM ONLY)
# ----------------------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.message.chat

    if chat.type != "private":
        await update.message.reply_text("Use /start in DM only.")
        return

    keyboard = [[InlineKeyboardButton("Start", callback_data="dm_start")]]

    await update.message.reply_text(
        "Add me to a group first, then press Start.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ----------------------------------------------------------------------------------
# CALLBACK HANDLER
# ----------------------------------------------------------------------------------
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    state = get_user_state(user_id)

    # --------------------------- DM Start ---------------------------
    if data == "dm_start":
        if not GROUP_MEMBERS:
            await query.edit_message_text("I’m not in any groups yet. Add me to a group first.")
            return

        keyboard = []
        for chat_id in GROUP_MEMBERS:
            keyboard.append([
                InlineKeyboardButton(f"Group {chat_id}", callback_data=f"open_menu|{chat_id}")
            ])

        await query.edit_message_text(
            "Choose a group:", reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --------------------------- Group Menu ---------------------------
    if data.startswith("open_menu"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)

        keyboard = [
            [InlineKeyboardButton("Add Tag Group", callback_data=f"add_tag_group|{chat_id}")],
            [InlineKeyboardButton("Manage Tag Groups", callback_data=f"manage_tag_groups|{chat_id}")],
        ]

        await query.edit_message_text(
            f"Tag Menu for group {chat_id}",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    # --------------------------- Add Tag Group ---------------------------
    if data.startswith("add_tag_group"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)

        members = GROUP_MEMBERS.get(chat_id, [])
        TEMP_SELECTION[user_id] = set()

        keyboard = [
            [InlineKeyboardButton(name, callback_data=f"toggle_member|{chat_id}|{uid}")]
            for uid, name in members
        ]
        keyboard.append([InlineKeyboardButton("Done", callback_data=f"done_select|{chat_id}")])

        await query.edit_message_text(
            "Select members:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --------------------------- Toggle Member ---------------------------
    if data.startswith("toggle_member"):
        _, chat_id, uid = data.split("|")
        uid = int(uid)

        selected = TEMP_SELECTION[user_id]
        if uid in selected:
            selected.remove(uid)
        else:
            selected.add(uid)

        await query.answer("Updated.")
        return

    # --------------------------- Done Selecting Members ---------------------------
    if data.startswith("done_select"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)

        state["step"] = "waiting_tag_name"
        state["temp"] = {
            "chat_id": chat_id,
            "members": list(TEMP_SELECTION[user_id]),
        }

        await query.edit_message_text("Send the tag group name:")
        return

    # --------------------------- Manage Tag Groups ---------------------------
    if data.startswith("manage_tag_groups"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)

        groups = TAG_GROUPS.get(chat_id, {})

        if not groups:
            await query.edit_message_text("No tag groups found.")
            return

        keyboard = [
            [InlineKeyboardButton(tg, callback_data=f"edit_tg|{chat_id}|{tg}")]
            for tg in groups
        ]

        await query.edit_message_text(
            "Select a tag group:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # --------------------------- Tag Group Options ---------------------------
    if data.startswith("edit_tg"):
        _, chat_id, tg_name = data.split("|")
        chat_id = int(chat_id)

        keyboard = [
            [InlineKeyboardButton("Edit Members", callback_data=f"edit_members|{chat_id}|{tg_name}")],
            [InlineKeyboardButton("Edit Name", callback_data=f"edit_name|{chat_id}|{tg_name}")],
            [InlineKeyboardButton("Delete Tag Group", callback_data=f"delete_tg|{chat_id}|{tg_name}")],
        ]

        await query.edit_message_text(
            f"Managing: {tg_name}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

# ----------------------------------------------------------------------------------
# TEXT HANDLER
# ----------------------------------------------------------------------------------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    # --------------------------- DM: Tag name ---------------------------
    if state["step"] == "waiting_tag_name":
        tag_name = update.message.text.strip()
        chat_id = state["temp"]["chat_id"]
        members = state["temp"]["members"]

        TAG_GROUPS.setdefault(chat_id, {})[tag_name] = members

        state["step"] = None
        state["temp"] = {}

        await update.message.reply_text("Tag group created successfully.")
        return

    # --------------------------- Group Tagging ---------------------------
    if update.message.chat.type in ["group", "supergroup"]:
        text = update.message.text.strip()
        chat_id = update.message.chat_id
        groups = TAG_GROUPS.get(chat_id, {})

        for tg_name, ids in groups.items():
            if text == f"@{tg_name}" or text == f"#{tg_name}":
                mentions = " ".join(
                    f"<a href=\"tg://user?id={uid}\">.</a>" for uid in ids
                )
                await update.message.reply_html(mentions)
                return

# ----------------------------------------------------------------------------------
# BOT LAUNCH — WEBHOOK MODE
# ----------------------------------------------------------------------------------
async def set_webhook(app):
    webhook_url = os.getenv("WEBHOOK_URL")
    await app.bot.set_webhook(webhook_url)

def main():
    token = os.getenv("TOKEN")
    webhook_url = os.getenv("WEBHOOK_URL")

    if not token:
        raise RuntimeError("TOKEN environment variable missing.")
    if not webhook_url:
        raise RuntimeError("WEBHOOK_URL environment variable missing.")

    app = ApplicationBuilder().token(token).build()

    # handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # set webhook at startup
    app.post_init = set_webhook

    print("Bot running with webhook...")
    app.run_webhook(
    listen="0.0.0.0",
    port=int(os.getenv("PORT", 8080)),
    url_path=os.getenv("TOKEN"),
    webhook_url=f"{os.getenv('WEBHOOK_URL')}/{os.getenv('TOKEN')}",
)

if __name__ == "__main__":
    main()
