import os
import re
import mimetypes
import uuid
from datetime import datetime
from functools import wraps
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

app = Flask(__name__)
app.config["SECRET_KEY"] = "dance-with-sizzy-afro"


def _clean_database_url(raw_value):
    if not raw_value:
        return ""

    value = raw_value.strip().strip('"').strip("'")

    # Keep only the first URL token if extra text was pasted into the env value.
    match = re.search(r"postgres(?:ql)?://[^\s'\"]+", value)
    if match:
        value = match.group(0)

    # Handle accidental copy/paste like: DATABASE_URL=postgresql://...
    for prefix in ("DATABASE_URL=", "POSTGRES_URL=", "POSTGRES_URL_NON_POOLING="):
        if value.upper().startswith(prefix):
            value = value.split("=", 1)[1].strip().strip('"').strip("'")
            break

    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql://", 1)

    if value.startswith("postgresql://") and "+" not in value.split("://", 1)[0]:
        value = value.replace("postgresql://", "postgresql+psycopg://", 1)

    parsed = urlparse(value)
    if parsed.scheme.startswith("postgresql") and parsed.query:
        allowed_keys = {
            "sslmode",
            "connect_timeout",
            "application_name",
            "target_session_attrs",
            "options",
            "keepalives",
            "keepalives_idle",
            "keepalives_interval",
            "keepalives_count",
            "channel_binding",
            "gssencmode",
            "sslrootcert",
            "sslcert",
            "sslkey",
            "passfile",
        }
        filtered_query = urlencode(
            [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k in allowed_keys],
            doseq=True,
        )
        value = urlunparse(parsed._replace(query=filtered_query))

    return value


# PostgreSQL Configuration
# Check for both DATABASE_URL (standard) and POSTGRES_URL (Supabase)
database_url = _clean_database_url(
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or os.getenv("POSTGRES_URL_NON_POOLING")
    or "postgresql://user:password@localhost/dbname"
)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 3600,
}

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
app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
app.config["SUPABASE_FLYER_BUCKET"] = os.getenv("SUPABASE_FLYER_BUCKET", "event-flyers")
app.config["SUPABASE_LOGO_BUCKET"] = os.getenv("SUPABASE_LOGO_BUCKET", "sponsor-logos")

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
    flyer_url = db.Column(db.Text, nullable=False)
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


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text)
    image_url = db.Column(db.Text)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)
    updated_at = db.Column(db.String(50), nullable=False)


def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        _ensure_event_flyer_column()


def _ensure_event_flyer_column():
    """Add flyer_url to existing events tables if needed."""
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("events")}

    if "flyer_url" not in columns:
        db.session.execute(text("ALTER TABLE events ADD COLUMN flyer_url TEXT"))
        db.session.commit()


def _allowed_image_filename(filename):
    allowed_extensions = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    _, extension = os.path.splitext(filename.lower())
    return extension in allowed_extensions


def _upload_image_to_supabase(file_storage, bucket_name, object_prefix, error_label):
    """Upload an image to Supabase Storage and return its public URL."""
    if not file_storage or not file_storage.filename:
        raise ValueError(f"Please choose a {error_label} image to upload.")

    if not app.config["SUPABASE_URL"] or not app.config["SUPABASE_SERVICE_ROLE_KEY"]:
        raise ValueError("Supabase storage is not configured.")

    if not _allowed_image_filename(file_storage.filename):
        raise ValueError(f"{error_label.capitalize()} image must be a JPG, PNG, WEBP, or GIF file.")

    original_extension = os.path.splitext(file_storage.filename)[1].lower()
    mime_type = file_storage.mimetype or mimetypes.guess_type(file_storage.filename)[0] or "application/octet-stream"
    if not mime_type.startswith("image/"):
        raise ValueError(f"{error_label.capitalize()} image must be an image file.")

    object_name = f"{object_prefix}/{uuid.uuid4().hex}{original_extension or '.jpg'}"
    upload_url = (
        f"{app.config['SUPABASE_URL'].rstrip('/')}"
        f"/storage/v1/object/{bucket_name}/{quote(object_name, safe='/')}"
    )

    payload = file_storage.read()
    request_obj = Request(
        upload_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {app.config['SUPABASE_SERVICE_ROLE_KEY']}",
            "apikey": app.config["SUPABASE_SERVICE_ROLE_KEY"],
            "Content-Type": mime_type,
            "x-upsert": "true",
        },
    )

    try:
        with urlopen(request_obj, timeout=30) as response:
            response.read()
    except HTTPError as error:
        raise ValueError(f"{error_label.capitalize()} upload failed with status {error.code}.") from error
    except URLError as error:
        raise ValueError(f"{error_label.capitalize()} upload failed. Please try again.") from error

    return (
        f"{app.config['SUPABASE_URL'].rstrip('/')}"
        f"/storage/v1/object/public/{bucket_name}/{quote(object_name, safe='/')}"
    )


