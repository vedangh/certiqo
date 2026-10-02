import os
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv
from db import get_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


@app.route("/")
def home():
    return "CertiQo is running"


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        if not name or not email or len(password) < 8:
            flash("Fill in all fields. Password must be at least 8 characters.")
            return render_template("register.html")

        conn = get_db()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (%s, %s, %s)",
                (name, email, generate_password_hash(password)),
            )
            conn.commit()
        except mysql.connector.IntegrityError:
            flash("That email is already registered.")
            return render_template("register.html")
        finally:
            cur.close()
            conn.close()

        flash("Account created. Login page comes next.")
        return redirect(url_for("register"))

    return render_template("register.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)
