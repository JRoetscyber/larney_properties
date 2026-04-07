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
UPLOAD_FOLDER        = os.path.join(BASE_DIR, "static", "uploads")
UPLOAD_FOLDER_AGENTS = os.path.join(BASE_DIR, "static", "uploads", "agents")
ALLOWED_EXTENSIONS   = {"png", "jpg", "jpeg", "webp"}

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
                           agent_profile_image=agent_profile_image)


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
        # Pull contact info from agent's current profile
        db_agent = db.execute(
            "SELECT phone, email FROM agents WHERE id = ?", (session["agent_id"],)
        ).fetchone()
        db.execute(
            """
            INSERT INTO properties
                (title, price, location, description, image_filename,
                 bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
                 agent_phone, agent_email, agent_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, price, location, description, image_filename,
             bedrooms, bathrooms, size_sqm, property_type, status, is_featured,
             db_agent["phone"] or "", db_agent["email"] or "",
             session["agent_id"]),
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
