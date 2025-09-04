from flask import Flask
from database import init_db, get_db, close_db, create_service, get_all_services
from sqlite3 import IntegrityError
import os
from flask import request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from database import (
    create_reservation, get_reservations_by_user, get_reservation_by_id,
    delete_reservation, update_reservation_status
)
from database import (
    create_complaint, get_complaints_by_user,
    get_complaint_by_id, update_complaint_status
)





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

@app.route("/services", methods=["GET"])
def list_services():
    """Tüm aktif servisleri listele"""
    services = get_all_services(active_only=True)
    return jsonify(services), 200


@app.route("/services", methods=["POST"])
def add_service():
    """Yeni bir servis ekle"""
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    price = data.get("price")

    # Zorunlu alan kontrolü
    if not name or price is None:
        return jsonify({"error": "name and price required"}), 400

    # DB’ye kaydet
    service_id = create_service(name, description, price)

    # Eklenen servisi geri als
    db = get_db()
    row = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()

    return jsonify({
        "message": "service created",
        "service": dict(row)
    }), 201

# --- RESERVATIONS ---

@app.route("/reservations", methods=["GET"])
def list_reservations():
    """Giriş yapan kullanıcının rezervasyonlarını getir"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    reservations = get_reservations_by_user(uid)
    return jsonify(reservations), 200


@app.route("/reservations", methods=["POST"])
def add_reservation():
    """Yeni rezervasyon oluştur"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    service_id = data.get("service_id")
    start_time = data.get("start_time")
    end_time = data.get("end_time")
    note = data.get("note")

    if not service_id or not start_time:
        return jsonify({"error": "service_id and start_time required"}), 400

    res_id = create_reservation(uid, service_id, start_time, end_time, note)
    return jsonify({"message": "reservation created", "id": res_id}), 201


@app.route("/reservations/<int:res_id>", methods=["DELETE"])
def remove_reservation(res_id):
    """Kullanıcının kendi rezervasyonunu silmesi"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    res = get_reservation_by_id(res_id)
    if not res:
        return jsonify({"error": "reservation not found"}), 404
    if res["user_id"] != uid:
        return jsonify({"error": "not authorized"}), 403

    delete_reservation(res_id)
    return jsonify({"message": "reservation deleted"}), 200

# --- COMPLAINTS ---

@app.route("/complaints", methods=["GET"])
def list_complaints():
    """Giriş yapan kullanıcının şikayetlerini getir"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    complaints = get_complaints_by_user(uid)
    return jsonify(complaints), 200


@app.route("/complaints", methods=["POST"])
def add_complaint():
    """Yeni şikayet oluştur"""
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    text = data.get("text", "").strip()

    if not title or not text:
        return jsonify({"error": "title and text required"}), 400

    comp_id = create_complaint(uid, title, text)
    return jsonify({"message": "complaint created", "id": comp_id}), 201




if __name__ == "__main__":
    print("Loaded from:", __file__, flush=True)
    app.run(debug=True, port=5002, use_reloader=False)



