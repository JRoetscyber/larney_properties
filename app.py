import functools
import os
import re
import sqlite3
import requests
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, g, session, jsonify,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# ── App config ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "your_development_secret_key_here") # REPLACE 'your_development_secret_key_here' with a strong random value in production

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
DATABASE     = os.path.join(BASE_DIR, "properties.db")
UPLOAD_FOLDER        = os.path.join(BASE_DIR, "static", "uploads")
UPLOAD_FOLDER_AGENTS = os.path.join(BASE_DIR, "static", "uploads", "agents")
ALLOWED_EXTENSIONS   = {"png", "jpg", "jpeg", "webp"}

app.config["UPLOAD_FOLDER"]      = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB

# SMTP Configuration for sending emails
app.config["MAIL_SERVER"]   = os.environ.get("MAIL_SERVER")   or "smtp.gmail.com"
app.config["MAIL_PORT"]     = int(os.environ.get("MAIL_PORT") or 587)
app.config["MAIL_USE_TLS"]  = os.environ.get("MAIL_USE_TLS")  or True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME") or "your_email@gmail.com" # REPLACE WITH YOUR GMAIL
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD") or "your_password" # REPLACE WITH YOUR GMAIL APP PASSWORD
app.config["ADMIN_EMAIL"]   = os.environ.get("ADMIN_EMAIL")   or "admin_email@example.com" # REPLACE WITH ADMIN EMAIL

# ── Database helpers ──────────────────────────────────────────────────────────
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

import smtplib, ssl

