import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.config["SECRET_KEY"] = "dance-with-sizzy-afro"
app.config["DATABASE"] = "submissions.db"

# Email configuration
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", 587))
app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "True") == "True"
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME"))
app.config["ADMIN_EMAIL"] = os.getenv("ADMIN_EMAIL", "sizzyafro@gmail.com")
app.config["MAIL_SUPPRESS_SEND"] = True  # Disable actual sending during development

# Initialize mail lazily
mail = None

def get_mail():
    """Get mail instance, initializing if needed"""
    global mail
    if mail is None:
        from flask_mail import Mail
        mail = Mail(app)
    return mail


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            message TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            event_date TEXT NOT NULL,
            location TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS sponsors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            logo_url TEXT,
            website TEXT,
            tier TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS partnership_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price TEXT,
            benefits TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    db.commit()


@app.teardown_appcontext
def close_db(_exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access the admin panel.", "error")
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapped


def send_notification_email(subject, body):
    """Send email notification to admin"""
    try:
        if app.config["MAIL_USERNAME"] and app.config["ADMIN_EMAIL"]:
            from flask_mail import Message
            msg = Message(
                subject=subject,
                recipients=[app.config["ADMIN_EMAIL"]],
                body=body
            )
            mail_instance = get_mail()
            mail_instance.send(msg)
            return True
    except Exception as e:
        print(f"Email notification failed: {e}")
    return False


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/community")
def community():
    return render_template("community.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email:
            flash("Please enter your name and email to join the community.", "error")
            return redirect(url_for("contact"))

        db = get_db()
        db.execute(
            "INSERT INTO submissions (name, email, message, created_at) VALUES (?, ?, ?, ?)",
            (name, email, message, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()

        # Send email notification
        email_body = f"""
New Contact Form Submission - Dance with Sizzy Afro

Name: {name}
Email: {email}
Message: {message or 'No message provided'}

Submitted at: {datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")} UTC

Reply to: {email}
        """
        send_notification_email(
            subject=f"New Contact: {name}",
            body=email_body
        )

        flash("Welcome to the Dance with Sizzy Afro community! We will reach out soon.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD", "changeme123")

        if username == admin_username and password == admin_password:
            session["admin_logged_in"] = True
            flash("Welcome to the admin panel.", "success")
            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "error")

    return render_template("admin_login.html")


@app.route("/admin/logout")
@admin_required
def admin_logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    db = get_db()
    submissions = db.execute(
        "SELECT id, name, email, message, created_at FROM submissions ORDER BY id DESC"
    ).fetchall()
    total_submissions = db.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
    total_events = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    total_sponsors = db.execute("SELECT COUNT(*) FROM sponsors").fetchone()[0]
    total_plans = db.execute("SELECT COUNT(*) FROM partnership_plans").fetchone()[0]

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        total_submissions=total_submissions,
        total_events=total_events,
        total_sponsors=total_sponsors,
        total_plans=total_plans,
    )


# Public routes
@app.route("/events")
def events():
    db = get_db()
    events_list = db.execute(
        "SELECT id, title, description, event_date, location FROM events ORDER BY event_date ASC"
    ).fetchall()
    return render_template("events.html", events=events_list)


@app.route("/sponsors")
def sponsors():
    db = get_db()
    sponsors_list = db.execute(
        "SELECT id, name, logo_url, website, tier FROM sponsors ORDER BY tier DESC, name ASC"
    ).fetchall()
    return render_template("sponsors.html", sponsors=sponsors_list)


@app.route("/partnerships")
def partnerships():
    db = get_db()
    plans = db.execute(
        "SELECT id, name, description, price, benefits FROM partnership_plans ORDER BY id ASC"
    ).fetchall()
    return render_template("partnerships.html", plans=plans)


# Admin Events Management
@app.route("/admin/events")
@admin_required
def admin_events():
    db = get_db()
    events_list = db.execute(
        "SELECT id, title, event_date, location, created_at FROM events ORDER BY event_date DESC"
    ).fetchall()
    return render_template("admin_events.html", events=events_list)


@app.route("/admin/events/create", methods=["GET", "POST"])
@admin_required
def admin_events_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()

        if not title or not event_date:
            flash("Title and event date are required.", "error")
            return redirect(url_for("admin_events_create"))

        db = get_db()
        db.execute(
            "INSERT INTO events (title, description, event_date, location, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, description, event_date, location, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        flash("Event created successfully.", "success")
        return redirect(url_for("admin_events"))

    return render_template("admin_events_form.html", event=None)


@app.route("/admin/events/edit/<int:event_id>", methods=["GET", "POST"])
@admin_required
def admin_events_edit(event_id):
    db = get_db()
    event = db.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("admin_events"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()

        if not title or not event_date:
            flash("Title and event date are required.", "error")
            return redirect(url_for("admin_events_edit", event_id=event_id))

        db.execute(
            "UPDATE events SET title = ?, description = ?, event_date = ?, location = ? WHERE id = ?",
            (title, description, event_date, location, event_id),
        )
        db.commit()
        flash("Event updated successfully.", "success")
        return redirect(url_for("admin_events"))

    return render_template("admin_events_form.html", event=event)


@app.route("/admin/events/delete/<int:event_id>", methods=["POST"])
@admin_required
def admin_events_delete(event_id):
    db = get_db()
    db.execute("DELETE FROM events WHERE id = ?", (event_id,))
    db.commit()
    flash("Event deleted successfully.", "success")
    return redirect(url_for("admin_events"))


# Admin Sponsors Management
@app.route("/admin/sponsors")
@admin_required
def admin_sponsors():
    db = get_db()
    sponsors_list = db.execute(
        "SELECT id, name, tier, website, created_at FROM sponsors ORDER BY tier DESC, name ASC"
    ).fetchall()
    return render_template("admin_sponsors.html", sponsors=sponsors_list)


@app.route("/admin/sponsors/create", methods=["GET", "POST"])
@admin_required
def admin_sponsors_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        logo_url = request.form.get("logo_url", "").strip()
        website = request.form.get("website", "").strip()
        tier = request.form.get("tier", "").strip()

        if not name:
            flash("Sponsor name is required.", "error")
            return redirect(url_for("admin_sponsors_create"))

        db = get_db()
        db.execute(
            "INSERT INTO sponsors (name, logo_url, website, tier, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, logo_url, website, tier, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        flash("Sponsor created successfully.", "success")
        return redirect(url_for("admin_sponsors"))

    return render_template("admin_sponsors_form.html", sponsor=None)


@app.route("/admin/sponsors/edit/<int:sponsor_id>", methods=["GET", "POST"])
@admin_required
def admin_sponsors_edit(sponsor_id):
    db = get_db()
    sponsor = db.execute("SELECT * FROM sponsors WHERE id = ?", (sponsor_id,)).fetchone()

    if not sponsor:
        flash("Sponsor not found.", "error")
        return redirect(url_for("admin_sponsors"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        logo_url = request.form.get("logo_url", "").strip()
        website = request.form.get("website", "").strip()
        tier = request.form.get("tier", "").strip()

        if not name:
            flash("Sponsor name is required.", "error")
            return redirect(url_for("admin_sponsors_edit", sponsor_id=sponsor_id))

        db.execute(
            "UPDATE sponsors SET name = ?, logo_url = ?, website = ?, tier = ? WHERE id = ?",
            (name, logo_url, website, tier, sponsor_id),
        )
        db.commit()
        flash("Sponsor updated successfully.", "success")
        return redirect(url_for("admin_sponsors"))

    return render_template("admin_sponsors_form.html", sponsor=sponsor)


@app.route("/admin/sponsors/delete/<int:sponsor_id>", methods=["POST"])
@admin_required
def admin_sponsors_delete(sponsor_id):
    db = get_db()
    db.execute("DELETE FROM sponsors WHERE id = ?", (sponsor_id,))
    db.commit()
    flash("Sponsor deleted successfully.", "success")
    return redirect(url_for("admin_sponsors"))


# Admin Partnership Plans Management
@app.route("/admin/partnerships")
@admin_required
def admin_partnerships():
    db = get_db()
    plans = db.execute(
        "SELECT id, name, price, created_at FROM partnership_plans ORDER BY id ASC"
    ).fetchall()
    return render_template("admin_partnerships.html", plans=plans)


@app.route("/admin/partnerships/create", methods=["GET", "POST"])
@admin_required
def admin_partnerships_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        benefits = request.form.get("benefits", "").strip()

        if not name:
            flash("Plan name is required.", "error")
            return redirect(url_for("admin_partnerships_create"))

        db = get_db()
        db.execute(
            "INSERT INTO partnership_plans (name, description, price, benefits, created_at) VALUES (?, ?, ?, ?, ?)",
            (name, description, price, benefits, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")),
        )
        db.commit()
        flash("Partnership plan created successfully.", "success")
        return redirect(url_for("admin_partnerships"))

    return render_template("admin_partnerships_form.html", plan=None)


@app.route("/admin/partnerships/edit/<int:plan_id>", methods=["GET", "POST"])
@admin_required
def admin_partnerships_edit(plan_id):
    db = get_db()
    plan = db.execute("SELECT * FROM partnership_plans WHERE id = ?", (plan_id,)).fetchone()

    if not plan:
        flash("Partnership plan not found.", "error")
        return redirect(url_for("admin_partnerships"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        benefits = request.form.get("benefits", "").strip()

        if not name:
            flash("Plan name is required.", "error")
            return redirect(url_for("admin_partnerships_edit", plan_id=plan_id))

        db.execute(
            "UPDATE partnership_plans SET name = ?, description = ?, price = ?, benefits = ? WHERE id = ?",
            (name, description, price, benefits, plan_id),
        )
        db.commit()
        flash("Partnership plan updated successfully.", "success")
        return redirect(url_for("admin_partnerships"))

    return render_template("admin_partnerships_form.html", plan=plan)


@app.route("/admin/partnerships/delete/<int:plan_id>", methods=["POST"])
@admin_required
def admin_partnerships_delete(plan_id):
    db = get_db()
    db.execute("DELETE FROM partnership_plans WHERE id = ?", (plan_id,))
    db.commit()
    flash("Partnership plan deleted successfully.", "success")
    return redirect(url_for("admin_partnerships"))


# Initialize database on first request
@app.before_request
def before_request():
    """Initialize database if not already done"""
    if not hasattr(app, '_db_initialized'):
        try:
            with app.app_context():
                init_db()
            app._db_initialized = True
        except Exception as e:
            print(f"Database initialization error: {e}")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
