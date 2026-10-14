"""Flask API + static file server for the Crop Recommendation app.

Run:  python backend/app.py   ->  http://127.0.0.1:5000
"""
import math
import os
import re
import sqlite3
from functools import wraps
from pathlib import Path

import pandas as pd
from flask import Flask, g, jsonify, request, send_from_directory, session
from werkzeug.security import check_password_hash, generate_password_hash

from model import FEATURES, load_or_train

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "backend" / "users.db"

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

BUNDLE = load_or_train()
MODEL, MEANS, STDS = BUNDLE["model"], BUNDLE["means"], BUNDLE["stds"]

# Allowed input ranges (also validated in the UI)
RANGES = {"N": (0, 140), "P": (5, 145), "K": (5, 205), "temperature": (8, 44),
          "humidity": (14, 100), "ph": (3.5, 9.9), "rainfall": (20, 300)}


# ---------- database ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            phone TEXT)""")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(users)")}
        for col in ("email", "phone"):          # upgrade databases made by older versions
            if col not in cols:
                conn.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")
        try:
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_phone ON users(phone)")
        except sqlite3.IntegrityError:
            pass  # old database with duplicate phone numbers
        if not conn.execute("SELECT 1 FROM users WHERE username='farmer'").fetchone():
            conn.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",
                         ("farmer", generate_password_hash("grow2026")))


def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if "user" not in session:
            return jsonify(error="Please sign in."), 401
        return fn(*a, **kw)
    return wrapper


# ---------- auth ----------
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@app.post("/api/register")
def register():
    d = request.get_json(silent=True) or {}
    u, p = str(d.get("username", "")).strip(), str(d.get("password", ""))
    email = str(d.get("email", "")).strip().lower()
    phone = re.sub(r"[\s\-()]", "", str(d.get("phone", "")))
    if len(u) < 3 or len(p) < 6:
        return jsonify(error="Username needs 3+ characters and password 6+."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="Enter a valid email id."), 400
    if not re.fullmatch(r"\+?\d{10,15}", phone):
        return jsonify(error="Enter a valid phone number (10 to 15 digits)."), 400
    try:
        db().execute("INSERT INTO users(username,password_hash,email,phone) VALUES(?,?,?,?)",
                     (u, generate_password_hash(p), email, phone))
        db().commit()
    except sqlite3.IntegrityError:
        c = db()
        if c.execute("SELECT 1 FROM users WHERE username=?", (u,)).fetchone():
            msg = "That username is taken."
        elif c.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
            msg = "An account with this email already exists."
        else:
            msg = "An account with this phone number already exists."
        return jsonify(error=msg), 409
    session["user"] = u
    return jsonify(user=u)


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    u, p = str(d.get("username", "")).strip(), str(d.get("password", ""))
    digits = re.sub(r"[\s\-()]", "", u)          # phone typed with spaces/dashes
    tail = digits.lstrip("+")[-10:] if re.fullmatch(r"\+?\d{10,15}", digits) else None
    row = db().execute(
        "SELECT * FROM users WHERE username=? OR email=? OR phone=? "
        "OR (? IS NOT NULL AND phone LIKE ?)",
        (u, u.lower(), digits, tail, f"%{tail}" if tail else None)).fetchone()
    if not row or not check_password_hash(row["password_hash"], p):
        return jsonify(error="Username or password is incorrect."), 401
    session["user"] = row["username"]
    return jsonify(user=row["username"])


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def me():
    return jsonify(user=session.get("user"))


# ---------- crops ----------
@app.get("/api/crops")
@login_required
def crops():
    """Average growing conditions per crop (feeds Explorer + Ideal conditions)."""
    return jsonify(crops=[{"name": n.title(), **MEANS[n]} for n in sorted(MEANS)],
                   features=FEATURES, accuracy=BUNDLE["accuracy"], rows=BUNDLE["rows"])


@app.post("/api/recommend")
@login_required
def recommend():
    d = request.get_json(silent=True) or {}
    try:
        values = {f: float(d[f]) for f in FEATURES}
    except (KeyError, TypeError, ValueError):
        return jsonify(error=f"Send numeric values for: {', '.join(FEATURES)}"), 400
    for f, v in values.items():
        lo, hi = RANGES[f]
        if not lo <= v <= hi:
            return jsonify(error=f"{f} must be between {lo} and {hi}."), 400

    row = pd.DataFrame([values])[FEATURES]
    proba = MODEL.predict_proba(row)[0]
    ranked = sorted(zip(MODEL.classes_, proba), key=lambda t: -t[1])[:6]

    def feature_match(crop):
        out = {}
        for f in FEATURES:
            z = (values[f] - MEANS[crop][f]) / max(STDS[crop][f], 1e-6)
            out[f] = round(math.exp(-0.5 * z * z), 3)
        return out

    return jsonify(results=[
        {"name": c.title(), "score": round(float(p), 3), "features": feature_match(c)}
        for c, p in ranked])


# ---------- crop photos ----------
IMG_DIR = ROOT / "frontend" / "images"
IMG_DIR.mkdir(exist_ok=True)
EXTS = (".jpg", ".jpeg", ".png", ".webp")


@app.get("/api/photos")
@login_required
def photos():
    """Map crop -> image url for every photo found in frontend/images."""
    out = {}
    for p in IMG_DIR.iterdir():
        if p.suffix.lower() in EXTS and p.stem.lower() in MEANS:
            out[p.stem.lower()] = f"/images/{p.name}?v={int(p.stat().st_mtime)}"
    return jsonify(photos=out)


# ---------- frontend ----------
FRONTEND = ROOT / "frontend"


@app.get("/")
def index():
    return send_from_directory(FRONTEND, "index.html")


@app.get("/<path:name>")
def assets(name):
    return send_from_directory(FRONTEND, name)


@app.after_request
def no_cache(resp):
    if not request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


init_db()
if __name__ == "__main__":
    app.run(debug=True, port=5000)
