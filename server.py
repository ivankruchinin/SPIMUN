#!/usr/bin/env python3
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import json, os, hashlib, secrets, time, uuid

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

DATA_DIR      = "/var/www/html/data"
USERS_FILE    = os.path.join(DATA_DIR, "users.json")
TOKENS_FILE   = os.path.join(DATA_DIR, "tokens.json")
ARTICLES_FILE = os.path.join(DATA_DIR, "articles.json")
IMAGES_DIR    = "/var/www/html/article-images"
FILES_DIR     = "/var/www/html/article-files"

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(IMAGES_DIR, exist_ok=True)
os.makedirs(FILES_DIR, exist_ok=True)


def load(path, default):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return default


def save(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def get_user_by_email(email):
    return load(USERS_FILE, {}).get(email.lower())


def get_user_from_token(token):
    tokens = load(TOKENS_FILE, {})
    entry = tokens.get(token)
    if not entry:
        return None
    if entry["expires"] < time.time():
        tokens.pop(token)
        save(TOKENS_FILE, tokens)
        return None
    return get_user_by_email(entry["email"])


def require_auth():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    user = get_user_from_token(token)
    if not user:
        return None, jsonify({"error": "Unauthorized"}), 401
    return user, None, None


def require_admin():
    user, err, code = require_auth()
    if err:
        return None, err, code
    if user.get("role") != "admin":
        return None, jsonify({"error": "Admin only"}), 403
    return user, None, None


def extract_text_from_pdf(pdf_path):
    try:
        import fitz
        doc = fitz.open(pdf_path)
        paragraphs = []
        for page in doc:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))
            for block in blocks:
                text = block[4].strip()
                if text and len(text) > 20:
                    paragraphs.append(text)
        doc.close()
        return "\n\n".join(paragraphs)
    except Exception:
        return ""


# ── AUTH ──────────────────────────────────────────────────────────────────────

