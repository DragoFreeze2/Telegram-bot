# webapp_server.py
import threading
import os
from flask import Flask, jsonify, request, send_from_directory, abort
import httpx

app = Flask(__name__, static_folder="webapp", static_url_path="/webapp")

# These will be set by start_webapp(get_groups_fn, get_tag_groups_fn)
_GET_GROUPS = None
_GET_TAG_GROUPS = None
BOT_TOKEN = os.getenv("TOKEN") or os.getenv("BOT_TOKEN")


@app.route("/webapp/index.html")
def webapp_index():
    return send_from_directory("webapp", "index.html")


@app.route("/webapp/<path:path>")
def webapp_static(path):
    return send_from_directory("webapp", path)


@app.route("/api/groups")
def api_groups():
    groups = _GET_GROUPS() if _GET_GROUPS else {}
    # return an array of {chat_id, title}
    out = [{"chat_id": int(k), "title": f"Group {k}"} for k in groups.keys()]
    return jsonify({"groups": out})


@app.route("/api/members/<int:chat_id>")
def api_members(chat_id: int):
    groups = _GET_GROUPS() if _GET_GROUPS else {}
    members = groups.get(str(chat_id)) or groups.get(chat_id) or []
    # members are stored as list of (user_id, name) or list of dicts - handle both
    out = []
    for item in members:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append({"id": int(item[0]), "name": item[1]})
        elif isinstance(item, dict):
            out.append({"id": int(item.get("id")), "name": item.get("name")})
        else:
            # fallback if you stored just usernames as strings
            out.append({"id": None, "name": str(item)})
    return jsonify(out)


@app.route("/api/taggroups/<int:chat_id>")
def api_taggroups(chat_id: int):
    tgs = _GET_TAG_GROUPS() if _GET_TAG_GROUPS else {}
    tg = tgs.get(str(chat_id)) or tgs.get(chat_id) or {}
    return jsonify({"tag_groups": tg})


@app.route("/api/taggroups", methods=["POST"])
def api_create_taggroups():
    data = request.get_json() or {}
    chat_id = data.get("chat_id")
    name = data.get("name")
    members = data.get("members", [])
    if not chat_id or not name:
        abort(400, "chat_id and name required")

    tgs = _GET_TAG_GROUPS() if _GET_TAG_GROUPS else {}
    # ensure storage under string key
    key = str(chat_id)
    if key not in tgs:
        tgs[key] = {}
    tgs[key][name] = members
    return jsonify({"ok": True})


@app.route("/api/trigger", methods=["POST"])
def api_trigger():
    data = request.get_json() or {}
    chat_id = data.get("chat_id")
    tag_name = data.get("tag_name")
    if not chat_id or not tag_name:
        abort(400, "chat_id and tag_name required")

    tgs = _GET_TAG_GROUPS() if _GET_TAG_GROUPS else {}
    tg = (tgs.get(str(chat_id)) or tgs.get(chat_id) or {}).get(tag_name)
    if not tg:
        abort(404, "tag group not found")

    # Build mention message and send via Telegram API (using token env)
    if not BOT_TOKEN:
        abort(500, "BOT_TOKEN not set on server")

    mentions = " ".join([f'<a href="tg://user?id={int(uid)}">\u200b</a>' for uid in tg])
    async_send_message(chat_id, mentions)
    return jsonify({"ok": True})


def async_send_message(chat_id: int, html: str):
    # non-blocking send using httpx in a separate thread
    def _send():
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            httpx.post(url, json={
                "chat_id": chat_id,
                "text": html,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            }, timeout=15.0)
        except Exception as e:
            print("webapp_server send error:", e)
    threading.Thread(target=_send, daemon=True).start()


def start_webapp(get_groups_fn=None, get_tag_groups_fn=None, host="0.0.0.0", port=8000):
    """
    Call this from your bot like:
      start_webapp(lambda: GROUP_MEMBERS, lambda: TAG_GROUPS)
    """
    global _GET_GROUPS, _GET_TAG_GROUPS
    _GET_GROUPS = get_groups_fn
    _GET_TAG_GROUPS = get_tag_groups_fn

    def run():
        # Flask's development server is fine for Railway / simple hosting
        app.run(host=host, port=port, threaded=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
