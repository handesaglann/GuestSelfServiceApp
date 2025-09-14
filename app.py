from flask import Flask, request, jsonify, session, render_template, redirect

from sqlite3 import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from database import is_admin


from database import (
    init_db, get_db, close_db,
    create_service, get_all_services,
    create_reservation, get_reservations_by_user, get_reservation_by_id,
    delete_reservation, update_reservation_status,
    create_complaint, get_complaints_by_user,
    get_complaint_by_id, update_complaint_status,
    create_invoice, get_invoices_by_user,
    update_invoice_status, import_invoices_from_csv,
    get_user_total_from_invoices
)

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-change-me"),
    SESSION_COOKIE_HTTPONLY=True,
)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# --- DB bağlantısını kapatma ---
@app.teardown_appcontext
def teardown_db(exception):
    close_db()


# --- Health & Home ---
@app.route("/")
def root():
    return redirect("/login")


@app.route("/home")
def home_page():
    return render_template("home.html")



@app.route("/health")
def health():
    return "OK", 200

@app.route("/init-db")
def init_database():
    init_db()
    return "Database initialized!"


# --- USERS ---
@app.route("/add-user/<name>/<email>")
def add_user(name, email):
    db = get_db()
    try:
        with db:
            db.execute(
                "INSERT INTO users (name, email) VALUES (?, ?)",
                (name, email)
            )
        return {"message": f"{name} eklendi"}, 201
    except IntegrityError:
        return {"error": "Bu email zaten kayıtlı"}, 409


