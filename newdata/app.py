import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from urllib.parse import quote_plus

import certifi
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError
from bson import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_mail import Mail, Message

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

# ============================================================
# EMAIL CONFIGURATION
# ============================================================
# Keep credentials in .env. Never hard-code your Gmail password.
app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "True").lower() == "true"
app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "False").lower() == "true"
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "").strip()
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get(
    "MAIL_DEFAULT_SENDER",
    app.config["MAIL_USERNAME"]
).strip()

mail = Mail(app)

MONGO_DB = os.environ.get("MONGO_DB", "promptverse").strip()
MONGO_HOST = os.environ.get("MONGO_HOST", "").strip()
MONGO_USERNAME = os.environ.get("MONGO_USERNAME", "").strip()
MONGO_PASSWORD = os.environ.get("MONGO_PASSWORD", "")
MONGO_URI = os.environ.get("MONGO_URI", "").strip()


if not MONGO_URI and MONGO_HOST and MONGO_USERNAME and MONGO_PASSWORD:
    MONGO_URI = (
        "mongodb+srv://"
        f"{quote_plus(MONGO_USERNAME)}:{quote_plus(MONGO_PASSWORD)}"
        f"@{MONGO_HOST}/{MONGO_DB}"
        "?retryWrites=true&w=majority&authSource=admin"
    )

ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp", "gif"}

CATEGORIES = [
    "Cinematic", "Photography", "Anime", "Fashion",
    "Fantasy", "Product", "Architecture", "3D"
]

MODELS = [
    "Midjourney", "Flux", "Stable Diffusion",
    "Sora", "Veo", "DALL-E", "Gemini"
]

PROMPT_TYPES = [
    "image",
    "video",
    "slides",
    "sheets",
    "webpage",
    "document"
]

USE_CASES = [
    "Profile Avatar", "Social Media Post", "Infographic / Edu Visual",
    "YouTube Thumbnail", "Comic / Storyboard", "Product Marketing",
    "E-commerce Main Image", "Game Asset", "Poster / Flyer",
    "App / Web Design"
]

STYLES = [
    "Photography", "Cinematic / Film Still", "Anime / Manga",
    "Illustration", "Sketch / Line Art", "Comic / Graphic Novel",
    "3D Render", "Chibi / Q-Style", "Isometric", "Pixel Art",
    "Oil Painting", "Watercolor", "Ink / Chinese Style",
    "Retro / Vintage", "Cyberpunk / Sci-Fi", "Minimalism"
]

SUBJECTS = [
    "Portrait / Selfie", "Influencer / Model", "Character",
    "Group / Couple", "Product", "Food / Drink", "Fashion Item",
    "Animal / Creature", "Vehicle", "Architecture / Interior",
    "Landscape / Nature", "Cityscape / Street", "Diagram / Chart",
    "Text / Typography", "Abstract / Background"
]

client = None
db = None


def utcnow():
    return datetime.now(timezone.utc)


def now_iso():
    return utcnow().isoformat()


def get_db():
    global client, db

    if db is not None:
        return db

    if not MONGO_URI:
        raise RuntimeError(
            "MongoDB configuration is missing. Put MONGO_HOST, "
            "MONGO_USERNAME and MONGO_PASSWORD in .env, or set MONGO_URI."
        )

    try:
        client = MongoClient(
            MONGO_URI,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=15000,
            connectTimeoutMS=15000,
            socketTimeoutMS=15000,
            retryWrites=True,
            appname="PromptVerse",
        )
        client.admin.command("ping")
        db = client[MONGO_DB]
        ensure_indexes()
        return db
    except Exception as exc:
        raise RuntimeError(
            "MongoDB Atlas connection/authentication failed. "
            "Check Database Access username/password and Network Access. "
            f"Original error: {exc}"
        ) from exc


def ensure_indexes():
    d = db
    d.users.create_index([("email", ASCENDING)], unique=True)
    d.admins.create_index([("email", ASCENDING)], unique=True)
    d.prompts.create_index([("created_at", DESCENDING)])
    d.prompts.create_index([("author_id", ASCENDING), ("created_at", DESCENDING)])
    d.prompts.create_index([("category", ASCENDING)])
    d.prompts.create_index([("model", ASCENDING)])
    d.prompts.create_index([("prompt_type", ASCENDING)])
    d.prompts.create_index([("use_case", ASCENDING)])
    d.prompts.create_index([("style", ASCENDING)])
    d.prompts.create_index([("subject", ASCENDING)])
    d.prompts.create_index([("tags", ASCENDING)])
    d.likes.create_index(
        [("user_id", ASCENDING), ("prompt_id", ASCENDING)], unique=True
    )
    d.saves.create_index(
        [("user_id", ASCENDING), ("prompt_id", ASCENDING)], unique=True
    )
    d.views.create_index([("prompt_id", ASCENDING), ("created_at", DESCENDING)])
    d.copy_events.create_index([("prompt_id", ASCENDING), ("created_at", DESCENDING)])
    d.categories.create_index([("name", ASCENDING)], unique=True)
    d.password_resets.create_index([("token", ASCENDING)], unique=True)
    d.password_resets.create_index([("expires_at", ASCENDING)])
    d.email_otps.create_index([("email", ASCENDING), ("created_at", DESCENDING)])
    d.email_otps.create_index([("expires_at", ASCENDING)])
    d.admin_logs.create_index([("created_at", DESCENDING)])
    d.admin_logs.create_index([("admin_id", ASCENDING), ("created_at", DESCENDING)])


def init_db():
    d = get_db()

    category_data = [
        ("Cinematic", "🎬"), ("Photography", "📷"), ("Anime", "🎨"),
        ("Fashion", "👗"), ("Fantasy", "🧙"), ("Product", "📦"),
        ("Architecture", "🏛️"), ("3D", "🧊")
    ]

    for name, emoji in category_data:
        d.categories.update_one(
            {"name": name},
            {"$setOnInsert": {
                "name": name,
                "emoji": emoji,
                "created_at": now_iso()
            }},
            upsert=True
        )


def parse_tags(raw):
    if isinstance(raw, list):
        return [
            str(x).strip().lower().lstrip("#")
            for x in raw if str(x).strip()
        ]
    return [
        x.strip().lower().lstrip("#")
        for x in re.split(r"[,\n]+", raw or "")
        if x.strip()
    ]


def user_doc():
    uid = session.get("user_id")
    if not uid:
        return None

    try:
        oid = ObjectId(uid)
    except Exception:
        session.pop("user_id", None)
        return None

    try:
        return get_db().users.find_one({"_id": oid})
    except Exception:
        session.pop("user_id", None)
        return None


def user_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not user_doc():
            session["next_after_login"] = request.url
            flash("Please sign in to continue.", "error")
            return redirect(url_for("user_login"))
        return fn(*args, **kwargs)
    return wrapper