@app.route("/api/register", methods=["POST"])
def register():
    d = request.json or {}
    email = (d.get("email") or "").strip().lower()
    password = (d.get("password") or "").strip()
    name = (d.get("name") or "").strip()
    school = (d.get("school") or "").strip()
    if not email or not password or not name:
        return jsonify({"error": "Name, email and password are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400
    users = load(USERS_FILE, {})
    if email in users:
        return jsonify({"error": "An account with this email already exists"}), 409
    users[email] = {
        "email": email, "name": name, "school": school,
        "password": hash_pw(password), "role": "delegate",
        "committee": None, "country": None, "notes": "",
        "created": time.strftime("%Y-%m-%d %H:%M")
    }
    save(USERS_FILE, users)
    return jsonify({"ok": True, "message": "Account created. Welcome to SPIMUN!"})


@app.route("/api/login", methods=["POST"])
def login():
    d = request.json or {}
    email = (d.get("email") or "").strip().lower()
    password = (d.get("password") or "").strip()
    user = get_user_by_email(email)
    if not user or user["password"] != hash_pw(password):
        return jsonify({"error": "Incorrect email or password"}), 401
    token = secrets.token_hex(32)
    tokens = load(TOKENS_FILE, {})
    tokens[token] = {"email": email, "expires": time.time() + 60 * 60 * 24 * 7}
    save(TOKENS_FILE, tokens)
    return jsonify({"ok": True, "token": token, "user": {
        "name": user["name"], "email": user["email"], "school": user["school"],
        "role": user["role"], "committee": user["committee"],
        "country": user["country"], "notes": user["notes"]
    }})


@app.route("/api/me", methods=["GET"])
def me():
    user, err, code = require_auth()
    if err:
        return err, code
    return jsonify({
        "name": user["name"], "email": user["email"], "school": user["school"],
        "role": user["role"], "committee": user["committee"],
        "country": user["country"], "notes": user["notes"]
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    tokens = load(TOKENS_FILE, {})
    tokens.pop(token, None)
    save(TOKENS_FILE, tokens)
    return jsonify({"ok": True})


@app.route("/api/change-password", methods=["POST"])
def change_password():
    user, err, code = require_auth()
    if err:
        return err, code
    d = request.json or {}
    old_pw = (d.get("old_password") or "").strip()
    new_pw = (d.get("new_password") or "").strip()
    if user["password"] != hash_pw(old_pw):
        return jsonify({"error": "Current password is incorrect"}), 400
    if len(new_pw) < 6:
        return jsonify({"error": "New password must be at least 6 characters"}), 400
    users = load(USERS_FILE, {})
    users[user["email"]]["password"] = hash_pw(new_pw)
    save(USERS_FILE, users)
    return jsonify({"ok": True, "message": "Password updated"})


# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.route("/api/admin/delegates", methods=["GET"])
def admin_list():
    _, err, code = require_admin()
    if err:
        return err, code
    users = load(USERS_FILE, {})
    result = sorted([{
        "email": u["email"], "name": u["name"], "school": u["school"],
        "role": u["role"], "committee": u["committee"], "country": u["country"],
        "notes": u["notes"], "created": u.get("created", "")
    } for u in users.values()], key=lambda x: x["name"])
    return jsonify(result)


@app.route("/api/admin/assign", methods=["POST"])
def admin_assign():
    _, err, code = require_admin()
    if err:
        return err, code
    d = request.json or {}
    email = (d.get("email") or "").lower()
    users = load(USERS_FILE, {})
    if email not in users:
        return jsonify({"error": "User not found"}), 404
    for field in ["committee", "country", "notes", "role"]:
        if d.get(field) is not None:
            users[email][field] = d[field]
    save(USERS_FILE, users)
    return jsonify({"ok": True})


@app.route("/api/admin/delete", methods=["POST"])
def admin_delete():
    _, err, code = require_admin()
    if err:
        return err, code
    email = (request.json or {}).get("email", "").lower()
    users = load(USERS_FILE, {})
    if email not in users:
        return jsonify({"error": "User not found"}), 404
    del users[email]
    save(USERS_FILE, users)
    return jsonify({"ok": True})


@app.route("/api/admin/announcement", methods=["GET", "POST"])
def announcement():
    ann_file = os.path.join(DATA_DIR, "announcement.json")
    if request.method == "GET":
        return jsonify(load(ann_file, {"text": "", "active": False}))
    _, err, code = require_admin()
    if err:
        return err, code
    save(ann_file, request.json)
    return jsonify({"ok": True})


# ── ARTICLES ──────────────────────────────────────────────────────────────────

@app.route("/api/articles", methods=["GET"])
def get_articles():
    articles = load(ARTICLES_FILE, [])
    published = [
        {k: v for k, v in a.items() if k != "body"}
        for a in articles if a.get("published", True)
    ]
    published.sort(key=lambda x: x.get("date", ""), reverse=True)
    return jsonify(published)


@app.route("/api/articles/<article_id>", methods=["GET"])
def get_article(article_id):
    for a in load(ARTICLES_FILE, []):
        if a["id"] == article_id and a.get("published", True):
            return jsonify(a)
    return jsonify({"error": "Article not found"}), 404


@app.route("/api/admin/articles", methods=["GET"])
def admin_get_articles():
    _, err, code = require_admin()
    if err:
        return err, code
    articles = load(ARTICLES_FILE, [])
    articles.sort(key=lambda x: x.get("date", ""), reverse=True)
    return jsonify(articles)


@app.route("/api/admin/articles/<article_id>", methods=["GET"])
def admin_get_article(article_id):
    _, err, code = require_admin()
    if err:
        return err, code
    for a in load(ARTICLES_FILE, []):
        if a["id"] == article_id:
            return jsonify(a)
    return jsonify({"error": "Article not found"}), 404


@app.route("/api/admin/articles", methods=["POST"])
def create_article():
    user, err, code = require_admin()
    if err:
        return err, code
    d = request.json or {}
    title = (d.get("title") or "").strip()
    if not title:
        return jsonify({"error": "Title is required"}), 400
    article = {
        "id":        str(uuid.uuid4())[:8],
        "title":     title,
        "summary":   (d.get("summary") or "").strip() or "Click to read this article.",
        "body":      (d.get("body") or "").strip(),
        "pdf_url":   d.get("pdf_url"),
        "pages":     d.get("pages", []),
        "image":     d.get("image_url"),
        "author":    user["name"],
        "date":      time.strftime("%Y-%m-%d"),
        "published": d.get("published", True)
    }
    articles = load(ARTICLES_FILE, [])
    articles.append(article)
    save(ARTICLES_FILE, articles)
    return jsonify({"ok": True, "id": article["id"]})


@app.route("/api/admin/articles/<article_id>", methods=["PUT"])
def update_article(article_id):
    _, err, code = require_admin()
    if err:
        return err, code
    d = request.json or {}
    articles = load(ARTICLES_FILE, [])
    for i, a in enumerate(articles):
        if a["id"] == article_id:
            for field in ["title", "summary", "body", "pdf_url", "pages", "published"]:
                if field in d:
                    articles[i][field] = d[field]
            if "image_url" in d:
                articles[i]["image"] = d["image_url"]
            articles[i]["edited"] = time.strftime("%Y-%m-%d %H:%M")
            save(ARTICLES_FILE, articles)
            return jsonify({"ok": True})
    return jsonify({"error": "Article not found"}), 404


@app.route("/api/admin/articles/<article_id>", methods=["DELETE"])
def delete_article(article_id):
    _, err, code = require_admin()
    if err:
        return err, code
    articles = [a for a in load(ARTICLES_FILE, []) if a["id"] != article_id]
    save(ARTICLES_FILE, articles)
    return jsonify({"ok": True})


# ── FILE UPLOADS ──────────────────────────────────────────────────────────────

@app.route("/api/admin/upload-pdf", methods=["POST"])
def upload_pdf():
    user, err, code = require_admin()
    if err:
        return err, code
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    if not f.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files are allowed"}), 400

    article_id = str(uuid.uuid4())
    pdf_dir = os.path.join(FILES_DIR, article_id)
    os.makedirs(pdf_dir, exist_ok=True)
    pdf_path = os.path.join(pdf_dir, "original.pdf")
    f.save(pdf_path)

    pages = []
    try:
        import fitz
        doc = fitz.open(pdf_path)
        for i, page in enumerate(doc):
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_filename = f"page-{i+1}.jpg"
            pix.save(os.path.join(pdf_dir, img_filename))
            pages.append(f"/article-files/{article_id}/{img_filename}")
        doc.close()
    except Exception as e:
        return jsonify({"error": f"Could not convert PDF: {str(e)}"}), 500

    extracted_text = extract_text_from_pdf(pdf_path)

    return jsonify({
        "ok": True,
        "url": f"/article-files/{article_id}/original.pdf",
        "pages": pages,
        "extracted_text": extracted_text
    })


@app.route("/api/admin/upload-image", methods=["POST"])
def upload_image():
    user, err, code = require_admin()
    if err:
        return err, code
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    ext = os.path.splitext(f.filename.lower())[1]
    if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
        return jsonify({"error": "Only JPG, PNG or WebP images allowed"}), 400
    filename = str(uuid.uuid4()) + ext
    f.save(os.path.join(IMAGES_DIR, filename))
    return jsonify({"ok": True, "url": "/article-images/" + filename})

# ── GALLERY ──────────────────────────────────────────────────────────────────

GALLERY_FILE = os.path.join(DATA_DIR, "gallery.json")
GALLERY_DIR  = "/var/www/html/gallery"
os.makedirs(GALLERY_DIR, exist_ok=True)

def load_gallery():
    if os.path.exists(GALLERY_FILE):
        return load(GALLERY_FILE, [])
    # Seed with existing hardcoded photos
    default = [
        {"id":"1","url":"photos/pic1.jpeg"},
        {"id":"2","url":"photos/pic2.jpeg"},
        {"id":"3","url":"photos/pic3.jpeg"},
        {"id":"4","url":"photos/pic5.jpeg"},
        {"id":"5","url":"photos/pic16.png"},
        {"id":"6","url":"photos/pic7.png"},
        {"id":"7","url":"photos/pic9.png"},
        {"id":"8","url":"photos/pic10.png"},
        {"id":"9","url":"photos/pic11.png"},
        {"id":"10","url":"photos/pic12.png"},
        {"id":"11","url":"photos/pic13.png"},
        {"id":"12","url":"photos/pic14.png"},
    ]
    save(GALLERY_FILE, default)
    return default

@app.route("/api/gallery", methods=["GET"])
def get_gallery():
    return jsonify(load_gallery())

@app.route("/api/admin/gallery", methods=["POST"])
def upload_gallery_image():
    _, err, code = require_admin()
    if err: return err, code
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    f = request.files["file"]
    ext = os.path.splitext(f.filename.lower())[1]
    if ext not in [".jpg",".jpeg",".png",".webp",".avif"]:
        return jsonify({"error": "Only JPG, PNG, WebP or AVIF allowed"}), 400
    filename = str(uuid.uuid4()) + ext
    f.save(os.path.join(GALLERY_DIR, filename))
    url = "/gallery/" + filename
    photos = load_gallery()
    new_id = str(int(time.time()*1000))
    photos.append({"id": new_id, "url": url})
    save(GALLERY_FILE, photos)
    return jsonify({"ok": True, "id": new_id, "url": url})

@app.route("/api/admin/gallery/<photo_id>", methods=["DELETE"])
def delete_gallery_image(photo_id):
    _, err, code = require_admin()
    if err: return err, code
    photos = load_gallery()
    photo = next((p for p in photos if p["id"] == photo_id), None)
    if not photo:
        return jsonify({"error": "Photo not found"}), 404
    # Delete file if it's in our gallery folder
    if photo["url"].startswith("/gallery/"):
        filepath = "/var/www/html" + photo["url"]
        if os.path.exists(filepath):
            os.remove(filepath)
    photos = [p for p in photos if p["id"] != photo_id]
    save(GALLERY_FILE, photos)
    return jsonify({"ok": True})



# ── STATIC FILES ──────────────────────────────────────────────────────────────

@app.route("/article-files/<path:filename>")
def serve_article_file(filename):
    return send_from_directory(FILES_DIR, filename)


@app.route("/article-images/<filename>")
def serve_article_image(filename):
    return send_from_directory(IMAGES_DIR, filename)

@app.route("/gallery/<filename>")
def serve_gallery(filename):
    return send_from_directory(GALLERY_DIR, filename)


# ── BOOT ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    users = load(USERS_FILE, {})
    if not users:
        users["admin@spimun.org"] = {
            "email": "admin@spimun.org", "name": "Secretariat",
            "school": "St. Peter's International School",
            "password": hash_pw("spimun2026admin"), "role": "admin",
            "committee": None, "country": None, "notes": "",
            "created": time.strftime("%Y-%m-%d %H:%M")
        }
        save(USERS_FILE, users)
        print("Default admin created: admin@spimun.org / spimun2026admin")

    print("SPIMUN server running on http://localhost:5001")
    app.run(host="127.0.0.1", port=5001, debug=False)