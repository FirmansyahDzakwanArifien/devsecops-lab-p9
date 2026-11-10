"""Aplikasi web sederhana untuk praktikum Container Security (P9)."""
import os
import secrets

from flask import Flask, jsonify

app = Flask(__name__)
# Secret diambil dari environment saat runtime, tidak pernah ditulis di image.
app.config["SECRET_KEY"] = os.environ.get("APP_SECRET") or secrets.token_hex(32)


@app.get("/")
def index():
    return "Hello, Secure World! DevSecOps P9 - Flask di container hardened.\n"


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Content-Security-Policy"] = "default-src 'none'"
    return resp


if __name__ == "__main__":
    # Hanya untuk development lokal. Di container aplikasi dijalankan lewat gunicorn.
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8080)))