def serialize(doc):
    if not doc:
        return None

    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    d["tags_list"] = parse_tags(d.get("tags", []))

    created = d.get("created_at")
    try:
        dt = datetime.fromisoformat(created)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except Exception:
        dt = utcnow()

    age_days = max((utcnow() - dt).total_seconds() / 86400, 0)
    decay = max(0.15, 1 / (1 + age_days / 7))
    d["score"] = round(
        (
            d.get("likes", 0) * 4
            + d.get("copies", 0) * 3
            + d.get("views", 0)
            + d.get("saves", 0) * 3
        ) * decay,
        2
    )
    d["is_new"] = dt >= utcnow() - timedelta(days=7)
    d["hot"] = d["score"] >= 1500 or d.get("likes", 0) >= 1000
    return d


def prompt_by_id(pid):
    try:
        return get_db().prompts.find_one({"_id": ObjectId(pid)})
    except Exception:
        return None


def prompt_form_context():
    d = get_db()
    categories = list(d.categories.find().sort("name", ASCENDING))
    return {
        "models": MODELS,
        "prompt_types": PROMPT_TYPES,
        "use_cases": USE_CASES,
        "styles": STYLES,
        "subjects": SUBJECTS,
        "categories": categories,
    }


@app.context_processor
def inject_globals():
    d = get_db()
    return {
        "current_user": user_doc(),
        "models": MODELS,
        "prompt_types": PROMPT_TYPES,
        "use_cases": USE_CASES,
        "styles": STYLES,
        "subjects": SUBJECTS,
        "categories": list(d.categories.find().sort("name", ASCENDING)),
        "datetime": datetime,
        "timezone": timezone,
    }



# ============================================================
# ADMIN AUTHENTICATION
# ============================================================

def admin_doc():
    aid = session.get("admin_id")
    if not aid:
        return None

    try:
        oid = ObjectId(aid)
    except Exception:
        session.pop("admin_id", None)
        return None

    try:
        return get_db().admins.find_one({"_id": oid})
    except Exception:
        session.pop("admin_id", None)
        return None


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not admin_doc():
            session["next_after_admin_login"] = request.url
            flash("Please sign in as an administrator.", "error")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper


def create_default_admin():
    d = get_db()

    email = os.environ.get("ADMIN_EMAIL", "admin@promptverse.com").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "Admin@123")

    existing = d.admins.find_one({"email": email})
    if existing:
        return

    d.admins.insert_one({
        "name": "PromptVerse Admin",
        "email": email,
        "password_hash": generate_password_hash(password),
        "is_active": True,
        "created_at": now_iso(),
        "updated_at": now_iso()
    })

    print(f"Default admin created: {email}")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if admin_doc():
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        admin = get_db().admins.find_one({"email": email})

        if (
            admin
            and admin.get("is_active", True)
            and admin.get("password_hash")
            and check_password_hash(admin["password_hash"], password)
        ):
            session.clear()
            session["admin_id"] = str(admin["_id"])

            nxt = session.pop("next_after_admin_login", None)
            return redirect(nxt or url_for("admin_dashboard"))

        flash("Invalid admin email/password or disabled account.", "error")

    return render_template("admin/login.html")


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    """
    Main admin dashboard.

    IMPORTANT:
    Templates can safely use:
        url_for("admin_dashboard")
    """
    d = get_db()
    admin = admin_doc()

    recent_prompts = list(
        d.prompts.find({}).sort("created_at", DESCENDING).limit(10)
    )

    for prompt in recent_prompts:
        prompt["author_name"] = get_prompt_author_name(prompt)
        prompt.setdefault("featured_order", 0)
        prompt.setdefault("trending_order", 0)
        prompt.setdefault("manual_featured", False)
        prompt.setdefault("manual_trending", False)

    recent_users = list(
        d.users.find({}).sort("created_at", DESCENDING).limit(10)
    )

    recent_logs = list(
        d.admin_logs.find({}).sort("created_at", DESCENDING).limit(10)
    )

    stats = {
        "users": d.users.count_documents({}),
        "prompts": d.prompts.count_documents({}),
        "likes": d.likes.count_documents({}),
        "saves": d.saves.count_documents({}),
        "copies": d.copy_events.count_documents({}),
        "views": d.views.count_documents({})
    }

    return render_template(
        "admin/dashboard.html",
        admin=admin,
        stats=stats,
        recent_prompts=recent_prompts,
        users=recent_users,
        logs=recent_logs
    )


def get_prompt_author_name(prompt):
    """Return a safe author name for both ObjectId and string author IDs."""
    author_id = prompt.get("author_id")

    if not author_id:
        if prompt.get("created_by_admin"):
            return "Admin"
        return "User"

    try:
        oid = ObjectId(author_id) if isinstance(author_id, str) else author_id
        author = get_db().users.find_one({"_id": oid})

        if author:
            return (
                author.get("name")
                or author.get("email")
                or "User"
            )
    except Exception:
        pass

    return "User"


def admin_log(action, details=""):
    """Write an admin activity record without breaking the current request."""
    try:
        get_db().admin_logs.insert_one({
            "admin_id": session.get("admin_id"),
            "action": action,
            "details": details,
            "created_at": now_iso()
        })
    except Exception:
        pass


# ============================================================
# ADMIN PROMPTS
# ============================================================

@app.route("/admin/prompts")
@admin_required
def admin_prompts():
    """
    Admin prompt management page.

    This fixes:
        BuildError: Could not build url for endpoint 'admin_prompts'
    """
    d = get_db()

    prompts = list(
        d.prompts.find({}).sort("created_at", DESCENDING)
    )

    for prompt in prompts:
        prompt["author_name"] = get_prompt_author_name(prompt)

        # Backward-compatible defaults for prompts created before
        # admin featured/trending controls were added.
        prompt.setdefault("featured_order", 0)
        prompt.setdefault("trending_order", 0)
        prompt.setdefault("manual_featured", False)
        prompt.setdefault("manual_trending", False)

    return render_template(
        "admin/prompts.html",
        prompts=prompts
    )


