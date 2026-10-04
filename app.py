import os
from functools import wraps
import mysql.connector
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from db import get_db

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


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

        flash("Account created. Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            "SELECT user_id, name, password_hash FROM users WHERE email = %s",
            (email,),
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["user_id"] = user["user_id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))

        flash("Invalid email or password.")

    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", name=session["name"])

@app.route("/clients")
@login_required
def clients():
    conn = get_db()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT client_id, name, email, phone
        FROM clients
        WHERE user_id = %s
        ORDER BY name
    """, (session["user_id"],))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("clients.html", clients=rows)

@app.route("/clients/add", methods=["GET", "POST"])
@login_required
def add_client():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()

        if not name:
            flash("Client name is required.")
            return render_template("client_form.html", client=None)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO clients (user_id, name, email, phone) VALUES (%s, %s, %s, %s)",
            (session["user_id"], name, email or None, phone or None),
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Client added.")
        return redirect(url_for("clients"))

    return render_template("client_form.html", client=None)


@app.route("/clients/<int:client_id>/edit", methods=["GET", "POST"])
@login_required
def edit_client(client_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT client_id, name, email, phone FROM clients "
        "WHERE client_id = %s AND user_id = %s",
        (client_id, session["user_id"]),
    )
    client = cur.fetchone()

    if client is None:
        cur.close()
        conn.close()
        abort(404)

    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip()
        phone = request.form["phone"].strip()

        if not name:
            cur.close()
            conn.close()
            flash("Client name is required.")
            return render_template("client_form.html", client=client)

        cur.execute(
            "UPDATE clients SET name = %s, email = %s, phone = %s "
            "WHERE client_id = %s AND user_id = %s",
            (name, email or None, phone or None, client_id, session["user_id"]),
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Client updated.")
        return redirect(url_for("clients"))

    cur.close()
    conn.close()
    return render_template("client_form.html", client=client)


@app.route("/clients/<int:client_id>/delete", methods=["POST"])
@login_required
def delete_client(client_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM clients WHERE client_id = %s AND user_id = %s",
        (client_id, session["user_id"]),
    )
    conn.commit()
    cur.close()
    conn.close()
    flash("Client deleted.")
    return redirect(url_for("clients"))
if __name__ == "__main__":
    app.run(debug=True, port=5001)
