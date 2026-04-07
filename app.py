import functools
import os
import re
import sqlite3
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, g, session, jsonify,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = "larney-properties-secret-key"

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATABASE     = os.path.join(BASE_DIR, "properties.db")
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB


# ── Database helpers ──────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create all tables and seed default agent on first run."""
    with sqlite3.connect(DATABASE) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                title          TEXT    NOT NULL,
                price          TEXT    NOT NULL,
                location       TEXT    NOT NULL,
                description    TEXT,
                image_filename TEXT,
                bedrooms       INTEGER DEFAULT 0,
                bathrooms      INTEGER DEFAULT 0,
                size_sqm       INTEGER DEFAULT 0,
                property_type  TEXT    DEFAULT 'House',
                status         TEXT    DEFAULT 'For Sale',
                is_featured    INTEGER DEFAULT 0,
                created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT    NOT NULL UNIQUE,
                password_hash TEXT    NOT NULL,
                created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        if db.execute("SELECT COUNT(*) FROM agents").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO agents (username, password_hash) VALUES (?, ?)",
                ("admin", generate_password_hash("larney2025")),
            )
        db.commit()


def migrate_db():
    """Safely add new columns to an existing properties table."""
    new_columns = [
        ("bedrooms",      "INTEGER DEFAULT 0"),
        ("bathrooms",     "INTEGER DEFAULT 0"),
        ("size_sqm",      "INTEGER DEFAULT 0"),
        ("property_type", "TEXT    DEFAULT 'House'"),
        ("status",        "TEXT    DEFAULT 'For Sale'"),
        ("is_featured",   "INTEGER DEFAULT 0"),
        ("agent_phone",   "TEXT    DEFAULT ''"),
        ("agent_email",   "TEXT    DEFAULT ''"),
    ]
    with sqlite3.connect(DATABASE) as db:
        for col, defn in new_columns:
            try:
                db.execute(f"ALTER TABLE properties ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass  # Column already exists
        db.commit()


# ── Auth helpers ──────────────────────────────────────────────────────────────
def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "agent_id" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_current_agent():
    return {"current_agent": session.get("agent_username")}


# ── Utility ───────────────────────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.template_filter("format_price")
def format_price_filter(value):
    """Format a price string with spaces as thousand separators: 2500000 → 2 500 000."""
    digits = re.sub(r"[^\d]", "", str(value or ""))
    if not digits:
        return value
    result, chunk = [], []
    for i, d in enumerate(reversed(digits)):
        if i > 0 and i % 3 == 0:
            result.append(" ")
        result.append(d)
    return "".join(reversed(result))


def to_wa_number(phone):
    """Convert a local SA number to international format for WhatsApp links."""
    p = re.sub(r"[\s\-+()]", "", phone or "")
    if p.startswith("0"):
        p = "27" + p[1:]
    return p or "27836548010"


def parse_price_numeric(price_str):
    """Strip everything non-digit from a price string and return int."""
    digits = re.sub(r"[^\d]", "", price_str or "")
    return int(digits) if digits else 0


# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    query = request.args.get("q", "").strip()
    db    = get_db()

    if query:
        rows = db.execute(
            """
            SELECT * FROM properties
            WHERE title LIKE ? OR location LIKE ? OR property_type LIKE ?
            ORDER BY is_featured DESC, created_at DESC
            """,
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM properties ORDER BY is_featured DESC, created_at DESC"
        ).fetchall()

    raw = db.execute("""
        SELECT
            COUNT(*)  AS total,
            SUM(CASE WHEN status = 'For Sale' THEN 1 ELSE 0 END) AS for_sale,
            SUM(CASE WHEN status = 'To Let'   THEN 1 ELSE 0 END) AS to_let,
            COUNT(DISTINCT location) AS locations
        FROM properties
    """).fetchone()

    stats = {
        "total":     raw["total"]     or 0,
        "for_sale":  raw["for_sale"]  or 0,
        "to_let":    raw["to_let"]    or 0,
        "locations": raw["locations"] or 0,
    }

    return render_template("index.html", properties=rows, query=query, stats=stats)


@app.route("/property/<int:prop_id>")
def property_detail(prop_id):
    db   = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id = ?", (prop_id,)).fetchone()
    if prop is None:
        flash("Property not found.", "warning")
        return redirect(url_for("index"))
    price_numeric = parse_price_numeric(prop["price"])
    agent_phone_wa = to_wa_number(prop["agent_phone"]) if prop["agent_phone"] else "27836548010"
    agent_phone_display = prop["agent_phone"] if prop["agent_phone"] else "083 654 8010"
    agent_email = prop["agent_email"] if prop["agent_email"] else "lani@larney.co.za"
    return render_template("property.html", prop=prop, price_numeric=price_numeric,
                           agent_phone_wa=agent_phone_wa,
                           agent_phone_display=agent_phone_display,
                           agent_email=agent_email)


@app.route("/bond-calculator")
def bond_calculator():
    return render_template("bond_calculator.html")


@app.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "POST":
        title         = request.form.get("title",         "").strip()
        price         = request.form.get("price",         "").strip()
        location      = request.form.get("location",      "").strip()
        description   = request.form.get("description",   "").strip()
        bedrooms      = request.form.get("bedrooms",      0)
        bathrooms     = request.form.get("bathrooms",     0)
        size_sqm      = request.form.get("size_sqm",      0)
        property_type = request.form.get("property_type", "House")
        status        = request.form.get("status",        "For Sale")
        is_featured   = 1 if request.form.get("is_featured") else 0
        agent_phone   = request.form.get("agent_phone",   "").strip()
        agent_email   = request.form.get("agent_email",   "").strip()

        errors = []
        if not title:    errors.append("Title is required.")
        if not price:    errors.append("Price is required.")
        if not location: errors.append("Location is required.")

        image_filename = None
        file = request.files.get("image")
        if file and file.filename:
            if not allowed_file(file.filename):
                errors.append("Only PNG, JPG, JPEG, or WEBP images are allowed.")
            else:
                image_filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("upload.html", form=request.form, image_filename=image_filename)

        db = get_db()
        db.execute(
            """
            INSERT INTO properties
                (title, price, location, description, image_filename,
                 bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
                 agent_phone, agent_email)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, price, location, description, image_filename,
             bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
             agent_phone, agent_email),
        )
        db.commit()
        flash(f'"{title}" has been listed successfully!', "success")
        return redirect(url_for("index"))

    return render_template("upload.html", form={}, image_filename=None)


@app.route("/property/<int:prop_id>/edit", methods=["GET", "POST"])
@login_required
def edit_property(prop_id):
    db   = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id = ?", (prop_id,)).fetchone()
    if prop is None:
        flash("Property not found.", "warning")
        return redirect(url_for("index"))

    if request.method == "POST":
        title         = request.form.get("title",         "").strip()
        price         = request.form.get("price",         "").strip()
        location      = request.form.get("location",      "").strip()
        description   = request.form.get("description",   "").strip()
        bedrooms      = request.form.get("bedrooms",      0)
        bathrooms     = request.form.get("bathrooms",     0)
        size_sqm      = request.form.get("size_sqm",      0)
        property_type = request.form.get("property_type", "House")
        status        = request.form.get("status",        "For Sale")
        is_featured   = 1 if request.form.get("is_featured") else 0
        agent_phone   = request.form.get("agent_phone",   "").strip()
        agent_email   = request.form.get("agent_email",   "").strip()

        errors = []
        if not title:    errors.append("Title is required.")
        if not price:    errors.append("Price is required.")
        if not location: errors.append("Location is required.")

        image_filename = prop["image_filename"]  # keep existing by default
        file = request.files.get("image")
        if file and file.filename:
            if not allowed_file(file.filename):
                errors.append("Only PNG, JPG, JPEG, or WEBP images are allowed.")
            else:
                new_filename = secure_filename(file.filename)
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], new_filename))
                if image_filename and image_filename != new_filename:
                    old_path = os.path.join(app.config["UPLOAD_FOLDER"], image_filename)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                image_filename = new_filename

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("edit_property.html", prop=prop, form=request.form)

        db.execute(
            """
            UPDATE properties SET
                title=?, price=?, location=?, description=?, image_filename=?,
                bedrooms=?, bathrooms=?, size_sqm=?, property_type=?, status=?, is_featured=?,
                agent_phone=?, agent_email=?
            WHERE id=?
            """,
            (title, price, location, description, image_filename,
             bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
             agent_phone, agent_email, prop_id),
        )
        db.commit()
        flash(f'"{title}" has been updated successfully!', "success")
        return redirect(url_for("property_detail", prop_id=prop_id))

    return render_template("edit_property.html", prop=prop, form=dict(prop))


@app.route("/property/<int:prop_id>/delete", methods=["POST"])
@login_required
def delete_property(prop_id):
    db   = get_db()
    prop = db.execute("SELECT * FROM properties WHERE id = ?", (prop_id,)).fetchone()
    if prop is None:
        flash("Property not found.", "warning")
        return redirect(url_for("index"))

    if prop["image_filename"]:
        img_path = os.path.join(app.config["UPLOAD_FOLDER"], prop["image_filename"])
        if os.path.exists(img_path):
            os.remove(img_path)

    db.execute("DELETE FROM properties WHERE id = ?", (prop_id,))
    db.commit()
    flash(f'"{prop["title"]}" has been deleted.', "success")
    return redirect(url_for("index"))


@app.route("/api/properties")
def api_properties():
    """Return property listings as JSON for the skeleton loader."""
    query = request.args.get("q", "").strip()
    db    = get_db()

    if query:
        rows = db.execute(
            """
            SELECT * FROM properties
            WHERE title LIKE ? OR location LIKE ? OR property_type LIKE ?
            ORDER BY is_featured DESC, created_at DESC
            """,
            (f"%{query}%", f"%{query}%", f"%{query}%"),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM properties ORDER BY is_featured DESC, created_at DESC"
        ).fetchall()

    return jsonify({"properties": [dict(r) for r in rows]})


@app.route("/login", methods=["GET", "POST"])
def login():
    if "agent_id" in session:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db       = get_db()
        agent    = db.execute(
            "SELECT * FROM agents WHERE username = ?", (username,)
        ).fetchone()

        if agent and check_password_hash(agent["password_hash"], password):
            session.clear()
            session["agent_id"]       = agent["id"]
            session["agent_username"] = agent["username"]
            flash(f"Welcome back, {agent['username']}!", "success")
            return redirect(url_for("index"))

        flash("Invalid username or password.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    migrate_db()
    app.run(debug=True, host='0.0.0.0', port=64000)
