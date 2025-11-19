import os
from flask import Flask, request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# ----------------------------------------------------------------------------------
# DATA STORAGE (In-memory)
# ----------------------------------------------------------------------------------
USER_STATE = {}            # {user_id: {step, temp}}
GROUP_MEMBERS = {}         # {chat_id: [(user_id, name)]}
TAG_GROUPS = {}            # {chat_id: {tag_name: [user_ids]}}
TEMP_SELECTION = {}        # {user_id: set(selected_ids)}

# ----------------------------------------------------------------------------------
# HELPERS
# ----------------------------------------------------------------------------------
def get_user_state(user_id):
    return USER_STATE.setdefault(user_id, {"step": None, "temp": {}})

# ----------------------------------------------------------------------------------
# Bot commands & handlers
# ----------------------------------------------------------------------------------
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type != "private":
        await update.message.reply_text("Use /start in private chat with me.")
        return

    keyboard = [[InlineKeyboardButton("Start", callback_data="dm_start")]]
    await update.message.reply_text(
        "Add me to a group first, then press Start:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    state = get_user_state(user_id)

    if data == "dm_start":
        if not GROUP_MEMBERS:
            await query.edit_message_text("I’m not in any groups yet. Add me to a group first.")
            return
        keyboard = [[InlineKeyboardButton(f"Group {cid}", callback_data=f"open_menu|{cid}")]
                    for cid in GROUP_MEMBERS.keys()]
        await query.edit_message_text("Choose a group:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("open_menu"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)
        keyboard = [
            [InlineKeyboardButton("Add Tag Group", callback_data=f"add_tag_group|{chat_id}")],
            [InlineKeyboardButton("Manage Tag Groups", callback_data=f"manage_tag_groups|{chat_id}")]
        ]
        await query.edit_message_text(f"Tag Menu for group {chat_id}", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("add_tag_group"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)
        members = GROUP_MEMBERS.get(chat_id, [])
        TEMP_SELECTION[user_id] = set()
        keyboard = [[InlineKeyboardButton(name, callback_data=f"toggle_member|{chat_id}|{uid}")]
                    for uid, name in members]
        keyboard.append([InlineKeyboardButton("Done", callback_data=f"done_select|{chat_id}")])
        await query.edit_message_text("Select members:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("toggle_member"):
        _, chat_id, uid = data.split("|")
        uid = int(uid)
        sel = TEMP_SELECTION[user_id]
        if uid in sel:
            sel.remove(uid)
        else:
            sel.add(uid)
        await query.answer("Toggled")
        return

    if data.startswith("done_select"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)
        state["step"] = "waiting_tag_name"
        state["temp"] = {"chat_id": chat_id, "members": list(TEMP_SELECTION[user_id])}
        await query.edit_message_text("Send the tag group name:")
        return

    if data.startswith("manage_tag_groups"):
        _, chat_id = data.split("|")
        chat_id = int(chat_id)
        groups = TAG_GROUPS.get(chat_id, {})
        if not groups:
            await query.edit_message_text("No tag groups found.")
            return
        keyboard = [[InlineKeyboardButton(tg, callback_data=f"edit_tg|{chat_id}|{tg}")]
                    for tg in groups.keys()]
        await query.edit_message_text("Select a tag group:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith("edit_tg"):
        _, chat_id, tg_name = data.split("|")
        chat_id = int(chat_id)
        keyboard = [
            [InlineKeyboardButton("Edit Members", callback_data=f"edit_members|{chat_id}|{tg_name}")],
            [InlineKeyboardButton("Edit Name", callback_data=f"edit_name|{chat_id}|{tg_name}")],
            [InlineKeyboardButton("Delete Tag Group", callback_data=f"delete_tg|{chat_id}|{tg_name}")]
        ]
        await query.edit_message_text(f"Managing {tg_name}:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    if state["step"] == "waiting_tag_name":
        tag_name = update.message.text.strip()
        chat_id = state["temp"]["chat_id"]
        members = state["temp"]["members"]
        TAG_GROUPS.setdefault(chat_id, {})[tag_name] = members
        state["step"] = None
        state["temp"] = {}
        await update.message.reply_text(f"Tag group **{tag_name}** created.")
        return

    if update.effective_chat.type in ["group", "supergroup"]:
        text = update.message.text.strip()
        chat_id = update.effective_chat.id
        groups = TAG_GROUPS.get(chat_id, {})
        for tg_name, ids in groups.items():
            if text == f"@{tg_name}" or text == f"#{tg_name}":
                mentions = " ".join(f'<a href="tg://user?id={uid}">.</a>' for uid in ids)
                await update.message.reply_html(mentions)
                return

# ----------------------------------------------------------------------------------
# Flask + Webhook Setup
# ----------------------------------------------------------------------------------
app = Flask(__name__)

@app.route("/", methods=["GET"])
def home():
    return "Bot is running.", 200

@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, telegram_app.bot)
    telegram_app.create_task(telegram_app.process_update(update))
    return "ok", 200

def main():
    telegram_app.run_polling()  # Only used if you test locally

if __name__ == "__main__":
    # Build Telegram application
    telegram_app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        webhook_url=os.getenv("WEBHOOK_URL") + "/webhook"
        )