@app.route("/admin/add-prompt", methods=["GET", "POST"])
@admin_required
def admin_add_prompt():
    """Create/publish a prompt directly from the admin panel."""

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        prompt_text = request.form.get("prompt", "").strip()
        model = request.form.get("model", MODELS[0]).strip()
        prompt_type = request.form.get("prompt_type", "image").strip()
        category = request.form.get("category", CATEGORIES[0]).strip()
        use_case = request.form.get("use_case", USE_CASES[0]).strip()
        style = request.form.get("style", STYLES[0]).strip()
        subject = request.form.get("subject", SUBJECTS[0]).strip()
        tags = parse_tags(request.form.get("tags", ""))
        image = request.form.get("image", "").strip()

        if not title:
            flash("Prompt title is required.", "error")
            return redirect(url_for("admin_add_prompt"))

        if not prompt_text:
            flash("Prompt text is required.", "error")
            return redirect(url_for("admin_add_prompt"))

        if model not in MODELS:
            model = MODELS[0]

        if prompt_type not in PROMPT_TYPES:
            prompt_type = "image"

        if category not in CATEGORIES:
            category = CATEGORIES[0]

        if use_case not in USE_CASES:
            use_case = USE_CASES[0]

        if style not in STYLES:
            style = STYLES[0]

        if subject not in SUBJECTS:
            subject = SUBJECTS[0]

        upload = request.files.get("image_file")

        if upload and upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1].lower()

            if ext not in ALLOWED_IMAGES:
                flash("Unsupported image format.", "error")
                return redirect(url_for("admin_add_prompt"))

            filename = secure_filename(
                datetime.now().strftime("%Y%m%d%H%M%S%f")
                + "_"
                + upload.filename
            )

            upload.save(os.path.join(UPLOAD_DIR, filename))

            image = url_for(
                "static",
                filename="uploads/" + filename
            )

        # Image URL is required because the current prompt cards/detail
        # pages use the image field.
        if not image:
            flash(
                "Please add an image URL or upload an image.",
                "error"
            )
            return redirect(url_for("admin_add_prompt"))

        d = get_db()

        duplicate = d.prompts.find_one({
            "prompt": {
                "$regex": "^" + re.escape(prompt_text) + "$",
                "$options": "i"
            }
        })

        if duplicate:
            flash("This prompt already exists.", "error")
            return redirect(url_for("admin_add_prompt"))

        created = now_iso()

        d.prompts.insert_one({
            "title": title,
            "description": description,
            "prompt": prompt_text,
            "image": image,
            "model": model,
            "category": category,
            "prompt_type": prompt_type,
            "use_case": use_case,
            "style": style,
            "subject": subject,
            "tags": tags,

            # Admin-created prompt is not owned by a normal user.
            "author_id": None,
            "created_by_admin": session.get("admin_id"),

            "views": 0,
            "likes": 0,
            "saves": 0,
            "copies": 0,

            # Admin content-management controls
            "featured_order": 0,
            "trending_order": 0,
            "manual_featured": False,
            "manual_trending": False,

            "created_at": created,
            "updated_at": created
        })

        admin_log(
            "Prompt created",
            f"Created prompt: {title}"
        )

        flash("Prompt published successfully!", "success")
        return redirect(url_for("admin_prompts"))

    return render_template(
        "admin/add_prompt.html",
        **prompt_form_context()
    )


# ============================================================
# ADMIN EDIT PROMPT
# ============================================================

