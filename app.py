import json
import os
from functools import wraps

import requests
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(path=None):
    if path is None:
        path = os.path.join(BASE_DIR, ".env")

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if key and key not in os.environ:
                os.environ[key] = value


load_dotenv()

app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/owl-alpha"
USERS_FILE = os.path.join(BASE_DIR, "users.json")
CHAT_MEMORY = {}
MAX_MEMORY_MESSAGES = 12


def get_api_key():
    load_dotenv()
    return os.environ.get("OPENROUTER_API_KEY", "")


def get_model():
    load_dotenv()
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def get_user_memory():
    return CHAT_MEMORY.setdefault(session["username"], [])


def trim_memory(messages):
    if len(messages) > MAX_MEMORY_MESSAGES:
        del messages[:-MAX_MEMORY_MESSAGES]


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}

    with open(USERS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)


def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as file:
        json.dump(users, file, indent=2)


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "username" not in session:
            if request.path == "/chat":
                return jsonify({"reply": "Please log in first."}), 401
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


@app.route("/")
@login_required
def home():
    return render_template("index.html", username=session["username"])


@app.after_request
def add_no_cache_headers(response):
    if response.content_type and response.content_type.startswith("text/html"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"

    return response


@app.route("/register", methods=["GET", "POST"])
def register():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.")
            return render_template("register.html")

        users = load_users()
        if username in users:
            flash("That username is already taken.")
            return render_template("register.html")

        users[username] = generate_password_hash(password)
        save_users(users)
        session["username"] = username
        return redirect(url_for("home"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if "username" in session:
        return redirect(url_for("home"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        users = load_users()

        if username in users and check_password_hash(users[username], password):
            session["username"] = username
            return redirect(url_for("home"))

        flash("Invalid username or password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/memory/clear", methods=["POST"])
@login_required
def clear_memory():
    CHAT_MEMORY.pop(session["username"], None)
    return jsonify({"status": "cleared"})


@app.route("/chat", methods=["POST"])
@login_required
def chat():
    api_key = get_api_key()
    if not api_key:
        return jsonify({"reply": "OpenRouter API key is missing. Set OPENROUTER_API_KEY first."}), 500

    user_message = request.json.get("message", "")
    messages = get_user_memory().copy()
    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:5001",
        "X-Title": "Simple Chatbot",
    }

    data = {
        "model": get_model(),
        "messages": messages,
        "max_tokens": 300,
    }

    try:
        client = requests.Session()
        client.trust_env = False
        response = client.post(API_URL, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        reply = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        if not reply:
            return jsonify({"reply": "OpenRouter returned an empty response. Please try again."}), 502

        memory = get_user_memory()
        memory.append({"role": "user", "content": user_message})
        memory.append({"role": "assistant", "content": reply})
        trim_memory(memory)

        return jsonify({"reply": reply})

    except requests.exceptions.HTTPError:
        try:
            error_body = response.json()
            error_message = error_body.get("error", {}).get("message") or response.text
        except ValueError:
            error_message = response.text

        return jsonify({
            "reply": f"OpenRouter error {response.status_code}: {error_message}"
        }), response.status_code

    except Exception as e:
        return jsonify({"reply": f"Error: {str(e)}"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