def _upload_flyer_to_supabase(file_storage):
    return _upload_image_to_supabase(file_storage, app.config["SUPABASE_FLYER_BUCKET"], "events", "flyer")


def _upload_logo_to_supabase(file_storage):
    return _upload_image_to_supabase(file_storage, app.config["SUPABASE_LOGO_BUCKET"], "sponsors", "logo")


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
    total_posts = Post.query.count()
    total_sponsors = Sponsor.query.count()
    total_plans = PartnershipPlan.query.count()

    return render_template(
        "admin_dashboard.html",
        submissions=submissions,
        total_submissions=total_submissions,
        total_events=total_events,
        total_posts=total_posts,
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


@app.route("/posts")
def posts():
    posts_list = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).all()
    return render_template("posts.html", posts=posts_list)


@app.route("/posts/<int:post_id>")
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    if not post.published:
        flash("This post is not published.", "error")
        return redirect(url_for("posts"))
    
    related_posts = Post.query.filter(Post.published == True, Post.id != post_id).order_by(Post.created_at.desc()).limit(3).all()
    return render_template("post_detail.html", post=post, related_posts=related_posts)


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
        flyer_file = request.files.get("flyer_file")

        if not title or not event_date or not flyer_file or not flyer_file.filename:
            flash("Title, flyer image, and event date are required.", "error")
            return redirect(url_for("admin_events_create"))

        try:
            flyer_url = _upload_flyer_to_supabase(flyer_file)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin_events_create"))

        event = Event(
            title=title,
            description=description,
            flyer_url=flyer_url,
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
        flyer_file = request.files.get("flyer_file")

        if not title or not event_date:
            flash("Title and event date are required.", "error")
            return redirect(url_for("admin_events_edit", event_id=event_id))

        flyer_url = event.flyer_url
        if flyer_file and flyer_file.filename:
            try:
                flyer_url = _upload_flyer_to_supabase(flyer_file)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_events_edit", event_id=event_id))

        event.title = title
        event.description = description
        event.flyer_url = flyer_url
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
        website = request.form.get("website", "").strip()
        tier = request.form.get("tier", "").strip()
        logo_file = request.files.get("logo_file")

        if not name or not logo_file or not logo_file.filename:
            flash("Sponsor name and logo image are required.", "error")
            return redirect(url_for("admin_sponsors_create"))

        try:
            logo_url = _upload_logo_to_supabase(logo_file)
        except ValueError as error:
            flash(str(error), "error")
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
        website = request.form.get("website", "").strip()
        tier = request.form.get("tier", "").strip()
        logo_file = request.files.get("logo_file")

        if not name:
            flash("Sponsor name is required.", "error")
            return redirect(url_for("admin_sponsors_edit", sponsor_id=sponsor_id))

        logo_url = sponsor.logo_url
        if logo_file and logo_file.filename:
            try:
                logo_url = _upload_logo_to_supabase(logo_file)
            except ValueError as error:
                flash(str(error), "error")
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


# Admin Posts Management
@app.route("/admin/posts")
@admin_required
def admin_posts():
    posts_list = Post.query.order_by(Post.created_at.desc()).all()
    return render_template("admin_posts.html", posts=posts_list)


@app.route("/admin/posts/create", methods=["GET", "POST"])
@admin_required
def admin_posts_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        image_url = request.form.get("image_url", "").strip()
        published = request.form.get("published") == "on"

        if not title or not content:
            flash("Please enter a title and content for the post.", "error")
            return redirect(url_for("admin_posts_create"))

        post = Post(
            title=title,
            content=content,
            excerpt=excerpt or None,
            image_url=image_url or None,
            published=published,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            updated_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(post)
        db.session.commit()

        flash("Post created successfully.", "success")
        return redirect(url_for("admin_posts"))

    return render_template("admin_posts_form.html", post=None)


@app.route("/admin/posts/edit/<int:post_id>", methods=["GET", "POST"])
@admin_required
def admin_posts_edit(post_id):
    post = Post.query.get_or_404(post_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        excerpt = request.form.get("excerpt", "").strip()
        image_url = request.form.get("image_url", "").strip()
        published = request.form.get("published") == "on"

        if not title or not content:
            flash("Please enter a title and content for the post.", "error")
            return redirect(url_for("admin_posts_edit", post_id=post_id))

        post.title = title
        post.content = content
        post.excerpt = excerpt or None
        post.image_url = image_url or None
        post.published = published
        post.updated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        db.session.commit()

        flash("Post updated successfully.", "success")
        return redirect(url_for("admin_posts"))

    return render_template("admin_posts_form.html", post=post)


@app.route("/admin/posts/delete/<int:post_id>", methods=["POST"])
@admin_required
def admin_posts_delete(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash("Post deleted successfully.", "success")
    return redirect(url_for("admin_posts"))


# Initialize database on startup (safely for serverless)
try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"Database initialization error: {e}")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

