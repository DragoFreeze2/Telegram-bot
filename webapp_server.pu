from flask import Flask, send_from_directory, jsonify
import threading

app = Flask(__name__, static_folder="webapp")

# Example placeholder members (replace with real DB later)
MEMBERS = ["Alice", "Bob", "Charlie"]

@app.route("/webapp/<path:path>")
def send_web(path):
    return send_from_directory("webapp", path)

@app.route("/")
def home():
    return "Mini app is running!"

# API endpoint (used by app.js)
@app.route("/api/members")
def get_members():
    return jsonify(MEMBERS)

def start_webapp():
    def run():
        app.run(host="0.0.0.0", port=8000)
    thread = threading.Thread(target=run)
    thread.start() 
