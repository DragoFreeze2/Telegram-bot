#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler,
    MessageHandler, ContextTypes, filters
)

# Your usernames list (WITHOUT @)
USERS = [
    "Y_35a",
    "Fbbhzoot",
    "llN5lx",
    "xxaraaas",
    "x320p",
    "hhmr39",
    "ki_4t",
    "abdulah_aljj",
    "yo_glg",
    "karam199779",
    "gli_894",
    "MLD38",
    "s1_6ra",
    "dmxv1",
    "jy5u_1",
    "i7obe",
    "yz_5m",
    "MY7MY74477",
    "OBA3IDA",
    "saif_sa_cr7",
    "mp8v1",
    "jgfw1",
    "c9z67",
    "hasonppppp",
    "a_8lmf",
    "X_NN_R",
    "My7my7447",
    "dragon_freeze2"
]

found = {}

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("Missing TOKEN env variable.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Rempo bot started.\n\n"
        "Tell everyone to send any message.\n\n"
        "Every time a username matches your list, I will print its ID to the terminal."
    )

async def listener(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    
    user = update.message.from_user
    username = user.username

    if not username:
        return

    if username in USERS and username not in found:
        found[username] = user.id
        print(f"FOUND ID: {username} -> {user.id}")
        await update.message.reply_text(f"Saved {username} → {user.id} (check terminal).")


def build():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("startscan", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, listener))
    return app


if __name__ == "main":
    app = build()
    app.run_polling()