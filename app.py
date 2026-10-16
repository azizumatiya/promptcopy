import os
import re
import sqlite3
import secrets
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "promptverse.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@promptverse.local")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@12345")
ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp", "gif"}

CATEGORIES = ["Cinematic", "Photography", "Anime", "Fashion", "Fantasy", "Product", "Architecture", "3D"]
MODELS = ["Midjourney", "Flux", "Stable Diffusion", "Sora", "Veo", "DALL-E", "Gemini"]

def now():
    return datetime.utcnow().isoformat()

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        verified INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS prompts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT DEFAULT '',
        prompt TEXT NOT NULL,
        image TEXT NOT NULL,
        model TEXT NOT NULL,
        category TEXT NOT NULL,
        prompt_type TEXT NOT NULL DEFAULT 'image',
        tags TEXT DEFAULT '',
        views INTEGER NOT NULL DEFAULT 0,
        likes INTEGER NOT NULL DEFAULT 0,
        saves INTEGER NOT NULL DEFAULT 0,
        copies INTEGER NOT NULL DEFAULT 0,
        manual_featured INTEGER NOT NULL DEFAULT 0,
        manual_trending INTEGER NOT NULL DEFAULT 0,
        featured_order INTEGER NOT NULL DEFAULT 9999,
        trending_order INTEGER NOT NULL DEFAULT 9999,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS likes (
        user_id INTEGER NOT NULL,
        prompt_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, prompt_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS saves (
        user_id INTEGER NOT NULL,
        prompt_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(user_id, prompt_id),
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS views (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        prompt_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS copy_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        prompt_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY(prompt_id) REFERENCES prompts(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action TEXT NOT NULL,
        details TEXT DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        emoji TEXT DEFAULT '✨',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS password_resets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    for name, emoji in [
        ("Cinematic","🎬"),("Photography","📷"),("Anime","🎨"),("Fashion","👗"),
        ("Fantasy","🧙"),("Product","📦"),("Architecture","🏛️"),("3D","🧊")
    ]:
        conn.execute("INSERT OR IGNORE INTO categories(name,emoji,created_at) VALUES(?,?,?)", (name, emoji, now()))
    admin = conn.execute("SELECT id FROM users WHERE email=?", (ADMIN_EMAIL,)).fetchone()
    if not admin:
        conn.execute(
            "INSERT INTO users(email,password_hash,is_active,verified,created_at) VALUES(?,?,?,?,?)",
            (ADMIN_EMAIL, generate_password_hash(ADMIN_PASSWORD), 1, 1, now())
        )
    count = conn.execute("SELECT COUNT(*) c FROM prompts").fetchone()["c"]
    if count == 0:
        seed = [
            ("Cinematic Cyberpunk City","Futuristic city glowing under neon rain.",
             "A cinematic futuristic cyberpunk city at midnight, towering glass skyscrapers, neon reflections on wet streets, atmospheric fog, volumetric light rays, ultra detailed environment, anamorphic composition, deep shadows, 35mm film look.",
             "https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1400&q=85","Midjourney","Cinematic","image","cinematic,cyberpunk,neon,night,4k,realistic",2500,1240,840,91),
            ("Neon Tokyo Rain","Cinematic Tokyo street scene.",
             "Tokyo street at night during heavy rain, glowing Japanese signs, pedestrians with transparent umbrellas, reflections across wet pavement, cinematic cyberpunk mood, realistic urban photography, 35mm lens, atmospheric depth.",
             "https://images.unsplash.com/photo-1519501025264-65ba15a82390?auto=format&fit=crop&w=1400&q=85","Flux","Photography","image","tokyo,rain,neon,street,photography,cinematic",3100,1890,1180,88),
            ("Luxury Car Motion","High-end automotive commercial.",
             "Black luxury sports car driving through a rain-soaked city at night, headlights reflecting on wet asphalt, smooth tracking camera, subtle tire spray, cinematic motion blur, premium automotive commercial.",
             "https://images.unsplash.com/photo-1503376780353-7e6692767b70?auto=format&fit=crop&w=1400&q=85","Sora","Cinematic","video","car,luxury,commercial,motion,cinematic",2800,1670,1050,84),
            ("Anime Hero Character","Dynamic anime character concept art.",
             "Powerful anime hero standing on a ruined futuristic rooftop, wind moving through detailed clothing, glowing energy surrounding the character, dramatic sunset sky, cinematic anime composition, expressive eyes, dynamic perspective, highly detailed illustration.",
             "https://images.unsplash.com/photo-1578632767115-351597cf2477?auto=format&fit=crop&w=1400&q=85","Midjourney","Anime","image","anime,hero,character,illustration,4k",2200,1540,930,79),
            ("Editorial Fashion Portrait","High-end editorial portrait.",
             "High-fashion editorial portrait of a confident young woman, sculptural black outfit, minimalist studio, soft directional lighting, subtle film grain, luxury magazine aesthetic, natural skin texture, 85mm lens.",
             "https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=1400&q=85","Flux","Fashion","image","fashion,portrait,editorial,luxury,studio",1800,980,620,74),
            ("Mystical Forest","Atmospheric fantasy environment.",
             "Enchanted ancient forest at blue hour, enormous trees covered in glowing moss, tiny floating particles, mysterious fog between the roots, magical warm light in the distance, cinematic fantasy environment.",
             "https://images.unsplash.com/photo-1448375240586-882707db888b?auto=format&fit=crop&w=1400&q=85","Stable Diffusion","Fantasy","image","forest,fantasy,magic,fog,cinematic",1500,1120,710,69),
            ("Fantasy Castle Reveal","Epic fantasy video concept.",
             "Slow cinematic camera movement toward a massive fantasy castle above the clouds, sunrise breaking through mist, flying birds, enormous mountain peaks, magical atmosphere, realistic environmental motion.",
             "https://images.unsplash.com/photo-1518709268805-4e9042af9f23?auto=format&fit=crop&w=1400&q=85","Veo","Fantasy","video","castle,fantasy,mountains,cinematic,video",1400,1320,810,66),
            ("Minimal Product Photography","Premium product scene.",
             "Luxury skincare bottle centered on a sculptural stone pedestal, soft beige studio background, diffused sunlight, subtle shadows, premium commercial product photography, clean composition, realistic glass reflections.",
             "https://images.unsplash.com/photo-1556228578-8c89e6adf883?auto=format&fit=crop&w=1400&q=85","Stable Diffusion","Product","image","product,skincare,minimal,luxury,commercial",1200,870,510,62),
            ("Futuristic Architecture","Organic futuristic architecture.",
             "Monumental futuristic architecture emerging from a desert landscape, flowing organic concrete structures, enormous glass surfaces, soft morning haze, minimal human presence, architectural photography, realistic shadows.",
             "https://images.unsplash.com/photo-1487958449943-2429e8be8625?auto=format&fit=crop&w=1400&q=85","Flux","Architecture","image","architecture,futuristic,desert,minimal,design",1000,720,420,58),
            ("3D Glass Character","Minimal 3D character render.",
             "Cute abstract 3D character made from translucent glass, soft pastel environment, studio lighting, realistic caustics, smooth rounded geometry, premium 3D illustration, minimal composition.",
             "https://images.unsplash.com/photo-1634017839464-5c339ebe3cb4?auto=format&fit=crop&w=1400&q=85","Stable Diffusion","3D","image","3d,glass,pastel,character,render",900,650,390,54),
            ("Luxury Watch Campaign","Cinematic luxury product campaign.",
             "Luxury mechanical wristwatch floating above black volcanic stone, dramatic single-source lighting, sharp metallic reflections, deep black background, subtle smoke, premium advertising photography.",
             "https://images.unsplash.com/photo-1524805444758-089113d48a6d?auto=format&fit=crop&w=1400&q=85","Midjourney","Product","image","watch,luxury,product,black,advertising",1600,1350,770,51),
            ("Animated Product Reveal","Short cinematic product reveal.",
             "Cinematic product reveal of a premium wireless headphone emerging from darkness, slow camera push-in, controlled studio lighting, subtle floating particles, glossy material reflections, luxury technology commercial.",
             "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?auto=format&fit=crop&w=1400&q=85","Sora","Product","video","headphones,technology,commercial,video,cinematic",1700,1450,880,49),
        ]
        base = datetime.utcnow()
        for i, p in enumerate(seed):
            created = (base - timedelta(days=i)).isoformat()
            conn.execute("""INSERT INTO prompts
                (title,description,prompt,image,model,category,prompt_type,tags,views,likes,saves,copies,growth,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                p[:12] + (created, created))
    conn.commit()
    conn.close()

def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return get_db().execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin login required.", "error")
            return redirect(url_for("admin_login"))
        return fn(*args, **kwargs)
    return wrapper

def log_action(action, details=""):
    get_db().execute("INSERT INTO activity_logs(action,details,created_at) VALUES(?,?,?)", (action, details, now()))
    get_db().commit()

def parse_tags(raw):
    raw = raw or ""
    parts = re.split(r"[,\n]+", raw)
    return [x.strip().lower().lstrip("#") for x in parts if x.strip()]

def row_to_dict(row):
    d = dict(row)
    d["tags_list"] = parse_tags(d.get("tags", ""))
    created = datetime.fromisoformat(d["created_at"])
    d["is_new"] = created >= datetime.utcnow() - timedelta(days=7)
    # Score uses recency decay.
    age_days = max((datetime.utcnow() - created).total_seconds() / 86400, 0)
    decay = max(0.15, 1 / (1 + age_days / 7))
    d["score"] = round((d["likes"]*4 + d["copies"]*3 + d["views"] + d["saves"]*3) * decay + (500 if d["manual_trending"] else 0), 2)
    d["hot"] = d["score"] >= 1500 or d["likes"] >= 1000
    return d

@app.context_processor
def inject_globals():
    return {
        "current_user": current_user(),
        "is_admin": bool(session.get("is_admin")),
        "categories": get_db().execute("SELECT * FROM categories ORDER BY name").fetchall(),
        "datetime": datetime,
        "config_admin_email": ADMIN_EMAIL
    }

@app.route("/")
def index():
    return render_template("index.html", models=MODELS)

@app.route("/prompt/<int:prompt_id>")
def prompt_detail(prompt_id):
    conn = get_db()
    p = conn.execute("SELECT * FROM prompts WHERE id=?", (prompt_id,)).fetchone()
    if not p:
        return "Prompt not found", 404
    conn.execute("UPDATE prompts SET views=views+1 WHERE id=?", (prompt_id,))
    conn.execute("INSERT INTO views(user_id,prompt_id,created_at) VALUES(?,?,?)", (session.get("user_id"), prompt_id, now()))
    conn.commit()
    p = conn.execute("SELECT * FROM prompts WHERE id=?", (prompt_id,)).fetchone()
    related = conn.execute("""SELECT * FROM prompts WHERE id!=? AND (category=? OR model=?)
                              ORDER BY CASE WHEN category=? THEN 0 ELSE 1 END, id DESC LIMIT 4""",
                           (prompt_id,p["category"],p["model"],p["category"])).fetchall()
    return render_template("prompt.html", prompt=p, related=related)

@app.route("/explore")
def explore():
    return render_template("index.html", models=MODELS, explore_mode=True)

@app.route("/library")
def library():
    if not current_user():
        session["next_after_login"] = url_for("library")
        return redirect(url_for("login"))
    conn = get_db()
    saved = conn.execute("""SELECT p.* FROM prompts p JOIN saves s ON s.prompt_id=p.id
                            WHERE s.user_id=? ORDER BY s.created_at DESC""", (session["user_id"],)).fetchall()
    liked = conn.execute("""SELECT p.* FROM prompts p JOIN likes l ON l.prompt_id=p.id
                            WHERE l.user_id=? ORDER BY l.created_at DESC""", (session["user_id"],)).fetchall()
    recent = conn.execute("""SELECT p.* FROM prompts p JOIN views v ON v.prompt_id=p.id
                             WHERE v.user_id=? GROUP BY p.id ORDER BY MAX(v.created_at) DESC LIMIT 20""",
                          (session["user_id"],)).fetchall()
    return render_template("library.html", saved=saved, liked=liked, recent=recent)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) or len(password) < 6:
            flash("Enter a valid email and password with at least 6 characters.", "error")
        else:
            try:
                get_db().execute("INSERT INTO users(email,password_hash,created_at) VALUES(?,?,?)",
                                 (email, generate_password_hash(password), now()))
                get_db().commit()
                flash("Account created. You can now log in.", "success")
                return redirect(url_for("login"))
            except sqlite3.IntegrityError:
                flash("That email is already registered.", "error")
    return render_template("auth.html", mode="signup")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        password = request.form.get("password","")
        user = get_db().execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if user and user["is_active"] and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["id"]
            nxt = session.pop("next_after_login", None)
            return redirect(nxt or url_for("index"))
        flash("Invalid email/password or disabled account.", "error")
    return render_template("auth.html", mode="login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/forgot-password", methods=["GET","POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        user = get_db().execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if user:
            token = secrets.token_urlsafe(32)
            expires = (datetime.utcnow()+timedelta(minutes=30)).isoformat()
            get_db().execute("INSERT INTO password_resets(user_id,token,expires_at) VALUES(?,?,?)", (user["id"],token,expires))
            get_db().commit()
            # Demo mode: show reset link. In production, send it by email.
            flash("Demo reset link: " + url_for("reset_password", token=token, _external=True), "success")
        else:
            flash("If the account exists, a reset link has been generated.", "success")
    return render_template("forgot.html")

@app.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    r = get_db().execute("SELECT * FROM password_resets WHERE token=? AND used=0", (token,)).fetchone()
    if not r or datetime.fromisoformat(r["expires_at"]) < datetime.utcnow():
        return "Reset link expired or invalid.", 400
    if request.method == "POST":
        password = request.form.get("password","")
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
        else:
            get_db().execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password),r["user_id"]))
            get_db().execute("UPDATE password_resets SET used=1 WHERE id=?", (r["id"],))
            get_db().commit()
            flash("Password changed. Please log in.", "success")
            return redirect(url_for("login"))
    return render_template("reset.html", token=token)

def require_login_action():
    if not current_user():
        session["next_after_login"] = request.referrer or url_for("index")
        return jsonify({"ok":False,"login":True,"redirect":url_for("login")}), 401
    return None

@app.post("/api/prompt/<int:prompt_id>/like")
def like_prompt(prompt_id):
    guard = require_login_action()
    if guard: return guard
    conn = get_db(); uid = session["user_id"]
    exists = conn.execute("SELECT 1 FROM likes WHERE user_id=? AND prompt_id=?", (uid,prompt_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM likes WHERE user_id=? AND prompt_id=?", (uid,prompt_id))
        conn.execute("UPDATE prompts SET likes=MAX(likes-1,0) WHERE id=?", (prompt_id,))
        liked=False
    else:
        conn.execute("INSERT INTO likes VALUES(?,?,?)", (uid,prompt_id,now()))
        conn.execute("UPDATE prompts SET likes=likes+1 WHERE id=?", (prompt_id,))
        liked=True
    conn.commit()
    likes=conn.execute("SELECT likes FROM prompts WHERE id=?", (prompt_id,)).fetchone()["likes"]
    return jsonify(ok=True,liked=liked,likes=likes)

@app.post("/api/prompt/<int:prompt_id>/save")
def save_prompt(prompt_id):
    guard = require_login_action()
    if guard: return guard
    conn=get_db(); uid=session["user_id"]
    exists=conn.execute("SELECT 1 FROM saves WHERE user_id=? AND prompt_id=?", (uid,prompt_id)).fetchone()
    if exists:
        conn.execute("DELETE FROM saves WHERE user_id=? AND prompt_id=?", (uid,prompt_id))
        conn.execute("UPDATE prompts SET saves=MAX(saves-1,0) WHERE id=?", (prompt_id,))
        saved=False
    else:
        conn.execute("INSERT INTO saves VALUES(?,?,?)", (uid,prompt_id,now()))
        conn.execute("UPDATE prompts SET saves=saves+1 WHERE id=?", (prompt_id,))
        saved=True
    conn.commit()
    return jsonify(ok=True,saved=saved)

@app.get("/api/prompt/<int:prompt_id>/state")
def prompt_state(prompt_id):
    uid=session.get("user_id")
    if not uid: return jsonify(logged_in=False,liked=False,saved=False)
    conn=get_db()
    return jsonify(
        logged_in=True,
        liked=bool(conn.execute("SELECT 1 FROM likes WHERE user_id=? AND prompt_id=?", (uid,prompt_id)).fetchone()),
        saved=bool(conn.execute("SELECT 1 FROM saves WHERE user_id=? AND prompt_id=?", (uid,prompt_id)).fetchone())
    )

@app.post("/api/prompt/<int:prompt_id>/copy")
def copy_prompt(prompt_id):
    conn=get_db()
    conn.execute("UPDATE prompts SET copies=copies+1 WHERE id=?", (prompt_id,))
    conn.execute("INSERT INTO copy_events(user_id,prompt_id,created_at) VALUES(?,?,?)", (session.get("user_id"),prompt_id,now()))
    conn.commit()
    return jsonify(ok=True)

@app.get("/api/prompts")
def api_prompts():
    conn=get_db()
    q=request.args.get("q","").strip().lower()
    model=request.args.get("model","All")
    category=request.args.get("category","All")
    ptype=request.args.get("type","All")
    sort=request.args.get("sort","newest")
    rows=conn.execute("SELECT * FROM prompts ORDER BY id DESC").fetchall()
    data=[]
    for row in rows:
        d=row_to_dict(row)
        hay=" ".join([d["title"],d["description"],d["prompt"],d["category"],d["model"],d["tags"]]).lower()
        if q and q not in hay: continue
        if model!="All" and d["model"]!=model: continue
        if category!="All" and d["category"]!=category: continue
        if ptype!="All" and d["prompt_type"]!=ptype: continue
        data.append(d)
    if sort=="trending": data.sort(key=lambda x:x["score"], reverse=True)
    elif sort=="likes": data.sort(key=lambda x:x["likes"], reverse=True)
    else: data.sort(key=lambda x:x["id"], reverse=True)
    return jsonify(data)

@app.get("/api/trending")
def api_trending():
    rows=get_db().execute("SELECT * FROM prompts").fetchall()
    data=[row_to_dict(r) for r in rows]
    manual=sorted([x for x in data if x["manual_trending"]], key=lambda x:(x["trending_order"],-x["score"]))
    automatic=sorted([x for x in data if not x["manual_trending"]], key=lambda x:x["score"], reverse=True)
    return jsonify((manual+automatic)[:30])

@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")
        if email==ADMIN_EMAIL.lower() and secrets.compare_digest(password, ADMIN_PASSWORD):
            session.clear(); session["is_admin"]=True
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.","error")
    return render_template("admin_login.html")

@app.post("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))

@app.get("/admin")
@admin_required
def admin_dashboard():
    conn=get_db()
    stats={
        "users":conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"],
        "prompts":conn.execute("SELECT COUNT(*) c FROM prompts").fetchone()["c"],
        "likes":conn.execute("SELECT COALESCE(SUM(likes),0) c FROM prompts").fetchone()["c"],
        "saves":conn.execute("SELECT COALESCE(SUM(saves),0) c FROM prompts").fetchone()["c"],
        "copies":conn.execute("SELECT COALESCE(SUM(copies),0) c FROM prompts").fetchone()["c"],
        "views":conn.execute("SELECT COALESCE(SUM(views),0) c FROM prompts").fetchone()["c"],
    }
    prompts=conn.execute("SELECT * FROM prompts ORDER BY id DESC").fetchall()
    users=conn.execute("SELECT * FROM users ORDER BY id DESC LIMIT 100").fetchall()
    logs=conn.execute("SELECT * FROM activity_logs ORDER BY id DESC LIMIT 50").fetchall()
    return render_template("admin.html",stats=stats,prompts=prompts,users=users,logs=logs,models=MODELS,categories=CATEGORIES)

@app.post("/admin/prompts/add")
@admin_required
def admin_add_prompt():
    title=request.form.get("title","").strip()
    description=request.form.get("description","").strip()
    prompt=request.form.get("prompt","").strip()
    image=request.form.get("image","").strip()
    model=request.form.get("model","Midjourney").strip()
    category=request.form.get("category","Cinematic").strip()
    ptype=request.form.get("prompt_type","image").strip()
    tags=",".join(parse_tags(request.form.get("tags","")))
    upload=request.files.get("image_file")
    if upload and upload.filename:
        ext=upload.filename.rsplit(".",1)[-1].lower()
        if ext not in ALLOWED_IMAGES:
            flash("Unsupported image format.","error")
            return redirect(url_for("admin_dashboard"))
        filename=secure_filename(datetime.utcnow().strftime("%Y%m%d%H%M%S%f")+"_"+upload.filename)
        upload.save(os.path.join(UPLOAD_DIR,filename))
        image=url_for("static",filename="uploads/"+filename)
    if not title or not prompt or not image:
        flash("Title, prompt and image are required.","error")
        return redirect(url_for("admin_dashboard"))
    conn=get_db()
    duplicate=conn.execute("SELECT id,title FROM prompts WHERE lower(trim(prompt))=lower(trim(?))", (prompt,)).fetchone()
    if duplicate:
        flash(f"Duplicate prompt detected: #{duplicate['id']} {duplicate['title']}","error")
        return redirect(url_for("admin_dashboard"))
    conn.execute("""INSERT INTO prompts(title,description,prompt,image,model,category,prompt_type,tags,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?)""",
                 (title,description,prompt,image,model,category,ptype,tags,now(),now()))
    conn.commit()
    log_action("ADD_PROMPT", title)
    flash("Prompt added successfully and placed first in Newest.","success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/prompts/<int:pid>/edit")
@admin_required
def admin_edit_prompt(pid):
    conn=get_db()
    old=conn.execute("SELECT * FROM prompts WHERE id=?", (pid,)).fetchone()
    if not old: return "Not found",404
    title=request.form.get("title","").strip()
    description=request.form.get("description","").strip()
    prompt=request.form.get("prompt","").strip()
    image=request.form.get("image","").strip()
    model=request.form.get("model","Midjourney")
    category=request.form.get("category","Cinematic")
    ptype=request.form.get("prompt_type","image")
    tags=",".join(parse_tags(request.form.get("tags","")))
    if not image: image=old["image"]
    conn.execute("""UPDATE prompts SET title=?,description=?,prompt=?,image=?,model=?,category=?,prompt_type=?,tags=?,updated_at=? WHERE id=?""",
                 (title,description,prompt,image,model,category,ptype,tags,now(),pid))
    conn.commit(); log_action("EDIT_PROMPT",f"#{pid} {title}")
    flash("Prompt updated.","success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/prompts/<int:pid>/delete")
@admin_required
def admin_delete_prompt(pid):
    conn=get_db(); row=conn.execute("SELECT title FROM prompts WHERE id=?", (pid,)).fetchone()
    conn.execute("DELETE FROM prompts WHERE id=?", (pid,)); conn.commit()
    log_action("DELETE_PROMPT",f"#{pid} {row['title'] if row else ''}")
    flash("Prompt deleted.","success")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/prompts/<int:pid>/toggle-featured")
@admin_required
def toggle_featured(pid):
    conn=get_db()
    row=conn.execute("SELECT manual_featured FROM prompts WHERE id=?", (pid,)).fetchone()
    conn.execute("UPDATE prompts SET manual_featured=? WHERE id=?", (0 if row["manual_featured"] else 1,pid))
    conn.commit(); log_action("TOGGLE_FEATURED",f"#{pid}")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/prompts/<int:pid>/toggle-trending")
@admin_required
def toggle_trending(pid):
    conn=get_db()
    row=conn.execute("SELECT manual_trending FROM prompts WHERE id=?", (pid,)).fetchone()
    conn.execute("UPDATE prompts SET manual_trending=? WHERE id=?", (0 if row["manual_trending"] else 1,pid))
    conn.commit(); log_action("TOGGLE_TRENDING",f"#{pid}")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/prompts/<int:pid>/reorder")
@admin_required
def reorder_prompt(pid):
    field=request.form.get("field","featured_order")
    value=request.form.get("value","9999")
    if field not in {"featured_order","trending_order"}: return "Bad field",400
    try: value=max(1,min(9999,int(value)))
    except: value=9999
    get_db().execute(f"UPDATE prompts SET {field}=? WHERE id=?", (value,pid))
    get_db().commit(); log_action("REORDER_PROMPT",f"#{pid} {field}={value}")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/users/<int:uid>/toggle")
@admin_required
def toggle_user(uid):
    conn=get_db()
    row=conn.execute("SELECT is_active,email FROM users WHERE id=?", (uid,)).fetchone()
    if not row: return "Not found",404
    conn.execute("UPDATE users SET is_active=? WHERE id=?", (0 if row["is_active"] else 1,uid))
    conn.commit(); log_action("TOGGLE_USER",row["email"])
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/categories/add")
@admin_required
def add_category():
    name=request.form.get("name","").strip()
    emoji=request.form.get("emoji","✨").strip()
    if name:
        try:
            get_db().execute("INSERT INTO categories(name,emoji,created_at) VALUES(?,?,?)",(name,emoji,now()))
            get_db().commit(); log_action("ADD_CATEGORY",name)
        except sqlite3.IntegrityError:
            flash("Category already exists.","error")
    return redirect(url_for("admin_dashboard"))

@app.post("/admin/categories/<int:cid>/delete")
@admin_required
def delete_category(cid):
    conn=get_db()
    row=conn.execute("SELECT name FROM categories WHERE id=?", (cid,)).fetchone()
    if row:
        used=conn.execute("SELECT COUNT(*) c FROM prompts WHERE category=?", (row["name"],)).fetchone()["c"]
        if used:
            flash("Cannot delete a category currently used by prompts.","error")
        else:
            conn.execute("DELETE FROM categories WHERE id=?", (cid,)); conn.commit()
            log_action("DELETE_CATEGORY",row["name"])
    return redirect(url_for("admin_dashboard"))

@app.get("/admin/analytics")
@admin_required
def admin_analytics():
    conn=get_db()
    days=int(request.args.get("days","7"))
    days=days if days in (1,7,30,3650) else 7
    cutoff=(datetime.utcnow()-timedelta(days=days)).isoformat()
    activity=conn.execute("""SELECT substr(created_at,1,10) day, COUNT(*) count
                             FROM views WHERE created_at>=? GROUP BY day ORDER BY day""",(cutoff,)).fetchall()
    copies=conn.execute("""SELECT substr(created_at,1,10) day, COUNT(*) count
                            FROM copy_events WHERE created_at>=? GROUP BY day ORDER BY day""",(cutoff,)).fetchall()
    return jsonify(days=days, views=[dict(x) for x in activity], copies=[dict(x) for x in copies])

@app.route("/create-prompt")
def create_prompt():
    return render_template("create_prompt.html")

@app.errorhandler(413)
def too_large(e):
    flash("Uploaded file is too large. Maximum is 10 MB.","error")
    return redirect(request.referrer or url_for("index"))

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
