from flask import Flask
from database import init_db, get_db, close_db
from sqlite3 import IntegrityError
import os
from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from sqlite3 import IntegrityError
from database import get_db


app = Flask(__name__)

app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
)

@app.teardown_appcontext                         
def teardown_db(exception):
    close_db()


@app.route("/")
def home():
    return "Home OK", 200

@app.route("/health")
def health():
    return "OK", 200

@app.route("/init-db")
def init_database():
    init_db()
    return "Database initialized!"

# Yeni: kullanıcı ekle
@app.route("/add-user/<name>/<email>")
def add_user(name, email):
    db = get_db()
    try:
        with db:  # auto-commit, hata olursa rollback
            db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                (name, email)
            )
        return {"message": f"{name} eklendi"}, 201
    except IntegrityError:
        return {"error": "Bu email zaten kayıtlı"}, 409

# Yeni: kullanıcıları listele
@app.route("/list-users")
def list_users():
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    return {"users": [dict(u) for u in users]}

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not name or not email or not password:
        return jsonify({"error": "name, email, password required"}), 400

    pw_hash = generate_password_hash(password)

    db = get_db()
    try:
        with db:
            cur = db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, pw_hash),
            )
        user_id = cur.lastrowid
        session["user_id"] = user_id  # giriş yapmış gibi kabul et
        return jsonify({"id": user_id, "name": name, "email": email}), 201
    except IntegrityError:
        return jsonify({"error": "email already exists"}), 409
    
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401

    session["user_id"] = row["id"]  # giriş başarılı → session kaydet
    return jsonify({
        "message": "login ok",
        "user": {"id": row["id"], "name": row["name"], "email": row["email"]}
    })

@app.route("/me", methods=["GET"])
def me():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    db = get_db()
    row = db.execute(
        "SELECT id, name, email FROM users WHERE id = ?", (uid,)
    ).fetchone()

    return jsonify({"user": dict(row)})

@app.route("/logout", methods=["POST"])
def logout():
    session.clear()   # tüm session değerlerini sil
    return jsonify({"message": "logged out"})



if __name__ == "__main__":
    print("Loaded from:", __file__, flush=True)
    app.run(debug=True, port=5002, use_reloader=False)
