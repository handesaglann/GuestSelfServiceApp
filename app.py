from flask import Flask

# Flask uygulamasını başlat
app = Flask(__name__)

# Ana sayfa ("/") rotası
@app.route("/")
def home():
    return "Hello, Guest Self-Service App!"

# Uygulamayı çalıştır
if __name__ == "__main__":
    app.run(debug=True)
