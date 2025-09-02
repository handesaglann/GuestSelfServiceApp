from flask import Flask
from database import init_db

app = Flask(__name__)

@app.route("/")               # ana sayfa 200
def home():
    return "Home OK", 200

@app.route("/health")         # sağlık kontrolü 200
def health():
    return "OK", 200

@app.route("/init-db")        # tabloyu kurar
def init_database():
    init_db()
    return "Database initialized!"

if __name__ == "__main__":
    print("Loaded from:", __file__)
    app.run(debug=True, port=5000, use_reloader=False)  # port=5000, reloader kapalı
