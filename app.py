import os
from functools import wraps
import mysql.connector
from datetime import date, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from db import get_db
from ai import draft_text, AIUnavailable

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
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT t.task_id, t.title, t.due_date, t.priority,
               c.client_id, c.name AS client_name
        FROM tasks t
        JOIN clients c ON c.client_id = t.client_id
        WHERE c.user_id = %s AND t.status = 'pending'
        ORDER BY t.due_date, FIELD(t.priority, 'high', 'medium', 'low')
        """,
        (session["user_id"],),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    today = date.today()
    week_end = today + timedelta(days=7)
    overdue, this_week, later = [], [], []

    for r in rows:
        r["days"] = (r["due_date"] - today).days
        if r["due_date"] < today:
            overdue.append(r)
        elif r["due_date"] <= week_end:
            this_week.append(r)
        else:
            later.append(r)

    return render_template(
        "dashboard.html",
        name=session["name"],
        overdue=overdue,
        this_week=this_week,
        later=later,
    )

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
def get_owned_client(client_id):
    """Return the client only if it belongs to the logged-in CA, else 404."""
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        "SELECT client_id, name FROM clients WHERE client_id = %s AND user_id = %s",
        (client_id, session["user_id"]),
    )
    client = cur.fetchone()
    cur.close()
    conn.close()
    if client is None:
        abort(404)
    return client


@app.route("/clients/<int:client_id>/tasks")
@login_required
def tasks(client_id):
    client = get_owned_client(client_id)

    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT task_id, title, due_date, status, priority, notes
        FROM tasks
        WHERE client_id = %s
        ORDER BY status = 'done', due_date
        """,
        (client_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return render_template("tasks.html", client=client, tasks=rows, today=date.today())


@app.route("/clients/<int:client_id>/tasks/add", methods=["GET", "POST"])
@login_required
def add_task(client_id):
    client = get_owned_client(client_id)

    if request.method == "POST":
        title = request.form["title"].strip()
        due_date = request.form["due_date"]
        priority = request.form["priority"]
        notes = request.form["notes"].strip()

        if not title or not due_date or priority not in ("low", "medium", "high"):
            flash("Title, due date and a valid priority are required.")
            return render_template("task_form.html", client=client)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tasks (client_id, title, due_date, priority, notes) "
            "VALUES (%s, %s, %s, %s, %s)",
            (client_id, title, due_date, priority, notes or None),
        )
        conn.commit()
        cur.close()
        conn.close()
        flash("Task added.")
        return redirect(url_for("tasks", client_id=client_id))

    return render_template("task_form.html", client=client)


@app.route("/clients/<int:client_id>/tasks/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle_task(client_id, task_id):
    get_owned_client(client_id)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tasks SET status = IF(status = 'done', 'pending', 'done') "
        "WHERE task_id = %s AND client_id = %s",
        (task_id, client_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for("tasks", client_id=client_id))


@app.route("/clients/<int:client_id>/tasks/<int:task_id>/delete", methods=["POST"])
@login_required
def delete_task(client_id, task_id):
    get_owned_client(client_id)

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM tasks WHERE task_id = %s AND client_id = %s",
        (task_id, client_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    flash("Task deleted.")
    return redirect(url_for("tasks", client_id=client_id))
@app.route("/clients/<int:client_id>/tasks/<int:task_id>/reminder", methods=["POST"])
@login_required
def draft_reminder(client_id, task_id):
    conn = get_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT t.task_id, t.title, t.due_date,
               c.client_id, c.name AS client_name, c.email AS client_email
        FROM tasks t
        JOIN clients c ON c.client_id = t.client_id
        WHERE t.task_id = %s AND c.client_id = %s AND c.user_id = %s
        """,
        (task_id, client_id, session["user_id"]),
    )
    task = cur.fetchone()
    cur.close()
    conn.close()
    if task is None:
        abort(404)

    due = task["due_date"].strftime("%d %B %Y")
    ca_name = session["name"]

    prompt = (
        "Write a short, polite, professional email body from a Chartered Accountant "
        f"named {ca_name} to a client named {task['client_name']}. "
        f"Reminder: the task '{task['title']}' is due on {due}. "
        "Ask the client to share any documents needed in good time. "
        "Rules: under 80 words. Plain text, no subject line. "
        "Use only the details given. Do not invent amounts, penalties, "
        f"section numbers or legal claims. Sign off with the name {ca_name}."
    )

    try:
        text = draft_text(prompt)
        used_ai = True
    except AIUnavailable:
        text = (
            f"Dear {task['client_name']},\n\n"
            f"This is a reminder that '{task['title']}' is due on {due}. "
            "Please share the required documents at your earliest convenience.\n\n"
            f"Regards,\n{ca_name}"
        )
        used_ai = False

    return render_template("reminder.html", task=task, text=text, used_ai=used_ai)
if __name__ == "__main__":
    app.run(debug=True, port=5001)
