import os
from flask import Flask, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

TOKEN = os.getenv("TOKEN")  # Loaded from Railway variables

app = Flask(__name__)

# Build Telegram application (PTB v20+)
telegram_app = (
    Application.builder()
    .token(TOKEN)
    .build()
)

# ------------------- COMMANDS -------------------

async def start(update: Update, context):
    await update.message.reply_text("Bot is running!")

telegram_app.add_handler(CommandHandler("start", start))

# ------------------- FLASK WEBHOOK -------------------

@app.route("/webhook", methods=["POST"])
def webhook():
    update = Update.de_json(request.json, telegram_app.bot)
    telegram_app.process_update(update)
    return "OK", 200


@app.route("/", methods=["GET"])
def home():
    return "Bot is running", 200

# ------------------- START WEBHOOK SERVER -------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
