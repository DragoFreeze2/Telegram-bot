# webapp_server.py
import os
from flask import Flask, request
import threading
import requests
import json

flask_app = Flask(__name__)

GROUP_MEMBERS_GETTER = None
TAG_GROUPS_GETTER = None

def start_webapp(get_members, get_tag_groups):
    global GROUP_MEMBERS_GETTER, TAG_GROUPS_GETTER
    GROUP_MEMBERS_GETTER = get_members
    TAG_GROUPS_GETTER = get_tag_groups

    # run Flask in background thread (important for Railway)
    thread = threading.Thread(target=lambda: flask_app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080))
    ))
    thread.daemon = True
    thread.start()

@flask_app.route("/", methods=["GET"])
def home():
    return "Bot is running.", 200

@flask_app.route("/", methods=["POST"])
def telegram_webhook():
    # forward Telegram update to local bot webhook handler
    try:
        data = request.get_json()

        # send update to bot.py webhook handler endpoint
        url = "http://127.0.0.1:8080"  # internal bot endpoint
        requests.post(url, json=data)

        return "OK", 200
    except Exception as e:
        return str(e), 500