import os, sqlite3
from flask import g

# DB yolu ve klasör
DB_PATH = os.path.join(os.path.dirname(__file__), "instance", "app.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)  # instance/ yoksa oluştur

def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn

def get_db():
    if "db" not in g:
        g.db = _connect()
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      email TEXT UNIQUE,
      password_hash TEXT,
      room_no TEXT,
      phone TEXT
    );

    CREATE TABLE IF NOT EXISTS services (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      description TEXT,
      price REAL NOT NULL DEFAULT 0,
      is_active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS reservations (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      service_id INTEGER NOT NULL,
      start_time TEXT NOT NULL,
      end_time TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      note TEXT,
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
      FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT
    );

    CREATE TABLE IF NOT EXISTS complaints (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      title TEXT NOT NULL,
      text TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'open',
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS invoices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      total_amount REAL NOT NULL,
      currency TEXT NOT NULL DEFAULT 'TRY',
      issued_at TEXT NOT NULL,
      paid INTEGER NOT NULL DEFAULT 0,
      source TEXT NOT NULL DEFAULT 'system',
      FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)
    db.commit()

# --- SERVICES CRUD ---
def create_service(name, description, price, is_active=1):
    db = get_db()
    cur = db.execute(
        "INSERT INTO services (name, description, price, is_active) VALUES (?, ?, ?, ?)",
        (name, description, price, is_active),
    )
    db.commit()
    return cur.lastrowid

def get_all_services(active_only=True):
    db = get_db()
    if active_only:
        rows = db.execute("SELECT * FROM services WHERE is_active=1").fetchall()
    else:
        rows = db.execute("SELECT * FROM services").fetchall()
    return [dict(r) for r in rows]

def get_service_by_id(service_id):
    db = get_db()
    row = db.execute("SELECT * FROM services WHERE id=?", (service_id,)).fetchone()
    return dict(row) if row else None

def update_service(service_id, name=None, description=None, price=None, is_active=None):
    db = get_db()
    fields, values = [], []
    if name is not None:
        fields.append("name=?")
        values.append(name)
    if description is not None:
        fields.append("description=?")
        values.append(description)
    if price is not None:
        fields.append("price=?")
        values.append(price)
    if is_active is not None:
        fields.append("is_active=?")
        values.append(is_active)
    if not fields:
        return False
    values.append(service_id)
    db.execute(f"UPDATE services SET {', '.join(fields)} WHERE id=?", values)
    db.commit()
    return True

def delete_service(service_id):
    db = get_db()
    db.execute("DELETE FROM services WHERE id=?", (service_id,))
    db.commit()
    return True

# --- RESERVATIONS CRUD ---
def create_reservation(user_id, service_id, start_time, end_time=None, note=None):
    db = get_db()
    cur = db.execute(
        """INSERT INTO reservations (user_id, service_id, start_time, end_time, note)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, service_id, start_time, end_time, note),
    )
    db.commit()
    return cur.lastrowid

def get_reservations_by_user(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT r.id, r.start_time, r.end_time, r.status, r.note,
                  s.name as service_name, s.price
           FROM reservations r
           JOIN services s ON r.service_id = s.id
           WHERE r.user_id = ?
           ORDER BY r.created_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def get_reservation_by_id(res_id):
    db = get_db()
    row = db.execute("SELECT * FROM reservations WHERE id=?", (res_id,)).fetchone()
    return dict(row) if row else None

def update_reservation_status(res_id, status):
    db = get_db()
    db.execute("UPDATE reservations SET status=? WHERE id=?", (status, res_id))
    db.commit()
    return True

def delete_reservation(res_id):
    db = get_db()
    db.execute("DELETE FROM reservations WHERE id=?", (res_id,))
    db.commit()
    return True

# --- COMPLAINTS CRUD ---
def create_complaint(user_id, title, text):
    db = get_db()
    cur = db.execute(
        "INSERT INTO complaints (user_id, title, text) VALUES (?, ?, ?)",
        (user_id, title, text)
    )
    db.commit()
    return cur.lastrowid

def get_complaints_by_user(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT id, title, text, status, created_at
           FROM complaints
           WHERE user_id = ?
           ORDER BY created_at DESC""",
        (user_id,)
    ).fetchall()
    return [dict(r) for r in rows]

def get_complaint_by_id(complaint_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM complaints WHERE id = ?",
        (complaint_id,)
    ).fetchone()
    return dict(row) if row else None

def update_complaint_status(complaint_id, status):
    db = get_db()
    db.execute(
        "UPDATE complaints SET status = ? WHERE id = ?",
        (status, complaint_id)
    )
    db.commit()
    return True

# --- INVOICES CRUD ---
def create_invoice(user_id, total_amount, issued_at, currency="TRY", paid=0, source="system"):
    db = get_db()
    cur = db.execute(
        """INSERT INTO invoices (user_id, total_amount, currency, issued_at, paid, source)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, total_amount, currency, issued_at, paid, source),
    )
    db.commit()
    return cur.lastrowid

def get_invoices_by_user(user_id):
    db = get_db()
    rows = db.execute(
        """SELECT id, total_amount, currency, issued_at, paid, source
           FROM invoices
           WHERE user_id = ?
           ORDER BY issued_at DESC""",
        (user_id,),
    ).fetchall()
    return [dict(r) for r in rows]

def update_invoice_status(invoice_id, paid):
    db = get_db()
    db.execute("UPDATE invoices SET paid = ? WHERE id = ?", (paid, invoice_id))
    db.commit()
    return True

def import_invoices_from_csv(file_path, user_id=None):
    import csv
    db = get_db()
    with open(file_path, newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            db.execute(
                """INSERT INTO invoices (user_id, total_amount, currency, issued_at, paid, source)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    user_id,  # her zaman login olan user_id kullanılacak
                    float(row.get("total_amount", 0)),
                    row.get("currency", "TRY"),
                    row.get("issued_at"),
                    int(row.get("paid", 0)),
                    "csv"
                ),
            )
    db.commit()
    return True