@app.route("/list-users")
def list_users():
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    return {"users": [dict(u) for u in users]}


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    # POST (form veya JSON)
    data = request.form if request.form else request.get_json(silent=True) or {}
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
        session["user_id"] = user_id
        return jsonify({"id": user_id, "name": name, "email": email}), 201
    except IntegrityError:
        return jsonify({"error": "email already exists"}), 409


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.form if request.form else request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "email and password required"}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, name, email, password_hash, role FROM users WHERE email = ?",
        (email,)
    ).fetchone()

    if not row or not row["password_hash"] or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid credentials"}), 401

    session["user_id"] = row["id"]

    # Eğer form üzerinden geliyorsa → yönlendirme yap
    if request.form:
        if row["role"] == "admin":
            return redirect("/dashboard")   # admin → dashboard
        else:
            return redirect("/home")

    # JSON API kullanıyorsa JSON dön
    return jsonify({
        "message": "login ok",
        "user": {"id": row["id"], "name": row["name"], "email": row["email"], "role": row["role"]}
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


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    return render_template("logout.html")



# --- SERVICES ---
@app.route("/services", methods=["GET"])
def list_services():
    services = get_all_services(active_only=True)
    return jsonify(services), 200


@app.route("/services", methods=["POST"])
def add_service():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    price = data.get("price")

    if not name or price is None:
        return jsonify({"error": "name and price required"}), 400

    service_id = create_service(name, description, price)

    db = get_db()
    row = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()

    return jsonify({
        "message": "service created",
        "service": dict(row)
    }), 201



# --- RESERVATIONS ---
@app.route("/reservations", methods=["GET"])
def list_reservations():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    reservations = get_reservations_by_user(uid)
    return jsonify(reservations), 200


@app.route("/reservations", methods=["POST"])
def add_reservation():
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
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    complaints = get_complaints_by_user(uid)
    return jsonify(complaints), 200


@app.route("/complaints", methods=["POST"])
def add_complaint():
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


# --- INVOICES ---
@app.route("/invoices", methods=["GET", "POST"])
def invoices():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    if request.method == "GET":
        invoices = get_invoices_by_user(uid)
        return jsonify(invoices), 200

    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        total_amount = data.get("total_amount")
        issued_at = data.get("issued_at")

        if not total_amount or not issued_at:
            return jsonify({"error": "total_amount and issued_at required"}), 400

        invoice_id = create_invoice(
            user_id=uid,
            total_amount=total_amount,
            issued_at=issued_at,
            currency=data.get("currency", "TRY"),
            paid=data.get("paid", 0),
            source="manual"
        )
        return jsonify({"message": "invoice created", "id": invoice_id}), 201


@app.route("/invoices/<int:invoice_id>/status", methods=["PUT"])
def update_invoice(invoice_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    paid = int(data.get("paid", 0))

    update_invoice_status(invoice_id, paid)
    return jsonify({"message": "invoice updated", "id": invoice_id, "paid": paid}), 200


@app.route("/upload_invoices", methods=["POST"])
def upload_invoices():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    if "file" not in request.files:
        return jsonify({"error": "no file uploaded"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "empty filename"}), 400

    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(file_path)

    # CSV import işlemini database.py hallediyor
    import_invoices_from_csv(file_path, user_id=uid)

    return jsonify({"message": "invoices imported from CSV"}), 201

@app.route("/my-total")
def my_total():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    total = get_user_total_from_invoices(uid)
    return jsonify({"total_spent": total})

@app.route("/logout-test")
def logout_test_page():
    return render_template("logout.html")

@app.route("/services-page")
def services_page():
    return render_template("services.html")

@app.route("/reservations-page")
def reservations_page():
    return render_template("reservations.html")

@app.route("/complaints-page")
def complaints_page():
    return render_template("complaints.html")

@app.route("/invoices-page")
def invoices_page():
    return render_template("invoices.html")

"""@app.route("/my-total")
def my_total():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401

    total = get_user_total_spent(uid)
    return jsonify({"total_spent": total})"""


@app.route("/dashboard")
def dashboard():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401
    if not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    db = get_db()
    stats = {}
    stats["total_users"] = db.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
    stats["total_reservations"] = db.execute("SELECT COUNT(*) as c FROM reservations").fetchone()["c"]
    stats["total_income"] = db.execute("SELECT SUM(total_amount) as s FROM invoices").fetchone()["s"] or 0
    stats["open_complaints"] = db.execute("SELECT COUNT(*) as c FROM complaints WHERE status='open'").fetchone()["c"]

    # Kullanıcı listesi
    rows = db.execute("SELECT id, name, email FROM users ORDER BY name ASC").fetchall()
    users = [dict(r) for r in rows]

    return render_template("dashboard.html", stats=stats, users=users)



@app.route("/admin/users")
def admin_users():
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401
    if not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    db = get_db()
    rows = db.execute("SELECT id, name, email FROM users ORDER BY name ASC").fetchall()
    return render_template("admin_users.html", users=[dict(r) for r in rows])

@app.route("/admin/user/<int:user_id>")
def admin_user_detail(user_id):
    uid = session.get("user_id")
    if not uid:
        return jsonify({"error": "not authenticated"}), 401
    if not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    db = get_db()
    user = db.execute("SELECT id, name, email FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        return "User not found", 404

    reservations = db.execute("""
        SELECT r.id, s.name as service_name, r.start_time, r.end_time, r.status
        FROM reservations r
        JOIN services s ON r.service_id = s.id
        WHERE r.user_id=?
    """, (user_id,)).fetchall()

    invoices = db.execute("""
        SELECT id, total_amount, currency, issued_at, paid, source
        FROM invoices WHERE user_id=?
    """, (user_id,)).fetchall()

    complaints = db.execute("""
        SELECT id, title, text, status, created_at
        FROM complaints WHERE user_id=?
    """, (user_id,)).fetchall()

    return render_template("admin_user_detail.html",
                           user=dict(user),
                           reservations=[dict(r) for r in reservations],
                           invoices=[dict(i) for i in invoices],
                           complaints=[dict(c) for c in complaints])


# --- ADMIN: Complaints yönetimi ---
@app.route("/admin/complaints")
def admin_complaints():
    uid = session.get("user_id")
    if not uid or not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    db = get_db()
    rows = db.execute("""
        SELECT c.id, u.name as user_name, c.title, c.text, c.status, c.created_at
        FROM complaints c
        JOIN users u ON c.user_id = u.id
        ORDER BY c.created_at DESC
    """).fetchall()
    return render_template("admin_complaints.html", complaints=[dict(r) for r in rows])

@app.route("/admin/complaint/<int:cid>/status", methods=["POST"])
def admin_update_complaint(cid):
    uid = session.get("user_id")
    if not uid or not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    new_status = request.form.get("status") or request.json.get("status")
    if new_status not in ["open", "in_progress", "resolved"]:
        return jsonify({"error": "invalid status"}), 400

    db = get_db()
    db.execute("UPDATE complaints SET status=? WHERE id=?", (new_status, cid))
    db.commit()
    return redirect("/admin/complaints")

@app.route("/admin/reservation/<int:rid>/status", methods=["POST"])
def admin_update_reservation(rid):
    uid = session.get("user_id")
    if not uid or not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    new_status = request.form.get("status")
    if new_status not in ["pending", "approved", "cancelled"]:
        return jsonify({"error": "invalid status"}), 400

    db = get_db()
    db.execute("UPDATE reservations SET status=? WHERE id=?", (new_status, rid))
    db.commit()
    return redirect(request.referrer or "/dashboard")


@app.route("/admin/invoice/<int:invoice_id>/status", methods=["POST"])
def admin_update_invoice(invoice_id):
    uid = session.get("user_id")
    if not uid or not is_admin(uid):
        return jsonify({"error": "not authorized"}), 403

    paid = int(request.form.get("paid", 0))
    db = get_db()
    db.execute("UPDATE invoices SET paid=? WHERE id=?", (paid, invoice_id))
    db.commit()

    # geri ilgili user detail sayfasına dön
    return redirect(request.referrer or "/dashboard")





if __name__ == "__main__":
    print("Loaded from:", __file__, flush=True)
    app.run(debug=True, port=5002, use_reloader=False)