def send_email(recipient, subject, body):
    sender_email    = app.config["MAIL_USERNAME"]
    sender_password = app.config["MAIL_PASSWORD"]

    if not sender_email or sender_email == "your_email@gmail.com":
        app.logger.warning(f"Email not sent to {recipient}: MAIL_USERNAME not configured.")
        return

    message = f"Subject: {subject}\n\n{body}"
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as server:
            server.starttls(context=context)
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, recipient, message)
            app.logger.info(f"Email sent to {recipient} with subject '{subject}'")
    except Exception as e:
        app.logger.error(f"Failed to send email to {recipient}: {e}")


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
    """Safely add new columns to existing tables and seed admin flag."""
    property_cols = [
        ("bedrooms",      "INTEGER DEFAULT 0"),
        ("bathrooms",     "INTEGER DEFAULT 0"),
        ("size_sqm",      "INTEGER DEFAULT 0"),
        ("property_type", "TEXT    DEFAULT 'House'"),
        ("status",        "TEXT    DEFAULT 'For Sale'"),
        ("is_featured",   "INTEGER DEFAULT 0"),
        ("agent_phone",   "TEXT    DEFAULT ''"),
        ("agent_email",   "TEXT    DEFAULT ''"),
        ("agent_id",      "INTEGER"),
    ]
    agent_cols = [
        ("full_name",     "TEXT    DEFAULT ''"),
        ("email",         "TEXT    DEFAULT ''"),
        ("phone",         "TEXT    DEFAULT ''"),
        ("bio",           "TEXT    DEFAULT ''"),
        ("profile_image", "TEXT"),
        ("is_admin",      "INTEGER DEFAULT 0"),
    ]
    extra_property_cols = [
        ("garages",       "INTEGER DEFAULT 0"),
        ("erf_size_sqm",  "INTEGER DEFAULT 0"),
    ]
    with sqlite3.connect(DATABASE) as db:
        for col, defn in property_cols:
            try:
                db.execute(f"ALTER TABLE properties ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass
        for col, defn in agent_cols:
            try:
                db.execute(f"ALTER TABLE agents ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass
        for col, defn in extra_property_cols:
            try:
                db.execute(f"ALTER TABLE properties ADD COLUMN {col} {defn}")
            except sqlite3.OperationalError:
                pass
        # seller leads table
        db.execute("""
            CREATE TABLE IF NOT EXISTS seller_leads (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name       TEXT NOT NULL,
                email           TEXT NOT NULL,
                phone           TEXT NOT NULL,
                contact_time    TEXT DEFAULT '',
                address         TEXT NOT NULL,
                suburb          TEXT DEFAULT '',
                city            TEXT DEFAULT '',
                property_type   TEXT DEFAULT 'House',
                bedrooms        INTEGER DEFAULT 0,
                bathrooms       INTEGER DEFAULT 0,
                garages         INTEGER DEFAULT 0,
                size_sqm        INTEGER DEFAULT 0,
                erf_size_sqm    INTEGER DEFAULT 0,
                asking_price    TEXT DEFAULT '',
                occupied        TEXT DEFAULT '',
                bond_outstanding TEXT DEFAULT '',
                notes           TEXT DEFAULT '',
                heard_from      TEXT DEFAULT '',
                status          TEXT DEFAULT 'New',
                agent_id        INTEGER,
                assigned_at     TIMESTAMP,
                pending_removal INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add agent_id and assigned_at to seller_leads if not exists
        try:
            db.execute("ALTER TABLE seller_leads ADD COLUMN agent_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            db.execute("ALTER TABLE seller_leads ADD COLUMN assigned_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            db.execute("ALTER TABLE seller_leads ADD COLUMN pending_removal INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        
         # Home price estimation leads
        db.execute("""
             CREATE TABLE IF NOT EXISTS Home_price_estimation_leads (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name       TEXT NOT NULL,
                email           TEXT NOT NULL,
                phone           TEXT NOT NULL,
                contact_time    TEXT DEFAULT '',
                address         TEXT NOT NULL,
                suburb          TEXT DEFAULT '',
                city            TEXT DEFAULT '',
                property_type   TEXT DEFAULT 'House',
                status          TEXT DEFAULT 'New',
                agent_id        INTEGER,
                assigned_at     TIMESTAMP,
                pending_removal INTEGER DEFAULT 0,
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Add agent_id and assigned_at to Home_price_estimation_leads if not exists
        try:
            db.execute("ALTER TABLE Home_price_estimation_leads ADD COLUMN agent_id INTEGER")
        except sqlite3.OperationalError:
            pass
        try:
            db.execute("ALTER TABLE Home_price_estimation_leads ADD COLUMN assigned_at TIMESTAMP")
        except sqlite3.OperationalError:
            pass
        try:
            db.execute("ALTER TABLE Home_price_estimation_leads ADD COLUMN pending_removal INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
         
         #property_images gallery table
        db.execute("""
            CREATE TABLE IF NOT EXISTS property_images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL,
                filename    TEXT    NOT NULL,
                sort_order  INTEGER DEFAULT 0,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Ensure the original admin account is always marked as admin
        db.execute("UPDATE agents SET is_admin = 1 WHERE username = 'admin'")
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


def admin_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if "agent_id" not in session:
            flash("Please log in to access that page.", "warning")
            return redirect(url_for("login"))
        agent = get_db().execute(
            "SELECT is_admin FROM agents WHERE id = ?", (session["agent_id"],)
        ).fetchone()
        if not agent or not agent["is_admin"]:
            flash("Admin access is required for that page.", "danger")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


@app.context_processor
def inject_globals():
    from datetime import datetime
    return {"now": datetime.utcnow()}


@app.context_processor
def inject_current_agent():
    agent_obj  = None
    is_admin   = False
    if "agent_id" in session:
        agent_obj = get_db().execute(
            "SELECT * FROM agents WHERE id = ?", (session["agent_id"],)
        ).fetchone()
        if agent_obj:
            is_admin = bool(agent_obj["is_admin"])
    return {
        "current_agent":          session.get("agent_username"),
        "current_agent_is_admin": is_admin,
        "current_agent_obj":      agent_obj,
    }


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
    db  = get_db()
    row = db.execute("""
        SELECT p.*,
               a.full_name     AS agent_name,
               a.phone         AS agent_profile_phone,
               a.email         AS agent_profile_email,
               a.profile_image AS agent_profile_image,
               a.bio           AS agent_bio
        FROM   properties p
        LEFT JOIN agents a ON p.agent_id = a.id
        WHERE  p.id = ?
    """, (prop_id,)).fetchone()
    if row is None:
        flash("Property not found.", "warning")
        return redirect(url_for("index"))

    prop = row
    price_numeric = parse_price_numeric(prop["price"])

    # Gallery images
    gallery = db.execute(
        "SELECT filename FROM property_images WHERE property_id = ? ORDER BY sort_order",
        (prop_id,),
    ).fetchall()
    if not gallery and prop["image_filename"]:
        gallery = [{"filename": prop["image_filename"]}]

    # Contact priority: agent profile → property fields → agency defaults
    raw_phone           = prop["agent_profile_phone"] or prop["agent_phone"] or "083 654 8010"
    agent_email         = prop["agent_profile_email"] or prop["agent_email"] or "lani@larney.co.za"
    agent_name          = prop["agent_name"] or "Larney Properties"
    agent_profile_image = prop["agent_profile_image"]
    agent_phone_wa      = to_wa_number(raw_phone)
    agent_phone_display = raw_phone

    return render_template("property.html", prop=prop, price_numeric=price_numeric,
                           agent_phone_wa=agent_phone_wa,
                           agent_phone_display=agent_phone_display,
                           agent_email=agent_email,
                           agent_name=agent_name,
                           agent_profile_image=agent_profile_image,
                           gallery=gallery)


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
        garages       = request.form.get("garages",       0)
        size_sqm      = request.form.get("size_sqm",      0)
        erf_size_sqm  = request.form.get("erf_size_sqm",  0)
        property_type = request.form.get("property_type", "House")
        status        = request.form.get("status",        "For Sale")
        is_featured   = 1 if request.form.get("is_featured") else 0
        errors = []
        if not title:    errors.append("Title is required.")
        if not price:    errors.append("Price is required.")
        if not location: errors.append("Location is required.")

        # Collect all images: pre-scraped + newly uploaded
        scraped_str = request.form.get("scraped_images", "").strip()
        all_images  = [f for f in scraped_str.split(",") if f.strip()]

        for file in request.files.getlist("images"):
            if file and file.filename:
                if not allowed_file(file.filename):
                    errors.append(f'"{file.filename}" is not an allowed image type.')
                else:
                    fname = secure_filename(file.filename)
                    file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
                    all_images.append(fname)

        image_filename = all_images[0] if all_images else None

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("upload.html", form=request.form)

        db = get_db()
        db_agent = db.execute(
            "SELECT phone, email FROM agents WHERE id = ?", (session["agent_id"],)
        ).fetchone()
        cur = db.execute(
            """
            INSERT INTO properties
                (title, price, location, description, image_filename,
                 bedrooms, bathrooms, garages, size_sqm, erf_size_sqm,
                 property_type, status, is_featured,
                 agent_phone, agent_email, agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, price, location, description, image_filename,
             bedrooms, bathrooms, garages, size_sqm, erf_size_sqm,
             property_type, status, is_featured,
             db_agent["phone"] or "", db_agent["email"] or "",
             session["agent_id"]),
        )
        prop_id = cur.lastrowid
        for i, fname in enumerate(all_images):
            db.execute(
                "INSERT INTO property_images (property_id, filename, sort_order) VALUES (?,?,?)",
                (prop_id, fname, i),
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
                bedrooms=?, bathrooms=?, size_sqm=?, property_type=?, status=?, is_featured=?
            WHERE id=?
            """,
            (title, price, location, description, image_filename,
             bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
             prop_id),
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

    # Delete all gallery images from disk
    gallery_rows = db.execute(
        "SELECT filename FROM property_images WHERE property_id = ?", (prop_id,)
    ).fetchall()
    deleted = set()
    for row in gallery_rows:
        fpath = os.path.join(app.config["UPLOAD_FOLDER"], row["filename"])
        if row["filename"] not in deleted and os.path.exists(fpath):
            os.remove(fpath)
            deleted.add(row["filename"])
    if prop["image_filename"] and prop["image_filename"] not in deleted:
        fpath = os.path.join(app.config["UPLOAD_FOLDER"], prop["image_filename"])
        if os.path.exists(fpath):
            os.remove(fpath)

    db.execute("DELETE FROM property_images WHERE property_id = ?", (prop_id,))
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


@app.route("/profile", methods=["GET", "POST"])
@login_required
def agent_profile():
    db    = get_db()
    agent = db.execute("SELECT * FROM agents WHERE id = ?", (session["agent_id"],)).fetchone()

    if request.method == "POST":
        action = request.form.get("action", "profile")

        if action == "password":
            current_pw  = request.form.get("current_password", "")
            new_pw      = request.form.get("new_password",      "").strip()
            confirm_pw  = request.form.get("confirm_password",  "").strip()

            if not check_password_hash(agent["password_hash"], current_pw):
                flash("Current password is incorrect.", "danger")
            elif len(new_pw) < 6:
                flash("New password must be at least 6 characters.", "danger")
            elif new_pw != confirm_pw:
                flash("Passwords do not match.", "danger")
            else:
                db.execute(
                    "UPDATE agents SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_pw), session["agent_id"]),
                )
                db.commit()
                flash("Password updated successfully.", "success")
            return redirect(url_for("agent_profile"))

        # action == "profile"
        full_name = request.form.get("full_name", "").strip()
        email     = request.form.get("email",     "").strip()
        phone     = request.form.get("phone",     "").strip()
        bio       = request.form.get("bio",       "").strip()

        profile_image = agent["profile_image"]
        file = request.files.get("profile_image")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Only PNG, JPG, JPEG, or WEBP images are allowed.", "danger")
                return redirect(url_for("agent_profile"))
            ext      = file.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"agent_{session['agent_id']}.{ext}")
            file.save(os.path.join(UPLOAD_FOLDER_AGENTS, filename))
            profile_image = filename

        db.execute(
            "UPDATE agents SET full_name=?, email=?, phone=?, bio=?, profile_image=? WHERE id=?",
            (full_name, email, phone, bio, profile_image, session["agent_id"]),
        )
        db.commit()
        flash("Profile updated successfully.", "success")
        return redirect(url_for("agent_profile"))

    return render_template("profile.html", agent=agent)


@app.route("/dashboard")
@login_required
def dashboard():
    db         = get_db()
    agent      = db.execute("SELECT * FROM agents WHERE id = ?", (session["agent_id"],)).fetchone()
    properties = db.execute(
        "SELECT * FROM properties WHERE agent_id = ? ORDER BY created_at DESC",
        (session["agent_id"],),
    ).fetchall()
    raw = db.execute("""
        SELECT
            COUNT(*)  AS total,
            SUM(CASE WHEN status = 'For Sale' THEN 1 ELSE 0 END) AS for_sale,
            SUM(CASE WHEN status = 'To Let'   THEN 1 ELSE 0 END) AS to_let
        FROM properties WHERE agent_id = ?
    """, (session["agent_id"],)).fetchone()
    stats = {
        "total":    raw["total"]    or 0,
        "for_sale": raw["for_sale"] or 0,
        "to_let":   raw["to_let"]   or 0,
    }
    return render_template("dashboard.html", agent=agent, properties=properties, stats=stats)


# ── Admin: agent management ────────────────────────────────────────────────────
@app.route("/admin/agents")
@admin_required
def admin_agents():
    db     = get_db()
    agents = db.execute("""
        SELECT a.*, COUNT(p.id) AS listing_count
        FROM   agents a
        LEFT JOIN properties p ON p.agent_id = a.id
        GROUP BY a.id
        ORDER BY a.is_admin DESC, a.created_at ASC
    """).fetchall()
    return render_template("admin_agents.html", agents=agents)


@app.route("/admin/agents/create", methods=["POST"])
@admin_required
def admin_create_agent():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm  = request.form.get("confirm_password", "")

    errors = []
    if not username:          errors.append("Username is required.")
    if len(password) < 6:     errors.append("Password must be at least 6 characters.")
    if password != confirm:   errors.append("Passwords do not match.")

    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("admin_agents"))

    db       = get_db()
    existing = db.execute("SELECT id FROM agents WHERE username = ?", (username,)).fetchone()
    if existing:
        flash(f'Username "{username}" is already taken.', "danger")
        return redirect(url_for("admin_agents"))

    db.execute(
        "INSERT INTO agents (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    db.commit()
    flash(f'Agent "{username}" created. They can now log in and complete their profile.', "success")
    return redirect(url_for("admin_agents"))


@app.route("/admin/agents/<int:target_id>/delete", methods=["POST"])
@admin_required
def admin_delete_agent(target_id):
    db    = get_db()
    agent = db.execute("SELECT * FROM agents WHERE id = ?", (target_id,)).fetchone()

    if not agent:
        flash("Agent not found.", "warning")
        return redirect(url_for("admin_agents"))
    if target_id == session["agent_id"]:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin_agents"))
    if agent["is_admin"]:
        flash("Admin accounts cannot be deleted.", "danger")
        return redirect(url_for("admin_agents"))

    # Remove profile image file if present
    if agent["profile_image"]:
        img_path = os.path.join(UPLOAD_FOLDER_AGENTS, agent["profile_image"])
        if os.path.exists(img_path):
            os.remove(img_path)

    # Unlink properties so listings remain but lose the agent association
    db.execute("UPDATE properties SET agent_id = NULL WHERE agent_id = ?", (target_id,))
    db.execute("DELETE FROM agents WHERE id = ?", (target_id,))
    db.commit()
    flash(f'Agent "{agent["username"]}" removed. Their listings remain active.', "success")
    return redirect(url_for("admin_agents"))


@app.route("/cma", methods=["GET", "POST"])
@login_required
def cma():
    if request.method == "GET":
        return render_template("CMA.html", form={})

    import tempfile, math
    from datetime import datetime
    from fpdf import FPDF
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    f = request.form
    errors = []

    def get(key, label):
        v = f.get(key, "").strip()
        if not v:
            errors.append(f"{label} is required.")
        return v

    client_name    = get("client_name",    "Client Surname")
    address        = get("address",        "Property Address")
    inflation_rate = get("inflation_rate", "Inflation Rate")
    repo_rate      = get("repo_rate",      "Repo Rate")
    subj_date      = get("subj_date",      "Subject: Date Last Sold")
    subj_price     = get("subj_price",     "Subject: Price Last Sold")

    comps = []
    for i in range(1, 4):
        cd = get(f"c{i}_date",  f"Comp {i}: Date Sold")
        cp = get(f"c{i}_price", f"Comp {i}: Price Sold")
        comps.append((cd, cp))

    if errors:
        for e in errors:
            flash(e, "danger")
        return render_template("CMA.html", form=f)

    try:
        inflation_rate = float(inflation_rate)
        repo_rate      = float(repo_rate)
        subj_price     = float(subj_price.replace(" ", "").replace(",", "").replace("R", ""))
        comps          = [(cd, float(cp.replace(" ", "").replace(",", "").replace("R", ""))) for cd, cp in comps]
    except ValueError:
        flash("All rate and price fields must be valid numbers.", "danger")
        return render_template("CMA.html", form=f)

    today = datetime.now()

    def years_since(date_str):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return (today - dt).days / 365.25

    def tvm(price, rate, years):
        return price * ((1 + rate / 100) ** years)

    subj_years = years_since(subj_date)
    adj_subject = tvm(subj_price, inflation_rate, subj_years)

    adj_comps = []
    for cd, cp in comps:
        adj_comps.append(tvm(cp, inflation_rate, years_since(cd)))

    avg_comps          = sum(adj_comps) / len(adj_comps)
    blended_value      = adj_subject * 0.4 + avg_comps * 0.6
    estimated_equity   = blended_value - subj_price
    date_str           = today.strftime("%d %B %Y")

    def fmt(n):
        return f"R {n:,.0f}".replace(",", " ")

    def safe(text):
        """Replace common Unicode chars with latin-1 equivalents for FPDF."""
        replacements = {
            "\u2014": "-",   # em dash
            "\u2013": "-",   # en dash
            "\u2018": "'",   # left single quote
            "\u2019": "'",   # right single quote
            "\u201c": '"',   # left double quote
            "\u201d": '"',   # right double quote
            "\u202f": " ",   # narrow no-break space
            "\u00a0": " ",   # no-break space
            "\u2192": "->",  # right arrow
        }
        for src, dst in replacements.items():
            text = text.replace(src, dst)
        return text.encode("latin-1", errors="replace").decode("latin-1")

    # ── Chart ──────────────────────────────────────────────────────────────
    NAVY_HEX   = "#1b2656"
    ORANGE_HEX = "#f15b22"
    MUSTARD_HEX = "#f7911d"

    fig, ax = plt.subplots(figsize=(7, 4))
    labels = ["Original\nPurchase", "Market Comps\n(Avg Adjusted)", "Blended\nValuation"]
    values = [subj_price, avg_comps, blended_value]
    colors = [NAVY_HEX, MUSTARD_HEX, ORANGE_HEX]
    bars = ax.bar(labels, values, color=colors, width=0.55)
    ax.set_title("Property Value Growth Trajectory", color=NAVY_HEX, fontweight="bold", fontsize=13)
    ax.set_ylabel("Value (ZAR)", color="#333")
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for bar in bars:
        h = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2, h + h * 0.02,
                f"R{h/1_000_000:.2f}m", ha="center", va="bottom",
                fontweight="bold", color=NAVY_HEX, fontsize=9)
    fig.tight_layout()

    tmp_dir   = tempfile.mkdtemp()
    chart_path = os.path.join(tmp_dir, "chart.png")
    fig.savefig(chart_path, dpi=180, transparent=True)
    plt.close(fig)

    # ── PDF ────────────────────────────────────────────────────────────────
    NAVY        = (27, 38, 86)
    ORANGE      = (241, 91, 34)
    MUSTARD_RGB = (247, 145, 29)
    LIGHT_TEXT  = (51, 51, 51)
    LIGHT_BG    = (245, 245, 245)

    class CmaPDF(FPDF):
        def header(self):
            self.set_font("Helvetica", "B", 20)
            self.set_text_color(*NAVY)
            self.cell(0, 10, "LARNEY PROPERTIES", new_x="LMARGIN", new_y="NEXT", align="C")
            self.set_font("Helvetica", "I", 11)
            self.set_text_color(*MUSTARD_RGB)
            self.cell(0, 6, "Home Price Estimation & Equity Analysis",
                      new_x="LMARGIN", new_y="NEXT", align="C")
            self.set_draw_color(*ORANGE)
            self.set_line_width(1.0)
            self.line(10, 30, 200, 30)
            self.ln(12)

        def footer(self):
            self.set_y(-25)
            self.set_draw_color(*NAVY)
            self.set_line_width(0.4)
            self.line(10, 270, 200, 270)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, "Prepared by Larney Properties - Let's review these metrics over coffee",
                      align="C")

    def section_header(pdf, title):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(0, 9, f"  {title}", new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(3)

    pdf = CmaPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    section_header(pdf, "1. BASELINE METRICS & MACRO INDICATORS")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*LIGHT_TEXT)
    pdf.cell(100, 6, safe(f"Property: {address}"))
    pdf.cell(90, 6, safe(f"Analysis Date: {date_str}"), align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(100, 6, safe(f"Client: {client_name}"))
    pdf.cell(90, 6, safe(f"Inflation: {inflation_rate}%  |  Repo Rate: {repo_rate}%"),
             align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    cur_y = pdf.get_y()
    pdf.image(chart_path, x=22, y=cur_y, w=165)
    pdf.set_y(cur_y + 88)
    pdf.ln(5)

    section_header(pdf, "2. MARKET TRIANGULATION (COMP-ADJUSTED)")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(*LIGHT_TEXT)
    pdf.set_fill_color(*LIGHT_BG)
    for i, ((cd, cp), adj) in enumerate(zip(comps, adj_comps), 1):
        pdf.cell(0, 8, safe(f"  Comp {i}: Sold {cd} for {fmt(cp)}  ->  Adjusted: {fmt(adj)}"),
                 new_x="LMARGIN", new_y="NEXT", fill=True)
        pdf.ln(1)
    pdf.ln(8)

    # Final valuation box
    box_y = pdf.get_y()
    pdf.set_fill_color(*LIGHT_BG)
    pdf.rect(10, box_y, 190, 46, "F")
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 8, "FINAL CALCULATED MARKET VALUE", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*ORANGE)
    pdf.cell(0, 12, safe(fmt(blended_value)), new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*MUSTARD_RGB)
    pdf.cell(0, 8, safe(f"Estimated Accrued Equity: {fmt(estimated_equity)}"),
             new_x="LMARGIN", new_y="NEXT", align="C")

    pdf_path = os.path.join(tmp_dir, f"Valuation_{client_name.replace(' ', '_')}.pdf")
    pdf.output(pdf_path)
    os.remove(chart_path)

    from flask import send_file
    return send_file(
        pdf_path,
        as_attachment=True,
        download_name=f"Larney_Valuation_{client_name.replace(' ', '_')}.pdf",
        mimetype="application/pdf",
    )


@app.route("/api/scrape", methods=["POST"])
@login_required
def scrape_listing():
    """Fetch a Property24 URL, parse it, save the image, return JSON."""
    import time, uuid, cloudscraper
    from bs4 import BeautifulSoup

    body = request.get_json() or {}
    url  = body.get("url", "").strip()
    if not url:
        return jsonify({"error": "URL is required"}), 400

    try:
        # ── Fetch page with Cloudscraper to bypass bot protection ──────
        scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )
        
        response = scraper.get(url, timeout=30)
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        result = {}

        # Title
        h1 = soup.find("h1")
        result["title"] = h1.get_text(strip=True) if h1 else ""

        # Price — strip to digits only
        price_div = soup.find("div", class_="p24_price")
        if price_div:
            result["price"] = re.sub(r"[^\d]", "", price_div.get_text())

        # Location
        addr = soup.find("address", class_="p24_address")
        result["location"] = addr.get_text(strip=True) if addr else ""

        # Bedrooms / Bathrooms
        for attr_title, key in [("Bedrooms", "bedrooms"), ("Bathrooms", "bathrooms")]:
            li = soup.find("li", attrs={"title": attr_title})
            if li:
                span = li.find("span")
                result[key] = re.sub(r"[^\d]", "", span.get_text()) if span else "0"

        # Floor size (m²) — prefer "Floor Size" row, fallback to erf
        size = "0"
        for kd in soup.find_all("div", class_="p24_propertyOverviewKey"):
            if "Floor Size" in kd.get_text():
                rd = kd.find_next_sibling("div", class_="p24_propertyOverviewResult")
                if rd:
                    info = rd.find("div", class_="p24_info")
                    if info:
                        size = re.sub(r"[^\d]", "", info.get_text().split("m")[0]) or "0"
                break
        if size == "0":
            li_sz = soup.find("li", class_="p24_size")
            if li_sz:
                sp = li_sz.find("span")
                if sp:
                    size = re.sub(r"[^\d\s]", "", sp.get_text().split("m")[0]).replace(" ", "") or "0"
        result["size_sqm"] = size

        # Property type
        prop_type = "House"
        for kd in soup.find_all("div", class_="p24_propertyOverviewKey"):
            if "Type of Property" in kd.get_text():
                rd = kd.find_next_sibling("div", class_="p24_propertyOverviewResult")
                if rd:
                    info = rd.find("div", class_="p24_info")
                    if info:
                        prop_type = info.get_text(strip=True)
                break
        result["property_type"] = prop_type

        # Garages
        garage_li = soup.find("li", attrs={"title": "Garages"})
        if garage_li:
            sp = garage_li.find("span")
            result["garages"] = re.sub(r"[^\d]", "", sp.get_text()) if sp else "0"

        # Erf size
        erf_size = "0"
        for kd in soup.find_all("div", class_="p24_propertyOverviewKey"):
            if "Erf Size" in kd.get_text():
                rd = kd.find_next_sibling("div", class_="p24_propertyOverviewResult")
                if rd:
                    info = rd.find("div", class_="p24_info")
                    if info:
                        erf_size = re.sub(r"[^\d]", "", info.get_text().split("m")[0]) or "0"
                break
        result["erf_size_sqm"] = erf_size

        # Rates & levies — collect for description appendix
        extras = {}
        for label in ["Rates and Taxes", "Levy"]:
            for kd in soup.find_all("div", class_="p24_propertyOverviewKey"):
                if label in kd.get_text():
                    rd = kd.find_next_sibling("div", class_="p24_propertyOverviewResult")
                    if rd:
                        info = rd.find("div", class_="p24_info")
                        if info:
                            extras[label] = info.get_text(strip=True)
                    break

        # Status from URL path
        result["status"] = "To Let" if ("/to-let/" in url or "/to-rent/" in url) else "For Sale"

        # Description + features list
        about = soup.find("section", class_="p24_listingAbout")
        desc_parts = []
        if about:
            paras = [p.get_text(strip=True) for p in about.find_all("p") if p.get_text(strip=True)]
            desc_parts.extend(paras)

        # Feature tags (pool, garden, pet friendly etc.)
        features = []
        for tag in soup.find_all("div", class_="p24_featureTagItem"):
            txt = tag.get_text(strip=True)
            if txt:
                features.append(txt)
        if not features:
            for li in soup.find_all("li", class_="p24_featureItem"):
                txt = li.get_text(strip=True)
                if txt:
                    features.append(txt)
        if features:
            desc_parts.append("Features: " + " • ".join(features))
        if extras:
            for k, v in extras.items():
                desc_parts.append(f"{k}: {v}")

        result["description"] = "\n\n".join(desc_parts)

        # Download all gallery images (up to 10)
        img_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.property24.com/",
        }
        saved_images = []
        gallery_divs = soup.find_all("div", class_="p24_galleryImageHolder")
        for gdiv in gallery_divs[:10]:
            raw_url   = gdiv.get("data-image-url") or ""
            image_url = re.sub(r"/(Ensure|Crop)\w+$", "", raw_url) if raw_url else raw_url
            if not image_url:
                continue
            try:
                img_resp = requests.get(image_url, headers=img_headers, timeout=20)
                if img_resp.status_code == 200:
                    ct  = img_resp.headers.get("content-type", "")
                    ext = "webp" if "webp" in ct else ("png" if "png" in ct else "jpg")
                    filename  = f"scraped_{uuid.uuid4().hex[:10]}.{ext}"
                    save_path = os.path.join(UPLOAD_FOLDER, filename)
                    with open(save_path, "wb") as fh:
                        fh.write(img_resp.content)
                    saved_images.append(filename)
            except Exception:
                pass

        if saved_images:
            result["scraped_images"] = ",".join(saved_images)
            result["scraped_image"]  = saved_images[0]
            result["image_preview"]  = url_for("static", filename=f"uploads/{saved_images[0]}")
            result["image_previews"] = [
                url_for("static", filename=f"uploads/{f}") for f in saved_images
            ]

        return jsonify(result)

    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/sell", methods=["GET", "POST"])
def sell():
    if request.method == "POST":
        full_name        = request.form.get("full_name",        "").strip()
        email            = request.form.get("email",            "").strip()
        phone            = request.form.get("phone",            "").strip()
        contact_time     = request.form.get("contact_time",     "").strip()
        address          = request.form.get("address",          "").strip()
        suburb           = request.form.get("suburb",           "").strip()
        city             = request.form.get("city",             "").strip()
        property_type    = request.form.get("property_type",    "House")
        bedrooms         = request.form.get("bedrooms",         0)
        bathrooms        = request.form.get("bathrooms",        0)
        garages          = request.form.get("garages",          0)
        size_sqm         = request.form.get("size_sqm",         0)
        erf_size_sqm     = request.form.get("erf_size_sqm",     0)
        asking_price     = request.form.get("asking_price",     "").strip()
        occupied         = request.form.get("occupied",         "").strip()
        bond_outstanding = request.form.get("bond_outstanding", "").strip()
        notes            = request.form.get("notes",            "").strip()
        heard_from       = request.form.get("heard_from",       "").strip()

        errors = []
        if not full_name: errors.append("Full name is required.")
        if not email:     errors.append("Email address is required.")
        if not phone:     errors.append("Phone number is required.")
        if not address:   errors.append("Property address is required.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("sell.html", form=request.form)

        from datetime import datetime, timezone, timedelta
        sast = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        db.execute("""
            INSERT INTO seller_leads
                (full_name, email, phone, contact_time, address, suburb, city,
                 property_type, bedrooms, bathrooms, garages, size_sqm, erf_size_sqm,
                 asking_price, occupied, bond_outstanding, notes, heard_from, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (full_name, email, phone, contact_time, address, suburb, city,
              property_type, bedrooms, bathrooms, garages, size_sqm, erf_size_sqm,
              asking_price, occupied, bond_outstanding, notes, heard_from, sast))
        db.commit()
        flash("Thank you! We will be in touch with you shortly.", "success")

        # Notify admin about new seller lead
        admin_email = app.config["ADMIN_EMAIL"]
        subject     = f"New Seller Lead: {full_name} ({property_type} at {address})"
        body        = (f"A new seller lead has been submitted:\n\n"
                       f"Name: {full_name}\n"
                       f"Email: {email}\n"
                       f"Phone: {phone}\n"
                       f"Contact Time: {contact_time or 'Any time'}\n"
                       f"Address: {address}, {suburb}, {city}\n"
                       f"Property Type: {property_type}\n"
                       f"Bedrooms: {bedrooms}\n"
                       f"Bathrooms: {bathrooms}\n"
                       f"Garages: {garages}\n"
                       f"Size (sqm): {size_sqm}\n"
                       f"Erf Size (sqm): {erf_size_sqm}\n"
                       f"Asking Price: {asking_price}\n"
                       f"Occupied: {occupied}\n"
                       f"Bond Outstanding: {bond_outstanding}\n"
                       f"Notes: {notes}\n"
                       f"Heard From: {heard_from}\n"
                       f"Submitted On: {sast}\n"
                       f"\nView lead in admin panel: {url_for('admin_leads', _external=True)}")
        send_email(admin_email, subject, body)

        return redirect(url_for("sell"))

    return render_template("sell.html", form={})

@app.route("/HPE", methods=["GET", "POST"])
def HPE():
    if request.method == "POST":
        full_name        = request.form.get("full_name",        "").strip()
        email            = request.form.get("email",            "").strip()
        phone            = request.form.get("phone",            "").strip()
        contact_time     = request.form.get("contact_time",     "").strip()
        address          = request.form.get("address",          "").strip()
        suburb           = request.form.get("suburb",           "").strip()
        city             = request.form.get("city",             "").strip()
        property_type    = request.form.get("property_type",    "House")
        status           = "New" # Define status as "New"

        errors = []
        if not full_name: errors.append("Full name is required.")
        if not email:     errors.append("Email address is required.")
        if not phone:     errors.append("Phone number is required.")
        if not address:   errors.append("Property address is required.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("Home_price_estimation.html", form=request.form)

        from datetime import datetime, timezone, timedelta
        sast = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S")
        db = get_db()
        db.execute("""
            INSERT INTO Home_price_estimation_leads
                (full_name, email, phone, contact_time, address, suburb, city,
                 property_type, status, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (full_name, email, phone, contact_time, address, suburb, city,
              property_type, status, sast))
        db.commit()
        flash("Thank you! We will be in touch with you shortly.", "success")

        # Notify admin about new HPE lead
        admin_email = app.config["ADMIN_EMAIL"]
        subject     = f"New HPE Lead: {full_name} ({property_type} at {address})"
        body        = (f"A new Home Price Estimation lead has been submitted:\n\n"
                       f"Name: {full_name}\n"
                       f"Email: {email}\n"
                       f"Phone: {phone}\n"
                       f"Contact Time: {contact_time or 'Any time'}\n"
                       f"Address: {address}, {suburb}, {city}\n"
                       f"Property Type: {property_type}\n"
                       f"Submitted On: {sast}\n"
                       f"\nView lead in admin panel: {url_for('admin_leads', _external=True)}")
        send_email(admin_email, subject, body)

        return redirect(url_for("HPE"))

    return render_template("Home_price_estimation.html", form={})


@app.route("/admin/leads")
@admin_required
def admin_leads():
    db    = get_db()
    leads = db.execute(
        """
        SELECT sl.id, sl.full_name, sl.email, sl.phone, sl.contact_time, sl.address, sl.suburb, sl.city, sl.property_type, sl.status, sl.created_at, 'seller' AS lead_type, sl.agent_id, a.full_name AS assigned_agent_name, sl.pending_removal
        FROM seller_leads sl
        LEFT JOIN agents a ON sl.agent_id = a.id
        UNION ALL
        SELECT hpe.id, hpe.full_name, hpe.email, hpe.phone, hpe.contact_time, hpe.address, hpe.suburb, hpe.city, hpe.property_type, hpe.status, hpe.created_at, 'hpe' AS lead_type, hpe.agent_id, a.full_name AS assigned_agent_name, hpe.pending_removal
        FROM Home_price_estimation_leads hpe
        LEFT JOIN agents a ON hpe.agent_id = a.id
        ORDER BY 11 DESC
        """
    ).fetchall()
    
    agents = db.execute("SELECT id, full_name, email FROM agents ORDER BY full_name").fetchall()
    return render_template("admin_leads.html", leads=leads, agents=agents)


@app.route("/admin/leads/<int:lead_id>/status", methods=["POST"])
@admin_required
def admin_lead_status(lead_id):
    status    = request.form.get("status", "New")
    lead_type = request.form.get("lead_type") # Get lead_type from form
    db = get_db()
    if lead_type == 'seller':
        db.execute("UPDATE seller_leads SET status = ? WHERE id = ?", (status, lead_id))
    elif lead_type == 'hpe':
        db.execute("UPDATE Home_price_estimation_leads SET status = ? WHERE id = ?", (status, lead_id))
    db.commit()
    return redirect(url_for("admin_leads"))


@app.route("/admin/leads/<int:lead_id>/assign", methods=["POST"])
@admin_required
def admin_assign_lead(lead_id):
    agent_id  = request.form.get("agent_id")
    lead_type = request.form.get("lead_type")
    db        = get_db()
    
    # Get current time for assigned_at timestamp
    from datetime import datetime, timezone, timedelta
    sast = datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d %H:%M:%S")

    agent_data = None
    if agent_id: # If an agent was selected (not 'Unassigned')
        agent_data = db.execute(
            "SELECT full_name, email FROM agents WHERE id = ?", (agent_id,)
        ).fetchone()

    lead_details = None
    if lead_type == 'seller':
        lead_details = db.execute(
            "SELECT * FROM seller_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if lead_details:
            db.execute(
                "UPDATE seller_leads SET agent_id = ?, assigned_at = ? WHERE id = ?",
                (agent_id if agent_id else None, sast if agent_id else None, lead_id),
            )
            db.commit()
            flash(f"Seller lead '{lead_details['full_name']}' assigned successfully.", "success")
            
            if agent_data:
                subject = f"New Seller Lead Assigned: {lead_details['full_name']}"
                body = (f"Hello {agent_data['full_name']},\n\n"
                        f"A new seller lead has been assigned to you:\n\n"
                        f"Client Name: {lead_details['full_name']}\n"
                        f"Client Email: {lead_details['email']}\n"
                        f"Client Phone: {lead_details['phone']}\n"
                        f"Property Address: {lead_details['address']}\n"
                        f"Property Type: {lead_details['property_type']}\n"
                        f"Status: {lead_details['status']}\n"
                        f"Assigned On: {sast}\n"
                        f"\nLog in to the admin panel to view full details and manage this lead: {url_for('admin_leads', _external=True)}")
                send_email(agent_data['email'], subject, body)

    elif lead_type == 'hpe':
        lead_details = db.execute(
            "SELECT * FROM Home_price_estimation_leads WHERE id = ?", (lead_id,)
        ).fetchone()
        if lead_details:
            db.execute(
                "UPDATE Home_price_estimation_leads SET agent_id = ?, assigned_at = ? WHERE id = ?",
                (agent_id if agent_id else None, sast if agent_id else None, lead_id),
            )
            db.commit()
            flash(f"Home Price Estimation lead '{lead_details['full_name']}' assigned successfully.", "success")

            if agent_data:
                subject = f"New HPE Lead Assigned: {lead_details['full_name']}"
                body = (f"Hello {agent_data['full_name']},\n\n"
                        f"A new Home Price Estimation lead has been assigned to you:\n\n"
                        f"Client Name: {lead_details['full_name']}\n"
                        f"Client Email: {lead_details['email']}\n"
                        f"Client Phone: {lead_details['phone']}\n"
                        f"Property Address: {lead_details['address']}\n"
                        f"Property Type: {lead_details['property_type']}\n"
                        f"Status: {lead_details['status']}\n"
                        f"Assigned On: {sast}\n"
                        f"\nLog in to the admin panel to view full details and manage this lead: {url_for('admin_leads', _external=True)}")
                send_email(agent_data['email'], subject, body)

    else:
        flash("Invalid lead type specified for assignment.", "danger")

    return redirect(url_for("admin_leads"))


@app.route("/admin/leads/<int:lead_id>/confirm_deletion", methods=["POST"])
@admin_required
def admin_confirm_deletion(lead_id):
    lead_type = request.form.get("lead_type")
    db = get_db()
    lead_name = ""

    table_name = ""
    if lead_type == 'seller':
        table_name = "seller_leads"
    elif lead_type == 'hpe':
        table_name = "Home_price_estimation_leads"
    else:
        flash("Invalid lead type specified for deletion.", "danger")
        return redirect(url_for("admin_leads"))

    lead = db.execute(f"SELECT full_name FROM {table_name} WHERE id = ?", (lead_id,)).fetchone()
    if lead:
        lead_name = lead["full_name"]
        db.execute(f"DELETE FROM {table_name} WHERE id = ?", (lead_id,))
        db.commit()
        flash(f"{lead_type.capitalize()} lead '{lead_name}' successfully deleted (confirmed by admin).", "success")
    else:
        flash(f"{lead_type.capitalize()} lead not found.", "danger")

    return redirect(url_for("admin_leads"))


@app.route("/admin/leads/<int:lead_id>/unmark_removal", methods=["POST"])
@admin_required
def admin_unmark_removal(lead_id):
    lead_type = request.form.get("lead_type")
    db = get_db()

    table_name = ""
    if lead_type == 'seller':
        table_name = "seller_leads"
    elif lead_type == 'hpe':
        table_name = "Home_price_estimation_leads"
    else:
        flash("Invalid lead type.", "danger")
        return redirect(url_for("admin_leads"))

    lead = db.execute(f"SELECT full_name FROM {table_name} WHERE id = ?", (lead_id,)).fetchone()
    if lead:
        db.execute(f"UPDATE {table_name} SET pending_removal = 0 WHERE id = ?", (lead_id,))
        db.commit()
        flash(f"Lead '{lead['full_name']}' unmarked for removal.", "info")
    else:
        flash(f"{lead_type.capitalize()} lead not found.", "danger")

    return redirect(url_for("admin_leads"))


@app.route("/admin/leads/<int:lead_id>/delete", methods=["POST"])
@admin_required
def admin_delete_lead(lead_id):
    lead_type = request.form.get("lead_type")
    db = get_db()
    lead_name = "" # To store the name of the deleted lead

    if lead_type == 'seller':
        lead = db.execute("SELECT full_name FROM seller_leads WHERE id = ?", (lead_id,)).fetchone()
        if lead:
            lead_name = lead["full_name"]
            db.execute("DELETE FROM seller_leads WHERE id = ?", (lead_id,))
            db.commit()
            flash(f"Seller lead '{lead_name}' deleted successfully.", "success")
        else:
            flash("Seller lead not found.", "danger")
    elif lead_type == 'hpe':
        lead = db.execute("SELECT full_name FROM Home_price_estimation_leads WHERE id = ?", (lead_id,)).fetchone()
        if lead:
            lead_name = lead["full_name"]
            db.execute("DELETE FROM Home_price_estimation_leads WHERE id = ?", (lead_id,))
            db.commit()
            flash(f"Home Price Estimation lead '{lead_name}' deleted successfully.", "success")
        else:
            flash("Home Price Estimation lead not found.", "danger")
    else:
        flash("Invalid lead type specified for deletion.", "danger")

    return redirect(url_for("admin_leads"))


@app.route("/agents")
def agents_page():
    db = get_db()
    agents_list = db.execute(
        "SELECT id, full_name, bio, phone, email, profile_image FROM agents ORDER BY full_name"
    ).fetchall()
    return render_template("agents.html", agents=agents_list)


@app.route("/agent/leads")
@login_required
def agent_leads():
    db = get_db()
    agent_id = session.get("agent_id")

    leads = db.execute(
        """
        SELECT sl.id, sl.full_name, sl.email, sl.phone, sl.contact_time, sl.address, sl.suburb, sl.city, sl.property_type, sl.status, sl.created_at, sl.pending_removal, 'seller' AS lead_type, sl.agent_id, a.full_name AS assigned_agent_name
        FROM seller_leads sl
        LEFT JOIN agents a ON sl.agent_id = a.id
        WHERE sl.agent_id = ?
        UNION ALL
        SELECT hpe.id, hpe.full_name, hpe.email, hpe.phone, hpe.contact_time, hpe.address, hpe.suburb, hpe.city, hpe.property_type, hpe.status, hpe.created_at, hpe.pending_removal, 'hpe' AS lead_type, hpe.agent_id, a.full_name AS assigned_agent_name
        FROM Home_price_estimation_leads hpe
        LEFT JOIN agents a ON hpe.agent_id = a.id
        WHERE hpe.agent_id = ?
        ORDER BY 11 DESC
        """,
        (agent_id, agent_id)
    ).fetchall()

    # Calculate statistics for the agent's leads
    stats = {
        "total_assigned": len(leads),
        "new_leads":      0,
        "contacted_leads": 0,
        "mandated_leads":  0,
        "closed_leads":    0,
        "not_interested_leads": 0,
        "pending_removal": 0,
    }
    for lead in leads:
        if lead['status'] == 'New':
            stats["new_leads"] += 1
        elif lead['status'] == 'Contacted':
            stats["contacted_leads"] += 1
        elif lead['status'] == 'Mandated':
            stats["mandated_leads"] += 1
        elif lead['status'] == 'Closed':
            stats["closed_leads"] += 1
        elif lead['status'] == 'Not Interested':
            stats["not_interested_leads"] += 1
        if lead['pending_removal'] == 1:
            stats["pending_removal"] += 1
    
    return render_template("agent_leads.html", leads=leads, stats=stats)


@app.route("/agent/leads/<int:lead_id>/status", methods=["POST"])
@login_required
def agent_lead_status(lead_id):
    status    = request.form.get("status", "New")
    lead_type = request.form.get("lead_type")
    agent_id  = session.get("agent_id")
    db        = get_db()

    table_name = ""
    if lead_type == 'seller':
        table_name = "seller_leads"
    elif lead_type == 'hpe':
        table_name = "Home_price_estimation_leads"
    else:
        flash("Invalid lead type.", "danger")
        return redirect(url_for("agent_leads"))

    # Verify lead ownership
    lead = db.execute(
        f"SELECT id, full_name FROM {table_name} WHERE id = ? AND agent_id = ?",
        (lead_id, agent_id)
    ).fetchone()

    if not lead:
        flash("Lead not found or not assigned to you.", "danger")
        return redirect(url_for("agent_leads"))

    db.execute(
        f"UPDATE {table_name} SET status = ? WHERE id = ?",
        (status, lead_id)
    )
    db.commit()
    flash(f"{lead['full_name']}'s status updated to '{status}'.", "success")
    return redirect(url_for("agent_leads"))


    return redirect(url_for("agent_leads"))


@app.route("/agent/leads/<int:lead_id>/mark_removal", methods=["POST"])
@login_required
def agent_mark_removal(lead_id):
    lead_type = request.form.get("lead_type")
    agent_id  = session.get("agent_id")
    db        = get_db()

    table_name = ""
    if lead_type == 'seller':
        table_name = "seller_leads"
    elif lead_type == 'hpe':
        table_name = "Home_price_estimation_leads"
    else:
        flash("Invalid lead type.", "danger")
        return redirect(url_for("agent_leads"))

    # Verify lead ownership
    lead = db.execute(
        f"SELECT id, full_name FROM {table_name} WHERE id = ? AND agent_id = ?",
        (lead_id, agent_id)
    ).fetchone()

    if not lead:
        flash("Lead not found or not assigned to you.", "danger")
        return redirect(url_for("agent_leads"))

    db.execute(
        f"UPDATE {table_name} SET pending_removal = 1 WHERE id = ?",
        (lead_id,)
    )
    db.commit()
    flash(f"Lead '{lead['full_name']}' marked for removal. An admin will review your request.", "info")
    return redirect(url_for("agent_leads"))


    return redirect(url_for("agent_leads"))


@app.route("/agent/leads/<int:lead_id>/unassign", methods=["POST"])
@login_required
def agent_unassign_lead(lead_id):
    lead_type = request.form.get("lead_type")
    agent_id  = session.get("agent_id")
    db        = get_db()
    
    table_name = ""
    if lead_type == 'seller':
        table_name = "seller_leads"
    elif lead_type == 'hpe':
        table_name = "Home_price_estimation_leads"
    else:
        flash("Invalid lead type.", "danger")
        return redirect(url_for("agent_leads"))

    # Verify lead ownership
    lead = db.execute(
        f"SELECT id, full_name FROM {table_name} WHERE id = ? AND agent_id = ?",
        (lead_id, agent_id)
    ).fetchone()

    if not lead:
        flash("Lead not found or not assigned to you.", "danger")
        return redirect(url_for("agent_leads"))

    db.execute(
        f"UPDATE {table_name} SET agent_id = NULL, assigned_at = NULL, pending_removal = 0 WHERE id = ?",
        (lead_id,)
    )
    db.commit()
    flash(f"Lead '{lead['full_name']}' has been unassigned and returned to the admin pool.", "info")

    # Notify admin about unassigned lead
    admin_email = app.config["ADMIN_EMAIL"]
    current_agent = session.get("agent_username", "An Agent")
    subject     = f"Lead Unassigned: {lead['full_name']} ({lead_type.capitalize()})"
    body        = (f"{current_agent} has unassigned the lead '{lead['full_name']}' "
                   f"({lead_type.capitalize()} lead ID: {lead_id}).\n\n"
                   f"The lead has been returned to the admin pool and is now available for re-assignment.\n\n"
                   f"View lead in admin panel: {url_for('admin_leads', _external=True)}")
    send_email(admin_email, subject, body)

    return redirect(url_for("agent_leads"))


@app.route("/popia")
def popia():
    return render_template("popia.html")


@app.route("/paipa")
def paipa():
    return render_template("paipa.html")


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
    os.makedirs(UPLOAD_FOLDER,        exist_ok=True)
    os.makedirs(UPLOAD_FOLDER_AGENTS, exist_ok=True)
    init_db()
    migrate_db()
    app.run(debug=True, host='0.0.0.0', port=64000)
