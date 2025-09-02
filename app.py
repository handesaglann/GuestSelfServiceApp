from flask import Flask
from database import init_db, get_db, close_db
from sqlite3 import IntegrityError

app = Flask(__name__)

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

if __name__ == "__main__":
    print("Loaded from:", __file__, flush=True)
    app.run(debug=True, port=5002, use_reloader=False)
