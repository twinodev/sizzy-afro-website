import os
from datetime import datetime
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = "dance-with-sizzy-afro"

# PostgreSQL Configuration
database_url = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

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


# Database Models
class Submission(db.Model):
    __tablename__ = "submissions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text)
    created_at = db.Column(db.String(50), nullable=False)


class Event(db.Model):
    __tablename__ = "events"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    event_date = db.Column(db.String(50), nullable=False)
    location = db.Column(db.String(255))
    created_at = db.Column(db.String(50), nullable=False)


class Sponsor(db.Model):
    __tablename__ = "sponsors"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    logo_url = db.Column(db.Text)
    website = db.Column(db.String(255))
    tier = db.Column(db.String(50))
    created_at = db.Column(db.String(50), nullable=False)


class PartnershipPlan(db.Model):
    __tablename__ = "partnership_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.String(50))
    benefits = db.Column(db.Text)
    created_at = db.Column(db.String(50), nullable=False)


def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()


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

        submission = Submission(
            name=name,
            email=email,
            message=message,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(submission)
        db.session.commit()

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
    submissions = Submission.query.order_by(Submission.id.desc()).all()
    total_submissions = Submission.query.count()
    total_events = Event.query.count()
    total_sponsors = Sponsor.query.count()
    total_plans = PartnershipPlan.query.count()

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
    events_list = Event.query.order_by(Event.event_date.asc()).all()
    return render_template("events.html", events=events_list)


@app.route("/sponsors")
def sponsors():
    sponsors_list = Sponsor.query.order_by(Sponsor.tier.desc(), Sponsor.name.asc()).all()
    return render_template("sponsors.html", sponsors=sponsors_list)


@app.route("/partnerships")
def partnerships():
    plans = PartnershipPlan.query.order_by(PartnershipPlan.id.asc()).all()
    return render_template("partnerships.html", plans=plans)


# Admin Events Management
@app.route("/admin/events")
@admin_required
def admin_events():
    events_list = Event.query.order_by(Event.event_date.desc()).all()
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

        event = Event(
            title=title,
            description=description,
            event_date=event_date,
            location=location,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(event)
        db.session.commit()
        flash("Event created successfully.", "success")
        return redirect(url_for("admin_events"))

    return render_template("admin_events_form.html", event=None)


@app.route("/admin/events/edit/<int:event_id>", methods=["GET", "POST"])
@admin_required
def admin_events_edit(event_id):
    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        event_date = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()

        if not title or not event_date:
            flash("Title and event date are required.", "error")
            return redirect(url_for("admin_events_edit", event_id=event_id))

        event.title = title
        event.description = description
        event.event_date = event_date
        event.location = location
        db.session.commit()
        flash("Event updated successfully.", "success")
        return redirect(url_for("admin_events"))

    return render_template("admin_events_form.html", event=event)


@app.route("/admin/events/delete/<int:event_id>", methods=["POST"])
@admin_required
def admin_events_delete(event_id):
    event = Event.query.get_or_404(event_id)
    db.session.delete(event)
    db.session.commit()
    flash("Event deleted successfully.", "success")
    return redirect(url_for("admin_events"))


# Admin Sponsors Management
@app.route("/admin/sponsors")
@admin_required
def admin_sponsors():
    sponsors_list = Sponsor.query.order_by(Sponsor.tier.desc(), Sponsor.name.asc()).all()
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

        sponsor = Sponsor(
            name=name,
            logo_url=logo_url,
            website=website,
            tier=tier,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(sponsor)
        db.session.commit()
        flash("Sponsor created successfully.", "success")
        return redirect(url_for("admin_sponsors"))

    return render_template("admin_sponsors_form.html", sponsor=None)


@app.route("/admin/sponsors/edit/<int:sponsor_id>", methods=["GET", "POST"])
@admin_required
def admin_sponsors_edit(sponsor_id):
    sponsor = Sponsor.query.get_or_404(sponsor_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        logo_url = request.form.get("logo_url", "").strip()
        website = request.form.get("website", "").strip()
        tier = request.form.get("tier", "").strip()

        if not name:
            flash("Sponsor name is required.", "error")
            return redirect(url_for("admin_sponsors_edit", sponsor_id=sponsor_id))

        sponsor.name = name
        sponsor.logo_url = logo_url
        sponsor.website = website
        sponsor.tier = tier
        db.session.commit()
        flash("Sponsor updated successfully.", "success")
        return redirect(url_for("admin_sponsors"))

    return render_template("admin_sponsors_form.html", sponsor=sponsor)


@app.route("/admin/sponsors/delete/<int:sponsor_id>", methods=["POST"])
@admin_required
def admin_sponsors_delete(sponsor_id):
    sponsor = Sponsor.query.get_or_404(sponsor_id)
    db.session.delete(sponsor)
    db.session.commit()
    flash("Sponsor deleted successfully.", "success")
    return redirect(url_for("admin_sponsors"))


# Admin Partnership Plans Management
@app.route("/admin/partnerships")
@admin_required
def admin_partnerships():
    plans = PartnershipPlan.query.order_by(PartnershipPlan.id.asc()).all()
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

        plan = PartnershipPlan(
            name=name,
            description=description,
            price=price,
            benefits=benefits,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(plan)
        db.session.commit()
        flash("Partnership plan created successfully.", "success")
        return redirect(url_for("admin_partnerships"))

    return render_template("admin_partnerships_form.html", plan=None)


@app.route("/admin/partnerships/edit/<int:plan_id>", methods=["GET", "POST"])
@admin_required
def admin_partnerships_edit(plan_id):
    plan = PartnershipPlan.query.get_or_404(plan_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        benefits = request.form.get("benefits", "").strip()

        if not name:
            flash("Plan name is required.", "error")
            return redirect(url_for("admin_partnerships_edit", plan_id=plan_id))

        plan.name = name
        plan.description = description
        plan.price = price
        plan.benefits = benefits
        db.session.commit()
        flash("Partnership plan updated successfully.", "success")
        return redirect(url_for("admin_partnerships"))

    return render_template("admin_partnerships_form.html", plan=plan)


@app.route("/admin/partnerships/delete/<int:plan_id>", methods=["POST"])
@admin_required
def admin_partnerships_delete(plan_id):
    plan = PartnershipPlan.query.get_or_404(plan_id)
    db.session.delete(plan)
    db.session.commit()
    flash("Partnership plan deleted successfully.", "success")
    return redirect(url_for("admin_partnerships"))


# Initialize database on startup (safely for serverless)
try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"Database initialization error: {e}")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