@app.route("/admin/prompt/<pid>/edit", methods=["GET", "POST"])
@app.route("/admin/prompts/<pid>/edit", methods=["GET", "POST"])
@admin_required
def admin_edit_prompt(pid):
    prompt = prompt_by_id(pid)

    if not prompt:
        flash("Prompt not found.", "error")
        return redirect(url_for("admin_prompts"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        prompt_text = request.form.get("prompt", "").strip()

        model = request.form.get("model", MODELS[0]).strip()
        prompt_type = request.form.get("prompt_type", "image").strip()
        category = request.form.get("category", CATEGORIES[0]).strip()
        use_case = request.form.get("use_case", USE_CASES[0]).strip()
        style = request.form.get("style", STYLES[0]).strip()
        subject = request.form.get("subject", SUBJECTS[0]).strip()
        tags = parse_tags(request.form.get("tags", ""))
        image = request.form.get("image", "").strip() or prompt.get("image", "")

        if not title or not prompt_text:
            flash("Title and prompt text are required.", "error")
            return redirect(url_for("admin_edit_prompt", pid=pid))

        if model not in MODELS:
            model = MODELS[0]

        if prompt_type not in PROMPT_TYPES:
            prompt_type = "image"

        if category not in CATEGORIES:
            category = CATEGORIES[0]

        if use_case not in USE_CASES:
            use_case = USE_CASES[0]

        if style not in STYLES:
            style = STYLES[0]

        if subject not in SUBJECTS:
            subject = SUBJECTS[0]

        upload = request.files.get("image_file")

        if upload and upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1].lower()

            if ext not in ALLOWED_IMAGES:
                flash("Unsupported image format.", "error")
                return redirect(url_for("admin_edit_prompt", pid=pid))

            filename = secure_filename(
                datetime.now().strftime("%Y%m%d%H%M%S%f")
                + "_"
                + upload.filename
            )

            upload.save(os.path.join(UPLOAD_DIR, filename))

            image = url_for(
                "static",
                filename="uploads/" + filename
            )

        d = get_db()

        duplicate = d.prompts.find_one({
            "_id": {"$ne": prompt["_id"]},
            "prompt": {
                "$regex": "^" + re.escape(prompt_text) + "$",
                "$options": "i"
            }
        })

        if duplicate:
            flash("Another prompt with the same text already exists.", "error")
            return redirect(url_for("admin_edit_prompt", pid=pid))

        d.prompts.update_one(
            {"_id": prompt["_id"]},
            {
                "$set": {
                    "title": title,
                    "description": description,
                    "prompt": prompt_text,
                    "image": image,
                    "model": model,
                    "prompt_type": prompt_type,
                    "category": category,
                    "use_case": use_case,
                    "style": style,
                    "subject": subject,
                    "tags": tags,
                    "updated_at": now_iso()
                }
            }
        )

        admin_log(
            "Prompt updated",
            f"Updated prompt: {title}"
        )

        flash("Prompt updated successfully.", "success")
        return redirect(url_for("admin_prompts"))

    return render_template(
        "admin/add_prompt.html",
        prompt=prompt,
        edit_mode=True,
        **prompt_form_context()
    )


# ============================================================
# ADMIN DELETE PROMPT
# ============================================================

@app.route("/admin/prompts/<pid>/delete", methods=["POST", "GET"])
@app.route("/admin/prompt/<pid>/delete", methods=["POST", "GET"])
@admin_required
def admin_delete_prompt(pid):
    prompt = prompt_by_id(pid)

    if not prompt:
        flash("Prompt not found.", "error")
        return redirect(url_for("admin_prompts"))

    d = get_db()
    oid = prompt["_id"]

    d.prompts.delete_one({"_id": oid})
    d.likes.delete_many({"prompt_id": oid})
    d.saves.delete_many({"prompt_id": oid})
    d.views.delete_many({"prompt_id": oid})
    d.copy_events.delete_many({"prompt_id": oid})

    admin_log(
        "Prompt deleted",
        f"Deleted prompt: {prompt.get('title', 'Untitled')}"
    )

    flash("Prompt deleted successfully.", "success")
    return redirect(url_for("admin_prompts"))


# ============================================================
# ADMIN PROMPT ORDER / FEATURED / TRENDING CONTROLS
# ============================================================

@app.post("/admin/prompt/<pid>/reorder")
@admin_required
def reorder_prompt(pid):
    """Set featured_order or trending_order for an individual prompt."""
    prompt = prompt_by_id(pid)

    if not prompt:
        flash("Prompt not found.", "error")
        return redirect(url_for("admin_prompts"))

    field = request.form.get("field", "").strip()
    value_raw = request.form.get("value", "").strip()

    allowed_fields = {"featured_order", "trending_order"}

    if field not in allowed_fields:
        flash("Invalid order field.", "error")
        return redirect(url_for("admin_prompts"))

    try:
        value = int(value_raw) if value_raw else 0
    except ValueError:
        flash("Order must be a number.", "error")
        return redirect(url_for("admin_prompts"))

    value = max(0, value)

    get_db().prompts.update_one(
        {"_id": prompt["_id"]},
        {
            "$set": {
                field: value,
                "updated_at": now_iso()
            }
        }
    )

    admin_log(
        "Prompt order updated",
        f"{prompt.get('title', 'Untitled')}: {field} = {value}"
    )

    flash("Prompt order updated successfully.", "success")
    return redirect(url_for("admin_prompts"))


@app.post("/admin/prompt/<pid>/featured")
@admin_required
def toggle_featured(pid):
    """Toggle manual featured status."""
    prompt = prompt_by_id(pid)

    if not prompt:
        flash("Prompt not found.", "error")
        return redirect(url_for("admin_prompts"))

    new_value = not bool(prompt.get("manual_featured", False))

    get_db().prompts.update_one(
        {"_id": prompt["_id"]},
        {
            "$set": {
                "manual_featured": new_value,
                "updated_at": now_iso()
            }
        }
    )

    admin_log(
        "Featured status changed",
        f"{prompt.get('title', 'Untitled')} -> "
        f"{'Featured' if new_value else 'Not Featured'}"
    )

    flash(
        "Prompt featured." if new_value else "Prompt removed from featured.",
        "success"
    )

    return redirect(url_for("admin_prompts"))


@app.post("/admin/prompt/<pid>/trending")
@admin_required
def toggle_trending(pid):
    """Toggle manual trending status."""
    prompt = prompt_by_id(pid)

    if not prompt:
        flash("Prompt not found.", "error")
        return redirect(url_for("admin_prompts"))

    new_value = not bool(prompt.get("manual_trending", False))

    get_db().prompts.update_one(
        {"_id": prompt["_id"]},
        {
            "$set": {
                "manual_trending": new_value,
                "updated_at": now_iso()
            }
        }
    )

    admin_log(
        "Trending status changed",
        f"{prompt.get('title', 'Untitled')} -> "
        f"{'Trending' if new_value else 'Not Trending'}"
    )

    flash(
        "Prompt marked as trending." if new_value
        else "Prompt removed from trending.",
        "success"
    )

    return redirect(url_for("admin_prompts"))


# ============================================================
# ADMIN CATEGORIES
# ============================================================

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    d = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        emoji = request.form.get("emoji", "✦").strip() or "✦"

        if not name:
            flash("Category name is required.", "error")
            return redirect(url_for("admin_categories"))

        existing = d.categories.find_one({
            "name": {"$regex": "^" + re.escape(name) + "$", "$options": "i"}
        })

        if existing:
            flash("Category already exists.", "error")
            return redirect(url_for("admin_categories"))

        d.categories.insert_one({
            "name": name,
            "emoji": emoji,
            "created_at": now_iso()
        })

        admin_log(
            "Category created",
            f"Created category: {name}"
        )

        flash("Category added successfully.", "success")
        return redirect(url_for("admin_categories"))

    categories = list(
        d.categories.find({}).sort("name", ASCENDING)
    )

    return render_template(
        "admin/categories.html",
        categories=categories
    )


@app.route("/admin/categories/<cid>/delete", methods=["POST", "GET"])
@admin_required
def admin_delete_category(cid):
    d = get_db()

    try:
        oid = ObjectId(cid)
    except Exception:
        flash("Invalid category.", "error")
        return redirect(url_for("admin_categories"))

    category = d.categories.find_one({"_id": oid})

    if not category:
        flash("Category not found.", "error")
        return redirect(url_for("admin_categories"))

    name = category.get("name", "")

    d.categories.delete_one({"_id": oid})

    admin_log(
        "Category deleted",
        f"Deleted category: {name}"
    )

    flash("Category deleted successfully.", "success")
    return redirect(url_for("admin_categories"))


# ============================================================
# ADMIN USERS
# ============================================================

@app.route("/admin/users")
@admin_required
def admin_users():
    users = list(
        get_db().users.find({}).sort("created_at", DESCENDING)
    )

    return render_template(
        "admin/users.html",
        users=users
    )


@app.route("/admin/users/<uid>/toggle", methods=["POST", "GET"])
@admin_required
def admin_toggle_user(uid):
    d = get_db()

    try:
        oid = ObjectId(uid)
    except Exception:
        flash("Invalid user.", "error")
        return redirect(url_for("admin_users"))

    user = d.users.find_one({"_id": oid})

    if not user:
        flash("User not found.", "error")
        return redirect(url_for("admin_users"))

    new_status = not user.get("is_active", True)

    d.users.update_one(
        {"_id": oid},
        {
            "$set": {
                "is_active": new_status,
                "updated_at": now_iso()
            }
        }
    )

    admin_log(
        "User status changed",
        f"{user.get('email', 'Unknown')} -> "
        f"{'Active' if new_status else 'Disabled'}"
    )

    flash(
        f"User {'enabled' if new_status else 'disabled'} successfully.",
        "success"
    )

    return redirect(url_for("admin_users"))


# ============================================================
# ADMIN ACTIVITY
# ============================================================

@app.route("/admin/activity")
@admin_required
def admin_activity():
    logs = list(
        get_db().admin_logs.find({})
        .sort("created_at", DESCENDING)
        .limit(200)
    )

    return render_template(
        "admin/activity.html",
        logs=logs
    )


# ============================================================
# ADMIN ANALYTICS
# ============================================================

@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    d = get_db()

    stats = {
        "users": d.users.count_documents({}),
        "prompts": d.prompts.count_documents({}),
        "likes": d.likes.count_documents({}),
        "saves": d.saves.count_documents({}),
        "copies": d.copy_events.count_documents({}),
        "views": d.views.count_documents({})
    }

    prompt_types = []
    for ptype in PROMPT_TYPES:
        prompt_types.append({
            "name": ptype,
            "count": d.prompts.count_documents({"prompt_type": ptype})
        })

    models = []
    for model in MODELS:
        models.append({
            "name": model,
            "count": d.prompts.count_documents({"model": model})
        })

    categories = []
    for category in CATEGORIES:
        categories.append({
            "name": category,
            "count": d.prompts.count_documents({"category": category})
        })

    return render_template(
        "admin/analytics.html",
        stats=stats,
        prompt_types=prompt_types,
        models=models,
        categories=categories
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():

    # Clear admin session
    session.pop("admin_id", None)
    session.pop("next_after_admin_login", None)

    # Success message
    flash("Admin logged out successfully.", "success")

    # Redirect to admin login page
    return redirect(url_for("admin_login"))

# Make admin information available to every admin template.
@app.context_processor
def inject_admin_globals():
    return {
        "current_admin": admin_doc()
    }


# ============================================================
# PUBLIC PAGES
# ============================================================

@app.route("/")
def index():
    return render_template("index.html", models=MODELS)


@app.route("/explore")
def explore():
    return render_template("index.html", models=MODELS, explore_mode=True)


@app.route("/prompts")
def prompts():
    return render_template("prompts.html", models=MODELS)


@app.route("/prompt/<pid>")
def prompt_detail(pid):
    p = prompt_by_id(pid)
    if not p:
        return "Prompt not found", 404

    d = get_db()
    oid = p["_id"]

    d.prompts.update_one({"_id": oid}, {"$inc": {"views": 1}})
    d.views.insert_one({
        "user_id": session.get("user_id"),
        "prompt_id": oid,
        "created_at": now_iso()
    })

    p = d.prompts.find_one({"_id": oid})

    related = list(
        d.prompts.find({
            "_id": {"$ne": oid},
            "$or": [
                {"category": p.get("category")},
                {"model": p.get("model")},
                {"style": p.get("style")}
            ]
        })
        .sort("created_at", DESCENDING)
        .limit(4)
    )

    return render_template(
        "prompt.html",
        prompt=p,
        related=related
    )


@app.route("/library")
@user_required
def library():
    d = get_db()
    uid = ObjectId(session["user_id"])

    saved_ids = [
        x["prompt_id"]
        for x in d.saves.find({"user_id": uid}).sort("created_at", DESCENDING)
    ]

    liked_ids = [
        x["prompt_id"]
        for x in d.likes.find({"user_id": uid}).sort("created_at", DESCENDING)
    ]

    recent_ids = []
    for x in d.views.find({"user_id": uid}).sort("created_at", DESCENDING).limit(100):
        if x["prompt_id"] not in recent_ids:
            recent_ids.append(x["prompt_id"])

    def fetch(ids):
        if not ids:
            return []
        return list(d.prompts.find({"_id": {"$in": ids}}))

    saved = fetch(saved_ids)
    liked = fetch(liked_ids)
    recent = fetch(recent_ids)

    positions = {str(x): i for i, x in enumerate(saved_ids)}
    saved.sort(key=lambda x: positions.get(str(x["_id"]), 999999))

    positions = {str(x): i for i, x in enumerate(liked_ids)}
    liked.sort(key=lambda x: positions.get(str(x["_id"]), 999999))

    positions = {str(x): i for i, x in enumerate(recent_ids)}
    recent.sort(key=lambda x: positions.get(str(x["_id"]), 999999))

    return render_template(
        "library.html",
        saved=saved,
        liked=liked,
        recent=recent
    )


# ============================================================
# AUTH
# ============================================================

@app.route("/user/signup", methods=["GET", "POST"])
def user_signup():
    """Registration step 1: email -> send OTP."""
    if user_doc():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Enter a valid email address.", "error")
            return render_template("signup.html")

        d = get_db()

        if d.users.find_one({"email": email}):
            flash("That email is already registered. Please log in.", "error")
            return render_template("signup.html", existing_email=True)

        if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
            flash("Email service is not configured. Add MAIL_USERNAME and MAIL_PASSWORD to .env.", "error")
            return render_template("signup.html")

        recent = d.email_otps.find_one({"email": email}, sort=[("created_at", DESCENDING)])
        if recent:
            try:
                elapsed = (utcnow() - datetime.fromisoformat(recent["created_at"])).total_seconds()
                if elapsed < 60:
                    flash(f"Please wait {max(1, 60 - int(elapsed))} seconds before requesting another OTP.", "error")
                    return render_template("signup.html")
            except Exception:
                pass

        otp = f"{secrets.randbelow(900000) + 100000:06d}"
        otp_doc = {
            "email": email,
            "otp_hash": generate_password_hash(otp),
            "created_at": now_iso(),
            "expires_at": (utcnow() + timedelta(minutes=5)).isoformat(),
            "attempts": 0,
            "used": False
        }

        d.email_otps.update_many(
            {"email": email, "used": False},
            {"$set": {"used": True, "invalidated_at": now_iso()}}
        )

        result = None
        try:
            result = d.email_otps.insert_one(otp_doc)

            msg = Message(
                subject="Your PromptVerse verification code",
                recipients=[email]
            )
            msg.html = f"""
            <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:30px;background:#f8fafc;color:#111827;">
                <div style="background:#111827;color:#fff;padding:25px;border-radius:16px;text-align:center;">
                    <h1 style="margin:0;">PromptVerse</h1>
                    <p>Email Verification</p>
                </div>
                <div style="background:#fff;margin-top:18px;padding:30px;border-radius:16px;text-align:center;border:1px solid #e5e7eb;">
                    <h2>Your verification code</h2>
                    <div style="font-size:34px;font-weight:800;letter-spacing:8px;padding:15px 10px;">{otp}</div>
                    <p>This OTP is valid for <strong>5 minutes</strong>.</p>
                    <p style="color:#6b7280;font-size:13px;">If you did not request this code, ignore this email.</p>
                </div>
            </div>
            """
            mail.send(msg)

            session["signup_email"] = email
            return redirect(url_for("signup_otp"))

        except Exception as exc:
            if result:
                d.email_otps.delete_one({"_id": result.inserted_id})
            print(f"SIGNUP OTP EMAIL ERROR: {exc}")
            flash("Could not send OTP. Check your Gmail SMTP/App Password settings.", "error")

    return render_template("signup.html")


@app.route("/signup/otp", methods=["GET", "POST"])
def signup_otp():
    """Registration step 2: verify OTP, then show password page."""
    email = session.get("signup_email")
    if not email:
        return redirect(url_for("user_signup"))

    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        d = get_db()

        if not re.fullmatch(r"\d{6}", otp):
            flash("Enter the 6-digit OTP.", "error")
            return render_template("signup_otp.html", email=email)

        otp_doc = d.email_otps.find_one(
            {"email": email, "used": False},
            sort=[("created_at", DESCENDING)]
        )

        if not otp_doc:
            flash("OTP not found. Please request a new OTP.", "error")
            return redirect(url_for("user_signup"))

        try:
            expires_at = datetime.fromisoformat(otp_doc["expires_at"])
        except Exception:
            expires_at = utcnow() - timedelta(seconds=1)

        if expires_at < utcnow():
            flash("OTP expired. Please request a new OTP.", "error")
            return redirect(url_for("user_signup"))

        if otp_doc.get("attempts", 0) >= 5:
            flash("Too many incorrect attempts. Please request a new OTP.", "error")
            return redirect(url_for("user_signup"))

        if not check_password_hash(otp_doc["otp_hash"], otp):
            d.email_otps.update_one(
                {"_id": otp_doc["_id"]},
                {"$inc": {"attempts": 1}}
            )
            flash("Incorrect OTP. Please try again.", "error")
            return render_template("signup_otp.html", email=email)

        # Do NOT create user yet. Move to password step.
        d.email_otps.update_one(
            {"_id": otp_doc["_id"]},
            {"$set": {"verified": True, "verified_at": now_iso()}}
        )
        session["signup_verified_email"] = email
        return redirect(url_for("signup_password"))

    return render_template("signup_otp.html", email=email)


@app.route("/signup/password", methods=["GET", "POST"])
def signup_password():
    """Registration step 3: choose password and create account."""
    email = session.get("signup_verified_email")
    if not email:
        return redirect(url_for("user_signup"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("signup_password.html", email=email)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("signup_password.html", email=email)

        d = get_db()

        if d.users.find_one({"email": email}):
            session.pop("signup_email", None)
            session.pop("signup_verified_email", None)
            flash("That email is already registered. Please log in.", "error")
            return redirect(url_for("user_login"))

        verified_otp = d.email_otps.find_one(
            {"email": email, "verified": True, "used": False},
            sort=[("created_at", DESCENDING)]
        )

        if not verified_otp:
            flash("Please verify your email with OTP first.", "error")
            return redirect(url_for("user_signup"))

        now = now_iso()
        display_name = email.split("@")[0].replace(".", " ").replace("_", " ").title()

        try:
            result = d.users.insert_one({
                "name": display_name or "PromptVerse User",
                "email": email,
                "password_hash": generate_password_hash(password),
                "is_active": True,
                "verified": True,
                "created_at": now,
                "updated_at": now
            })

            d.email_otps.update_one(
                {"_id": verified_otp["_id"]},
                {"$set": {"used": True, "account_created_at": now}}
            )

            u = d.users.find_one({"_id": result.inserted_id})
            session.clear()
            session["user_id"] = str(u["_id"])

            return redirect(url_for("index"))

        except DuplicateKeyError:
            flash("That email is already registered. Please log in.", "error")
            return redirect(url_for("user_login"))

    return render_template("signup_password.html", email=email)


@app.route("/user/login", methods=["GET", "POST"])
def user_login():
    if user_doc():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Please enter your email and password.", "error")
            return render_template("login.html")

        u = get_db().users.find_one({"email": email})

        if not u:
            flash("No account found with this email. Please sign up.", "error")
            return render_template("login.html")

        if not u.get("is_active", True):
            flash("Your account has been disabled. Please contact support.", "error")
            return render_template("login.html")

        if not u.get("password_hash") or not check_password_hash(u["password_hash"], password):
            flash("Incorrect email or password. Please try again.", "error")
            return render_template("login.html")

        session.clear()
        session["user_id"] = str(u["_id"])

        nxt = session.pop("next_after_login", None)
        return redirect(nxt or url_for("index"))

    return render_template("login.html")


@app.route("/user/logout")
def user_logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            flash("Enter a valid email address.", "error")
            return render_template("forgot.html")

        d = get_db()
        u = d.users.find_one({"email": email})

        # Always show the same success message to avoid email enumeration.
        if u and app.config["MAIL_USERNAME"] and app.config["MAIL_PASSWORD"]:
            token = secrets.token_urlsafe(32)

            d.password_resets.update_many(
                {"user_id": u["_id"], "used": False},
                {"$set": {"used": True, "invalidated_at": now_iso()}}
            )

            d.password_resets.insert_one({
                "user_id": u["_id"],
                "token": token,
                "created_at": now_iso(),
                "expires_at": (utcnow() + timedelta(minutes=30)).isoformat(),
                "used": False
            })

            reset_url = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            try:
                msg = Message(
                    subject="Reset your PromptVerse password",
                    recipients=[email]
                )
                msg.html = f"""
                <div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;padding:30px;background:#f8fafc;color:#111827;">
                    <div style="background:#111827;color:#fff;padding:25px;border-radius:16px;text-align:center;">
                        <h1 style="margin:0;">PromptVerse</h1>
                        <p>Password Reset</p>
                    </div>
                    <div style="background:#fff;margin-top:18px;padding:30px;border-radius:16px;border:1px solid #e5e7eb;">
                        <h2>Reset your password</h2>
                        <p>Click the button below to create a new password.</p>
                        <p style="text-align:center;margin:28px 0;">
                            <a href="{reset_url}" style="display:inline-block;background:#111827;color:#fff;text-decoration:none;padding:13px 24px;border-radius:10px;font-weight:700;">Reset Password</a>
                        </p>
                        <p style="color:#6b7280;font-size:13px;">This link expires in 30 minutes.</p>
                        <p style="color:#6b7280;font-size:12px;word-break:break-all;">If the button does not work: {reset_url}</p>
                    </div>
                </div>
                """
                mail.send(msg)
            except Exception as exc:
                print(f"PASSWORD RESET EMAIL ERROR: {exc}")

        elif u and (not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]):
            print("PASSWORD RESET EMAIL SKIPPED: MAIL_USERNAME or MAIL_PASSWORD is missing.")

        flash("If an account exists for that email, a password reset link has been sent.", "success")
        return redirect(url_for("forgot_password"))

    return render_template("forgot.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    d = get_db()
    r = d.password_resets.find_one({"token": token, "used": False})

    if not r:
        return render_template("reset.html", invalid=True), 400

    try:
        expires_at = datetime.fromisoformat(r["expires_at"])
    except Exception:
        expires_at = utcnow() - timedelta(seconds=1)

    if expires_at < utcnow():
        return render_template("reset.html", invalid=True), 400

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("reset.html", token=token)

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("reset.html", token=token)

        d.users.update_one(
            {"_id": r["user_id"]},
            {
                "$set": {
                    "password_hash": generate_password_hash(password),
                    "updated_at": now_iso()
                }
            }
        )

        d.password_resets.update_one(
            {"_id": r["_id"]},
            {"$set": {"used": True, "used_at": now_iso()}}
        )

        flash("Password changed successfully. Please log in.", "success")
        return redirect(url_for("user_login"))

    return render_template("reset.html", token=token)


# Backward-compatible user URLs.
@app.route("/signup")
def signup():
    return redirect(url_for("user_signup"))


@app.route("/login")
def login():
    return redirect(url_for("user_login"))


@app.route("/logout")
def logout():
    return redirect(url_for("user_logout"))


# ============================================================
# USER DASHBOARD
# ============================================================

@app.route("/user/dashboard")
@user_required
def user_dashboard():
    d = get_db()
    uid = ObjectId(session["user_id"])

    recent_prompts = list(
        d.prompts.find({"author_id": uid})
        .sort("created_at", DESCENDING)
        .limit(6)
    )

    all_prompts = list(d.prompts.find({"author_id": uid}))

    stats = {
        "my_prompts": len(all_prompts),
        "views": sum(p.get("views", 0) for p in all_prompts),
        "likes": d.likes.count_documents({"user_id": uid}),
        "saves": d.saves.count_documents({"user_id": uid}),
        "copies": sum(p.get("copies", 0) for p in all_prompts),
    }

    return render_template(
        "user/dashboard.html",
        recent_prompts=recent_prompts,
        stats=stats
    )


@app.route("/user/profile")
@user_required
def user_profile():
    return render_template("user/profile.html")


@app.route("/user/profile/edit", methods=["GET", "POST"])
@user_required
def user_edit_profile():
    d = get_db()
    uid = ObjectId(session["user_id"])

    if request.method == "POST":
        name = request.form.get("name", "").strip()

        if not name:
            flash("Name cannot be empty.", "error")
            return redirect(url_for("user_edit_profile"))

        d.users.update_one(
            {"_id": uid},
            {"$set": {"name": name, "updated_at": now_iso()}}
        )

        flash("Profile updated successfully.", "success")
        return redirect(url_for("user_profile"))

    return render_template("user/edit_profile.html")


@app.route("/user/settings")
@user_required
def user_settings():
    return render_template("user/settings.html")


# ============================================================
# USER CREATE PROMPT
# ============================================================

@app.route("/user/add-prompt", methods=["GET", "POST"])
@user_required
def user_add_prompt():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        prompt_text = request.form.get("prompt", "").strip()
        model = request.form.get("model", MODELS[0]).strip()
        prompt_type = request.form.get("prompt_type", "image").strip()
        category = request.form.get("category", CATEGORIES[0]).strip()
        use_case = request.form.get("use_case", USE_CASES[0]).strip()
        style = request.form.get("style", STYLES[0]).strip()
        subject = request.form.get("subject", SUBJECTS[0]).strip()
        tags = parse_tags(request.form.get("tags", ""))
        image = request.form.get("image", "").strip()

        if not title:
            flash("Prompt title is required.", "error")
            return redirect(url_for("user_add_prompt"))

        if not prompt_text:
            flash("Prompt text is required.", "error")
            return redirect(url_for("user_add_prompt"))

        if model not in MODELS:
            model = MODELS[0]

        if prompt_type not in PROMPT_TYPES:
            prompt_type = "image"

        if category not in CATEGORIES:
            category = CATEGORIES[0]

        if use_case not in USE_CASES:
            use_case = USE_CASES[0]

        if style not in STYLES:
            style = STYLES[0]

        if subject not in SUBJECTS:
            subject = SUBJECTS[0]

        upload = request.files.get("image_file")

        if upload and upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1].lower()

            if ext not in ALLOWED_IMAGES:
                flash("Unsupported image format.", "error")
                return redirect(url_for("user_add_prompt"))

            filename = secure_filename(
                datetime.now().strftime("%Y%m%d%H%M%S%f")
                + "_"
                + upload.filename
            )

            upload.save(os.path.join(UPLOAD_DIR, filename))
            image = url_for(
                "static",
                filename="uploads/" + filename
            )

        if not image:
            flash("Please add an image URL or upload an image.", "error")
            return redirect(url_for("user_add_prompt"))

        d = get_db()

        duplicate = d.prompts.find_one({
            "prompt": {
                "$regex": "^" + re.escape(prompt_text) + "$",
                "$options": "i"
            }
        })

        if duplicate:
            flash("This prompt already exists.", "error")
            return redirect(url_for("user_add_prompt"))

        created = now_iso()

        d.prompts.insert_one({
            "title": title,
            "description": description,
            "prompt": prompt_text,
            "image": image,
            "model": model,
            "category": category,
            "prompt_type": prompt_type,
            "use_case": use_case,
            "style": style,
            "subject": subject,
            "tags": tags,
            "author_id": session["user_id"],
            "views": 0,
            "likes": 0,
            "saves": 0,
            "copies": 0,
            "created_at": created,
            "updated_at": created
        })

        flash("Prompt published successfully!", "success")
        return redirect(url_for("user_my_prompts"))

    return render_template(
        "user/add_prompt.html",
        **prompt_form_context()
    )


# ============================================================
# USER MY PROMPTS
# ============================================================

@app.route("/user/my-prompts")
@user_required
def user_my_prompts():
    d = get_db()
    prompts = list(
        d.prompts.find({"author_id": session["user_id"]})
        .sort("created_at", DESCENDING)
    )

    return render_template(
        "user/my_prompts.html",
        prompts=prompts
    )


@app.route("/user/prompt/<pid>/edit", methods=["GET", "POST"])
@user_required
def user_edit_prompt(pid):
    prompt = prompt_by_id(pid)

    if not prompt or prompt.get("author_id") != session["user_id"]:
        return "Prompt not found", 404

    d = get_db()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        prompt_text = request.form.get("prompt", "").strip()
        model = request.form.get("model", MODELS[0]).strip()
        prompt_type = request.form.get("prompt_type", "image").strip()
        use_case = request.form.get("use_case", USE_CASES[0]).strip()
        style = request.form.get("style", STYLES[0]).strip()
        subject = request.form.get("subject", SUBJECTS[0]).strip()
        category = request.form.get("category", CATEGORIES[0]).strip()
        tags = parse_tags(request.form.get("tags", ""))

        if not title or not prompt_text:
            flash("Title and prompt are required.", "error")
            return redirect(url_for("user_edit_prompt", pid=pid))

        image = request.form.get("image", "").strip() or prompt.get("image", "")

        upload = request.files.get("image_file")
        if upload and upload.filename:
            ext = upload.filename.rsplit(".", 1)[-1].lower()

            if ext not in ALLOWED_IMAGES:
                flash("Unsupported image format.", "error")
                return redirect(url_for("user_edit_prompt", pid=pid))

            filename = secure_filename(
                datetime.now().strftime("%Y%m%d%H%M%S%f")
                + "_"
                + upload.filename
            )
            upload.save(os.path.join(UPLOAD_DIR, filename))
            image = url_for("static", filename="uploads/" + filename)

        d.prompts.update_one(
            {
                "_id": prompt["_id"],
                "author_id": session["user_id"]
            },
            {
                "$set": {
                    "title": title,
                    "description": description,
                    "prompt": prompt_text,
                    "image": image,
                    "model": model if model in MODELS else MODELS[0],
                    "prompt_type": prompt_type if prompt_type in PROMPT_TYPES else "image",
                    "category": category if category in CATEGORIES else CATEGORIES[0],
                    "use_case": use_case if use_case in USE_CASES else USE_CASES[0],
                    "style": style if style in STYLES else STYLES[0],
                    "subject": subject if subject in SUBJECTS else SUBJECTS[0],
                    "tags": tags,
                    "updated_at": now_iso()
                }
            }
        )

        flash("Prompt updated successfully.", "success")
        return redirect(url_for("user_my_prompts"))

    return render_template(
        "user/edit_prompt.html",
        prompt=prompt,
        **prompt_form_context()
    )


@app.post("/user/prompt/<pid>/delete")
@user_required
def user_delete_prompt(pid):
    prompt = prompt_by_id(pid)

    if not prompt or prompt.get("author_id") != session["user_id"]:
        return "Prompt not found", 404

    d = get_db()
    oid = prompt["_id"]

    d.prompts.delete_one({
        "_id": oid,
        "author_id": session["user_id"]
    })

    d.likes.delete_many({"prompt_id": oid})
    d.saves.delete_many({"prompt_id": oid})
    d.views.delete_many({"prompt_id": oid})
    d.copy_events.delete_many({"prompt_id": oid})

    flash("Prompt deleted successfully.", "success")
    return redirect(url_for("user_my_prompts"))


# ============================================================
# USER SAVED / LIKED
# ============================================================

@app.route("/user/saved-prompts")
@user_required
def user_saved_prompts():
    d = get_db()
    uid = ObjectId(session["user_id"])

    ids = [
        x["prompt_id"]
        for x in d.saves.find({"user_id": uid}).sort(
            "created_at", DESCENDING
        )
    ]

    prompts = list(
        d.prompts.find({"_id": {"$in": ids}})
    )

    order = {str(x): i for i, x in enumerate(ids)}
    prompts.sort(key=lambda x: order.get(str(x["_id"]), 999999))

    return render_template(
        "user/saved_prompts.html",
        prompts=prompts
    )


@app.route("/user/liked-prompts")
@user_required
def user_liked_prompts():
    d = get_db()
    uid = ObjectId(session["user_id"])

    ids = [
        x["prompt_id"]
        for x in d.likes.find({"user_id": uid}).sort(
            "created_at", DESCENDING
        )
    ]

    prompts = list(
        d.prompts.find({"_id": {"$in": ids}})
    )

    order = {str(x): i for i, x in enumerate(ids)}
    prompts.sort(key=lambda x: order.get(str(x["_id"]), 999999))

    return render_template(
        "user/liked_prompts.html",
        prompts=prompts
    )


# ============================================================
# PROMPT API
# ============================================================

def login_guard():
    if not user_doc():
        session["next_after_login"] = request.referrer or url_for("index")
        return jsonify(
            ok=False,
            login=True,
            redirect=url_for("user_login")
        ), 401
    return None


@app.post("/api/prompt/<pid>/like")
def like_prompt(pid):
    guard = login_guard()
    if guard:
        return guard

    p = prompt_by_id(pid)
    if not p:
        return jsonify(ok=False, error="Prompt not found"), 404

    d = get_db()
    uid = ObjectId(session["user_id"])
    oid = p["_id"]

    exists = d.likes.find_one({
        "user_id": uid,
        "prompt_id": oid
    })

    if exists:
        d.likes.delete_one({"_id": exists["_id"]})
        d.prompts.update_one(
            {"_id": oid},
            {"$max": {"likes": 0}, "$inc": {"likes": -1}}
        )
        liked = False
    else:
        try:
            d.likes.insert_one({
                "user_id": uid,
                "prompt_id": oid,
                "created_at": now_iso()
            })
            d.prompts.update_one(
                {"_id": oid},
                {"$inc": {"likes": 1}}
            )
            liked = True
        except DuplicateKeyError:
            liked = True

    current = d.prompts.find_one({"_id": oid})
    return jsonify(
        ok=True,
        liked=liked,
        likes=max(0, current.get("likes", 0))
    )


@app.post("/api/prompt/<pid>/save")
def save_prompt(pid):
    guard = login_guard()
    if guard:
        return guard

    p = prompt_by_id(pid)
    if not p:
        return jsonify(ok=False, error="Prompt not found"), 404

    d = get_db()
    uid = ObjectId(session["user_id"])
    oid = p["_id"]

    exists = d.saves.find_one({
        "user_id": uid,
        "prompt_id": oid
    })

    if exists:
        d.saves.delete_one({"_id": exists["_id"]})
        d.prompts.update_one(
            {"_id": oid},
            {"$max": {"saves": 0}, "$inc": {"saves": -1}}
        )
        saved = False
    else:
        try:
            d.saves.insert_one({
                "user_id": uid,
                "prompt_id": oid,
                "created_at": now_iso()
            })
            d.prompts.update_one(
                {"_id": oid},
                {"$inc": {"saves": 1}}
            )
            saved = True
        except DuplicateKeyError:
            saved = True

    return jsonify(ok=True, saved=saved)


@app.get("/api/prompt/<pid>/state")
def prompt_state(pid):
    p = prompt_by_id(pid)

    if not p:
        return jsonify(
            logged_in=bool(user_doc()),
            liked=False,
            saved=False
        )

    uid = session.get("user_id")
    if not uid:
        return jsonify(
            logged_in=False,
            liked=False,
            saved=False
        )

    d = get_db()
    oid = p["_id"]

    return jsonify(
        logged_in=True,
        liked=bool(d.likes.find_one({
            "user_id": uid,
            "prompt_id": oid
        })),
        saved=bool(d.saves.find_one({
            "user_id": uid,
            "prompt_id": oid
        }))
    )


@app.post("/api/prompt/<pid>/copy")
def copy_prompt(pid):
    p = prompt_by_id(pid)

    if not p:
        return jsonify(ok=False, error="Prompt not found"), 404

    d = get_db()
    oid = p["_id"]

    d.prompts.update_one(
        {"_id": oid},
        {"$inc": {"copies": 1}}
    )

    d.copy_events.insert_one({
        "user_id": session.get("user_id"),
        "prompt_id": oid,
        "created_at": now_iso()
    })

    current = d.prompts.find_one({"_id": oid})

    return jsonify(
        ok=True,
        copies=current.get("copies", 0)
    )


@app.get("/api/prompts")
def api_prompts():
    d = get_db()

    q = request.args.get("q", "").strip().lower()
    model = request.args.get("model", "All")
    category = request.args.get("category", "All")
    ptype = request.args.get("type", "All")
    use_case = request.args.get("use_case", "All")
    style = request.args.get("style", "All")
    subject = request.args.get("subject", "All")
    sort = request.args.get("sort", "newest")

    rows = list(
        d.prompts.find().sort("created_at", DESCENDING)
    )

    data = []

    for row in rows:
        x = serialize(row)

        hay = " ".join([
            str(x.get("title", "")),
            str(x.get("description", "")),
            str(x.get("prompt", "")),
            str(x.get("category", "")),
            str(x.get("model", "")),
            str(x.get("use_case", "")),
            str(x.get("style", "")),
            str(x.get("subject", "")),
            " ".join(x.get("tags_list", []))
        ]).lower()

        if q and q not in hay:
            continue

        if model != "All" and x.get("model") != model:
            continue

        if category != "All" and x.get("category") != category:
            continue

        if ptype != "All" and x.get("prompt_type") != ptype:
            continue

        if use_case != "All" and x.get("use_case") != use_case:
            continue

        if style != "All" and x.get("style") != style:
            continue

        if subject != "All" and x.get("subject") != subject:
            continue

        data.append(x)

    if sort == "trending":
        data.sort(key=lambda x: x["score"], reverse=True)
    elif sort == "likes":
        data.sort(key=lambda x: x.get("likes", 0), reverse=True)
    elif sort == "views":
        data.sort(key=lambda x: x.get("views", 0), reverse=True)

    return jsonify(data)


@app.get("/api/trending")
def api_trending():
    rows = [
        serialize(x)
        for x in get_db().prompts.find()
    ]

    rows.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return jsonify(rows[:30])


# ============================================================
# COMPATIBILITY ROUTE
# ============================================================

@app.route("/create-prompt")
@user_required
def create_prompt():
    return redirect(url_for("user_add_prompt"))


# ============================================================
# ERROR HANDLERS / START
# ============================================================

@app.errorhandler(413)
def too_large(e):
    flash(
        "Uploaded file is too large. Maximum is 10 MB.",
        "error"
    )
    return redirect(
        request.referrer or url_for("index")
    )


if __name__ == "__main__":
    try:
        init_db()
        create_default_admin()
        print(f"MongoDB connected: {MONGO_DB}")
        print("PromptVerse application started.")
        print("User Dashboard: http://127.0.0.1:5000/user/dashboard")
        print("Admin Dashboard: http://127.0.0.1:5000/admin/dashboard")
    except Exception as e:
        print("\nMongoDB connection/startup error:")
        print(e)
        print("\nCheck your .env file and MongoDB Atlas Network Access.")
        raise

    app.run(
        debug=True,
        host="127.0.0.1",
        port=5000
    )
