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
app.config["MAIL_SUPPRESS_SEND"] = os.getenv("MAIL_SUPPRESS_SEND", "False").lower() in ("1", "true", "yes")
app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
app.config["SUPABASE_FLYER_BUCKET"] = os.getenv("SUPABASE_FLYER_BUCKET", "event-flyers")
app.config["SUPABASE_LOGO_BUCKET"] = os.getenv("SUPABASE_LOGO_BUCKET", "sponsor-logos")
app.config["SUPABASE_POST_BUCKET"] = os.getenv("SUPABASE_POST_BUCKET", "post-images")

# Google Analytics configuration
app.config["GA_TRACKING_ID"] = os.getenv("GA_TRACKING_ID")

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
    verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255))
    verified_at = db.Column(db.String(50))
    notification_sent = db.Column(db.Boolean, default=False)
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


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    approved = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)


class Gallery(db.Model):
    __tablename__ = "gallery"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50), nullable=False)


class Video(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    youtube_id = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50), nullable=False)


class Testimonial(db.Model):
    __tablename__ = "testimonials"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(255))
    content = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, default=5)
    image_url = db.Column(db.Text)
    featured = db.Column(db.Boolean, default=False)
    approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50), nullable=False)


class FAQ(db.Model):
    __tablename__ = "faqs"
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(500), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(100))
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.String(50), nullable=False)


class NewsletterSubscriber(db.Model):
    __tablename__ = "newsletter_subscribers"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, unique=True)
    verified = db.Column(db.Boolean, default=False)
    verification_token = db.Column(db.String(255))
    subscribed = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)


class EventNotification(db.Model):
    __tablename__ = "event_notifications"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'))
    created_at = db.Column(db.String(50), nullable=False)


class ClassSchedule(db.Model):
    __tablename__ = "class_schedules"
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(10), nullable=False)
    end_time = db.Column(db.String(10), nullable=False)
    class_name = db.Column(db.String(255), nullable=False)
    location = db.Column(db.String(255))
    level = db.Column(db.String(50))
    capacity = db.Column(db.Integer)
    description = db.Column(db.Text)
    created_at = db.Column(db.String(50), nullable=False)


class MerchandiseProduct(db.Model):
    __tablename__ = "merchandise"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.String(20), nullable=False)
    image_url = db.Column(db.Text)
    category = db.Column(db.String(100))
    available = db.Column(db.Boolean, default=True)
    featured = db.Column(db.Boolean, default=False)
    purchase_url = db.Column(db.String(500))
    created_at = db.Column(db.String(50), nullable=False)


class SocialLinks(db.Model):
    __tablename__ = "social_links"
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False, unique=True)
    url = db.Column(db.String(500), nullable=False)
    display_name = db.Column(db.String(100))
    icon = db.Column(db.String(100))
    created_at = db.Column(db.String(50), nullable=False)


class PostTag(db.Model):
    __tablename__ = "post_tags"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    tag = db.Column(db.String(100), nullable=False)


class PostCategory(db.Model):
    __tablename__ = "post_categories"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    category = db.Column(db.String(100), nullable=False)


def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        _ensure_event_flyer_column()
        _ensure_submission_verification_columns()


def _ensure_event_flyer_column():
    """Add flyer_url to existing events tables if needed."""
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("events")}

    if "flyer_url" not in columns:
        db.session.execute(text("ALTER TABLE events ADD COLUMN flyer_url TEXT"))
        db.session.commit()


def _ensure_submission_verification_columns():
    """Add contact verification columns to existing submissions tables if needed."""
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("submissions")}

    column_statements = [
        ("verified", "BOOLEAN DEFAULT FALSE"),
        ("verification_token", "TEXT"),
        ("verified_at", "TEXT"),
        ("notification_sent", "BOOLEAN DEFAULT FALSE"),
    ]

    added_column = False
    for column_name, column_sql in column_statements:
        if column_name not in columns:
            db.session.execute(text(f"ALTER TABLE submissions ADD COLUMN {column_name} {column_sql}"))
            added_column = True

    if added_column:
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


def _upload_post_image_to_supabase(file_storage):
    return _upload_image_to_supabase(file_storage, app.config["SUPABASE_POST_BUCKET"], "posts", "post image")


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Please log in to access the admin panel.", "error")
            return redirect(url_for("admin_login"))
        return view_func(*args, **kwargs)

    return wrapped


def send_email_message(subject, body, recipients, return_error=False):
    """Send a plain text email to one or more recipients.
    
    Args:
        subject: Email subject line
        body: Email body text
        recipients: List of email addresses or single email string
        return_error: If True, return (success, error_message) tuple; if False, return boolean
    
    Returns:
        If return_error=False: True if sent successfully, False otherwise
        If return_error=True: (success_bool, error_message_str) tuple
    """
    try:
        if app.config["MAIL_SUPPRESS_SEND"]:
            error_msg = "Mail send skipped because MAIL_SUPPRESS_SEND is enabled. Set MAIL_SUPPRESS_SEND=False in environment variables."
            app.logger.warning(error_msg)
            if return_error:
                return False, error_msg
            return False

        # Validate required settings
        required_settings = {
            "MAIL_SERVER": app.config.get("MAIL_SERVER"),
            "MAIL_USERNAME": app.config.get("MAIL_USERNAME"),
            "MAIL_PASSWORD": app.config.get("MAIL_PASSWORD"),
        }
        
        missing = [k for k, v in required_settings.items() if not v]
        if missing or not recipients:
            error_msg = f"Mail send failed: Missing SMTP settings: {', '.join(missing)}" if missing else "Mail send failed: No recipients provided."
            app.logger.error(error_msg)
            if return_error:
                return False, error_msg
            return False

        from flask_mail import Message
        msg = Message(
            subject=subject,
            recipients=recipients if isinstance(recipients, list) else [recipients],
            body=body
        )
        mail_instance = get_mail()
        app.logger.info(f"Attempting to send email to {recipients} via {app.config.get('MAIL_SERVER')}:{app.config.get('MAIL_PORT')}")
        mail_instance.send(msg)
        success_msg = f"Email sent successfully to {recipients}"
        app.logger.info(success_msg)
        if return_error:
            return True, success_msg
        return True
    except Exception as e:
        error_msg = f"Email send failed: {str(e)}"
        app.logger.exception("Email notification failed: %s", e)
        if return_error:
            return False, error_msg
    return False if not return_error else (False, "Unknown email error")


def send_notification_email(subject, body):
    """Send email notification to admin"""
    return send_email_message(subject, body, [app.config["ADMIN_EMAIL"]])


# Context processors - inject data into all templates
@app.context_processor
def inject_analytics():
    """Inject Google Analytics tracking ID into all templates"""
    return {
        "ga_tracking_id": app.config.get("GA_TRACKING_ID")
    }


@app.route("/")
def home():
    # Show latest published posts on home page
    recent_posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).limit(3).all()
    return render_template("index.html", recent_posts=recent_posts)


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
            verified=False,
            verification_token=str(uuid.uuid4()),
            notification_sent=False,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(submission)
        db.session.commit()

        verify_url = url_for("contact_verify", token=submission.verification_token, _external=True)
        email_body = f"""
Please verify your contact request for Dance with Sizzy Afro.

Hi {name},

We received your message and need you to confirm this email address before we forward it to the team.

Verify here: {verify_url}

If you did not submit this request, you can ignore this email.
        """

        if not send_email_message(
            subject="Verify your Dance with Sizzy Afro contact request",
            body=email_body,
            recipients=[email]
        ):
            db.session.delete(submission)
            db.session.commit()
            flash("We could not send the verification email right now. Please try again.", "error")
            return redirect(url_for("contact"))

        flash("Check your email to verify your contact request before we notify the team.", "success")
        return redirect(url_for("contact"))

    return render_template("contact.html")


@app.route("/contact/verify/<token>")
def contact_verify(token):
    submission = Submission.query.filter_by(verification_token=token).first()
    if not submission:
        flash("Invalid or expired verification link.", "error")
        return redirect(url_for("contact"))

    if submission.verified:
        flash("Your contact request was already verified.", "info")
        return redirect(url_for("contact"))

    submission.verified = True
    submission.verified_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    submission.verification_token = None
    db.session.commit()

    if not submission.notification_sent:
        admin_body = f"""
New Verified Contact Form Submission - Dance with Sizzy Afro

Name: {submission.name}
Email: {submission.email}
Message: {submission.message or 'No message provided'}

Verified at: {submission.verified_at} UTC
Submitted at: {submission.created_at} UTC

Reply to: {submission.email}
        """
        if send_notification_email(
            subject=f"New Verified Contact: {submission.name}",
            body=admin_body
        ):
            submission.notification_sent = True
            db.session.commit()

    flash("Your email is verified. We have forwarded your message to the team.", "success")
    return redirect(url_for("contact"))


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


@app.route("/admin/send-test-email", methods=["POST"])
@admin_required
def send_test_email():
    """Send a test email to the admin email address to verify SMTP configuration."""
    from flask import jsonify
    
    success, message = send_email_message(
        subject="Test Email from Dance with Sizzy Afro",
        body="This is a test email to verify your SMTP configuration is working correctly.",
        recipients=[app.config["ADMIN_EMAIL"]],
        return_error=True
    )
    
    if success:
        return jsonify({"success": True, "message": message}), 200
    else:
        return jsonify({"success": False, "message": message}), 500


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


@app.route("/posts/<int:post_id>", methods=["GET", "POST"])
def post_detail(post_id):
    post = Post.query.get_or_404(post_id)
    if not post.published:
        flash("This post is not published.", "error")
        return redirect(url_for("posts"))

    if request.method == "POST":
        # Accept comments on posts
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()

        if not name or not email or not message:
            flash("Please provide your name, email, and a comment.", "error")
            return redirect(url_for("post_detail", post_id=post_id))

        comment = Comment(
            post_id=post.id,
            name=name,
            email=email,
            message=message,
            approved=True,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(comment)
        db.session.commit()
        flash("Thanks — your comment was posted.", "success")
        return redirect(url_for("post_detail", post_id=post_id))

    related_posts = Post.query.filter(Post.published == True, Post.id != post_id).order_by(Post.created_at.desc()).limit(3).all()
    comments = Comment.query.filter_by(post_id=post.id, approved=True).order_by(Comment.id.asc()).all()
    tags = PostTag.query.filter_by(post_id=post_id).all()
    categories = PostCategory.query.filter_by(post_id=post_id).all()
    return render_template("post_detail.html", post=post, related_posts=related_posts, comments=comments, tags=tags, categories=categories)


# Gallery Routes
@app.route("/gallery")
def gallery():
    category = request.args.get("category")
    page = request.args.get("page", 1, type=int)
    
    query = Gallery.query.order_by(Gallery.created_at.desc())
    if category:
        query = query.filter_by(category=category)
    
    gallery_items = query.paginate(page=page, per_page=12)
    categories = db.session.query(Gallery.category).distinct().all()
    featured = Gallery.query.filter_by(featured=True).limit(3).all()
    
    return render_template("gallery.html", gallery=gallery_items, categories=categories, featured=featured, current_category=category)


# Video Routes
@app.route("/videos")
def videos():
    category = request.args.get("category")
    page = request.args.get("page", 1, type=int)
    
    query = Video.query.order_by(Video.created_at.desc())
    if category:
        query = query.filter_by(category=category)
    
    videos_list = query.paginate(page=page, per_page=12)
    categories = db.session.query(Video.category).distinct().all()
    featured = Video.query.filter_by(featured=True).limit(3).all()
    
    return render_template("videos.html", videos=videos_list, categories=categories, featured=featured, current_category=category)


# Testimonials Routes
@app.route("/testimonials")
def testimonials():
    testimonials_list = Testimonial.query.filter_by(approved=True).order_by(Testimonial.featured.desc(), Testimonial.created_at.desc()).all()
    featured = Testimonial.query.filter_by(featured=True, approved=True).all()
    return render_template("testimonials.html", testimonials=testimonials_list, featured=featured)


@app.route("/testimonials/submit", methods=["GET", "POST"])
def submit_testimonial():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip()
        content = request.form.get("content", "").strip()
        rating = request.form.get("rating", 5, type=int)

        if not name or not content:
            flash("Please provide your name and testimonial.", "error")
            return redirect(url_for("submit_testimonial"))

        testimonial = Testimonial(
            name=name,
            role=role or None,
            content=content,
            rating=min(5, max(1, rating)),
            approved=False,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(testimonial)
        db.session.commit()
        
        # Send notification email
        send_notification_email(
            subject=f"New Testimonial from {name}",
            body=f"A new testimonial has been submitted:\n\n{content}\n\nReview in admin panel."
        )
        
        flash("Thank you for your testimonial! It will appear after approval.", "success")
        return redirect(url_for("testimonials"))

    return render_template("testimonial_form.html")


# FAQ Routes
@app.route("/faq")
def faq():
    categories = db.session.query(FAQ.category).distinct().all()
    current_category = request.args.get("category")
    
    query = FAQ.query.order_by(FAQ.order.asc(), FAQ.id.asc())
    if current_category:
        query = query.filter_by(category=current_category)
    
    faqs = query.all()
    return render_template("faq.html", faqs=faqs, categories=categories, current_category=current_category)


# Newsletter Routes
@app.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    email = request.form.get("email", "").strip()
    
    if not email:
        flash("Please enter your email.", "error")
        return redirect(request.referrer or url_for("home"))
    
    existing = NewsletterSubscriber.query.filter_by(email=email).first()
    if existing:
        flash("You're already subscribed.", "info")
        return redirect(request.referrer or url_for("home"))
    
    verification_token = str(uuid.uuid4())
    subscriber = NewsletterSubscriber(
        email=email,
        verification_token=verification_token,
        verified=False,
        subscribed=True,
        created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    )
    db.session.add(subscriber)
    db.session.commit()
    
    # Send verification email
    verify_url = url_for("newsletter_verify", token=verification_token, _external=True)
    send_notification_email(
        subject="Verify Your Newsletter Subscription",
        body=f"Click the link to verify: {verify_url}"
    )
    
    flash("Check your email to verify your subscription.", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/newsletter/verify/<token>")
def newsletter_verify(token):
    subscriber = NewsletterSubscriber.query.filter_by(verification_token=token).first()
    if not subscriber:
        flash("Invalid verification link.", "error")
        return redirect(url_for("home"))
    
    subscriber.verified = True
    subscriber.verification_token = None
    db.session.commit()
    
    flash("Your email has been verified! Thank you for subscribing.", "success")
    return redirect(url_for("home"))


# Class Schedule Routes
@app.route("/classes")
def classes():
    schedules = ClassSchedule.query.order_by(
        ClassSchedule.day_of_week.asc(),
        ClassSchedule.start_time.asc()
    ).all()
    
    # Order days properly
    day_order = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
    schedules = sorted(schedules, key=lambda x: (day_order.get(x.day_of_week, 7), x.start_time))
    
    return render_template("classes.html", schedules=schedules)


# Merchandise Routes
@app.route("/merchandise")
def merchandise():
    category = request.args.get("category")
    page = request.args.get("page", 1, type=int)
    
    query = MerchandiseProduct.query.filter_by(available=True).order_by(MerchandiseProduct.created_at.desc())
    if category:
        query = query.filter_by(category=category)
    
    products = query.paginate(page=page, per_page=12)
    categories = db.session.query(MerchandiseProduct.category).filter(MerchandiseProduct.available == True).distinct().all()
    featured = MerchandiseProduct.query.filter_by(featured=True, available=True).limit(4).all()
    
    return render_template("merchandise.html", products=products, categories=categories, featured=featured, current_category=category)


# Event Calendar Route
@app.route("/calendar")
def event_calendar():
    events_list = Event.query.order_by(Event.event_date.asc()).all()
    return render_template("event_calendar.html", events=events_list)


# Search Routes
@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return render_template("search.html", results=[], query=query)
    
    # Search across posts, events, and gallery
    posts_results = Post.query.filter(
        Post.published == True,
        (Post.title.ilike(f"%{query}%") | Post.content.ilike(f"%{query}%"))
    ).all()
    
    events_results = Event.query.filter(
        Event.title.ilike(f"%{query}%") | Event.description.ilike(f"%{query}%")
    ).all()
    
    gallery_results = Gallery.query.filter(
        Gallery.title.ilike(f"%{query}%") | Gallery.description.ilike(f"%{query}%")
    ).all()
    
    results = {
        "posts": posts_results,
        "events": events_results,
        "gallery": gallery_results
    }
    
    return render_template("search.html", results=results, query=query)


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
        image_file = request.files.get("image_file")
        published = request.form.get("published") == "on"

        if not title or not content:
            flash("Please enter a title and content for the post.", "error")
            return redirect(url_for("admin_posts_create"))

        # Prefer uploaded file over manual URL when provided
        if image_file and image_file.filename:
            try:
                image_url = _upload_post_image_to_supabase(image_file)
            except ValueError as error:
                flash(str(error), "error")
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
        image_file = request.files.get("image_file")
        published = request.form.get("published") == "on"

        if not title or not content:
            flash("Please enter a title and content for the post.", "error")
            return redirect(url_for("admin_posts_edit", post_id=post_id))

        # If a file was uploaded, attempt to upload and override the image URL
        if image_file and image_file.filename:
            try:
                image_url = _upload_post_image_to_supabase(image_file)
            except ValueError as error:
                flash(str(error), "error")
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


# Admin Submissions Management
@app.route("/admin/submissions")
@admin_required
def admin_submissions():
    submissions = Submission.query.order_by(Submission.id.desc()).all()
    return render_template("admin_submissions.html", submissions=submissions)


@app.route("/admin/submissions/delete/<int:submission_id>", methods=["POST"])
@admin_required
def admin_submissions_delete(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    db.session.delete(submission)
    db.session.commit()
    flash("Submission deleted successfully.", "success")
    return redirect(url_for("admin_submissions"))


# Admin Comments Management
@app.route("/admin/comments")
@admin_required
def admin_comments():
    comments = Comment.query.order_by(Comment.id.desc()).all()
    return render_template("admin_comments.html", comments=comments)


@app.route("/admin/comments/approve/<int:comment_id>", methods=["POST"])
@admin_required
def admin_comments_approve(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.approved = True
    db.session.commit()
    flash("Comment approved.", "success")
    return redirect(url_for("admin_comments"))


@app.route("/admin/comments/reject/<int:comment_id>", methods=["POST"])
@admin_required
def admin_comments_reject(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash("Comment rejected.", "success")
    return redirect(url_for("admin_comments"))


# Admin Gallery Management
@app.route("/admin/gallery")
@admin_required
def admin_gallery():
    gallery_items = Gallery.query.order_by(Gallery.created_at.desc()).all()
    return render_template("admin_gallery.html", gallery=gallery_items)


@app.route("/admin/gallery/create", methods=["GET", "POST"])
@admin_required
def admin_gallery_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        featured = request.form.get("featured") == "on"
        image_file = request.files.get("image_file")

        if not title or not image_file or not image_file.filename:
            flash("Title and image are required.", "error")
            return redirect(url_for("admin_gallery_create"))

        try:
            image_url = _upload_image_to_supabase(image_file, app.config["SUPABASE_POST_BUCKET"], "gallery", "gallery image")
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin_gallery_create"))

        gallery = Gallery(
            title=title,
            description=description,
            image_url=image_url,
            category=category or None,
            featured=featured,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(gallery)
        db.session.commit()
        flash("Gallery item created successfully.", "success")
        return redirect(url_for("admin_gallery"))

    return render_template("admin_gallery_form.html", item=None)


@app.route("/admin/gallery/edit/<int:item_id>", methods=["GET", "POST"])
@admin_required
def admin_gallery_edit(item_id):
    item = Gallery.query.get_or_404(item_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        featured = request.form.get("featured") == "on"
        image_file = request.files.get("image_file")

        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("admin_gallery_edit", item_id=item_id))

        if image_file and image_file.filename:
            try:
                item.image_url = _upload_image_to_supabase(image_file, app.config["SUPABASE_POST_BUCKET"], "gallery", "gallery image")
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_gallery_edit", item_id=item_id))

        item.title = title
        item.description = description
        item.category = category or None
        item.featured = featured
        db.session.commit()
        flash("Gallery item updated successfully.", "success")
        return redirect(url_for("admin_gallery"))

    return render_template("admin_gallery_form.html", item=item)


@app.route("/admin/gallery/delete/<int:item_id>", methods=["POST"])
@admin_required
def admin_gallery_delete(item_id):
    item = Gallery.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Gallery item deleted successfully.", "success")
    return redirect(url_for("admin_gallery"))


# Admin Video Management
@app.route("/admin/videos")
@admin_required
def admin_videos():
    videos_list = Video.query.order_by(Video.created_at.desc()).all()
    return render_template("admin_videos.html", videos=videos_list)


@app.route("/admin/videos/create", methods=["GET", "POST"])
@admin_required
def admin_videos_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        youtube_id = request.form.get("youtube_id", "").strip()
        category = request.form.get("category", "").strip()
        featured = request.form.get("featured") == "on"

        if not title or not youtube_id:
            flash("Title and YouTube ID are required.", "error")
            return redirect(url_for("admin_videos_create"))

        video = Video(
            title=title,
            description=description,
            youtube_id=youtube_id,
            category=category or None,
            featured=featured,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(video)
        db.session.commit()
        flash("Video created successfully.", "success")
        return redirect(url_for("admin_videos"))

    return render_template("admin_videos_form.html", video=None)


@app.route("/admin/videos/edit/<int:video_id>", methods=["GET", "POST"])
@admin_required
def admin_videos_edit(video_id):
    video = Video.query.get_or_404(video_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        youtube_id = request.form.get("youtube_id", "").strip()
        category = request.form.get("category", "").strip()
        featured = request.form.get("featured") == "on"

        if not title or not youtube_id:
            flash("Title and YouTube ID are required.", "error")
            return redirect(url_for("admin_videos_edit", video_id=video_id))

        video.title = title
        video.description = description
        video.youtube_id = youtube_id
        video.category = category or None
        video.featured = featured
        db.session.commit()
        flash("Video updated successfully.", "success")
        return redirect(url_for("admin_videos"))

    return render_template("admin_videos_form.html", video=video)


@app.route("/admin/videos/delete/<int:video_id>", methods=["POST"])
@admin_required
def admin_videos_delete(video_id):
    video = Video.query.get_or_404(video_id)
    db.session.delete(video)
    db.session.commit()
    flash("Video deleted successfully.", "success")
    return redirect(url_for("admin_videos"))


# Admin Testimonials Management
@app.route("/admin/testimonials")
@admin_required
def admin_testimonials():
    testimonials = Testimonial.query.order_by(Testimonial.created_at.desc()).all()
    return render_template("admin_testimonials.html", testimonials=testimonials)


@app.route("/admin/testimonials/approve/<int:testimonial_id>", methods=["POST"])
@admin_required
def admin_testimonials_approve(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    testimonial.approved = True
    db.session.commit()
    flash("Testimonial approved.", "success")
    return redirect(url_for("admin_testimonials"))


@app.route("/admin/testimonials/reject/<int:testimonial_id>", methods=["POST"])
@admin_required
def admin_testimonials_reject(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    db.session.delete(testimonial)
    db.session.commit()
    flash("Testimonial rejected.", "success")
    return redirect(url_for("admin_testimonials"))


@app.route("/admin/testimonials/feature/<int:testimonial_id>", methods=["POST"])
@admin_required
def admin_testimonials_feature(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    testimonial.featured = not testimonial.featured
    db.session.commit()
    flash("Testimonial updated.", "success")
    return redirect(url_for("admin_testimonials"))


# Admin FAQ Management
@app.route("/admin/faqs")
@admin_required
def admin_faqs():
    faqs = FAQ.query.order_by(FAQ.order.asc(), FAQ.id.asc()).all()
    return render_template("admin_faqs.html", faqs=faqs)


@app.route("/admin/faqs/create", methods=["GET", "POST"])
@admin_required
def admin_faqs_create():
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip()
        category = request.form.get("category", "").strip()
        order = request.form.get("order", 0, type=int)

        if not question or not answer:
            flash("Question and answer are required.", "error")
            return redirect(url_for("admin_faqs_create"))

        faq = FAQ(
            question=question,
            answer=answer,
            category=category or None,
            order=order,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(faq)
        db.session.commit()
        flash("FAQ created successfully.", "success")
        return redirect(url_for("admin_faqs"))

    return render_template("admin_faqs_form.html", faq=None)


@app.route("/admin/faqs/edit/<int:faq_id>", methods=["GET", "POST"])
@admin_required
def admin_faqs_edit(faq_id):
    faq = FAQ.query.get_or_404(faq_id)

    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip()
        category = request.form.get("category", "").strip()
        order = request.form.get("order", 0, type=int)

        if not question or not answer:
            flash("Question and answer are required.", "error")
            return redirect(url_for("admin_faqs_edit", faq_id=faq_id))

        faq.question = question
        faq.answer = answer
        faq.category = category or None
        faq.order = order
        db.session.commit()
        flash("FAQ updated successfully.", "success")
        return redirect(url_for("admin_faqs"))

    return render_template("admin_faqs_form.html", faq=faq)


@app.route("/admin/faqs/delete/<int:faq_id>", methods=["POST"])
@admin_required
def admin_faqs_delete(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    db.session.delete(faq)
    db.session.commit()
    flash("FAQ deleted successfully.", "success")
    return redirect(url_for("admin_faqs"))


# Admin Newsletter Management
@app.route("/admin/newsletter")
@admin_required
def admin_newsletter():
    subscribers = NewsletterSubscriber.query.order_by(NewsletterSubscriber.created_at.desc()).all()
    stats = {
        "total": NewsletterSubscriber.query.count(),
        "verified": NewsletterSubscriber.query.filter_by(verified=True).count(),
        "unverified": NewsletterSubscriber.query.filter_by(verified=False).count()
    }
    return render_template("admin_newsletter.html", subscribers=subscribers, stats=stats)


@app.route("/admin/newsletter/delete/<int:subscriber_id>", methods=["POST"])
@admin_required
def admin_newsletter_delete(subscriber_id):
    subscriber = NewsletterSubscriber.query.get_or_404(subscriber_id)
    db.session.delete(subscriber)
    db.session.commit()
    flash("Subscriber removed.", "success")
    return redirect(url_for("admin_newsletter"))


# Admin Class Schedule Management
@app.route("/admin/classes")
@admin_required
def admin_classes():
    schedules = ClassSchedule.query.order_by(ClassSchedule.day_of_week.asc(), ClassSchedule.start_time.asc()).all()
    return render_template("admin_classes.html", schedules=schedules)


@app.route("/admin/classes/create", methods=["GET", "POST"])
@admin_required
def admin_classes_create():
    if request.method == "POST":
        day = request.form.get("day_of_week", "").strip()
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        class_name = request.form.get("class_name", "").strip()
        location = request.form.get("location", "").strip()
        level = request.form.get("level", "").strip()
        capacity = request.form.get("capacity", 0, type=int)
        description = request.form.get("description", "").strip()

        if not day or not start_time or not end_time or not class_name:
            flash("Day, times, and class name are required.", "error")
            return redirect(url_for("admin_classes_create"))

        schedule = ClassSchedule(
            day_of_week=day,
            start_time=start_time,
            end_time=end_time,
            class_name=class_name,
            location=location or None,
            level=level or None,
            capacity=capacity or None,
            description=description or None,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(schedule)
        db.session.commit()
        flash("Class schedule created successfully.", "success")
        return redirect(url_for("admin_classes"))

    return render_template("admin_classes_form.html", schedule=None)


@app.route("/admin/classes/edit/<int:schedule_id>", methods=["GET", "POST"])
@admin_required
def admin_classes_edit(schedule_id):
    schedule = ClassSchedule.query.get_or_404(schedule_id)

    if request.method == "POST":
        day = request.form.get("day_of_week", "").strip()
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        class_name = request.form.get("class_name", "").strip()
        location = request.form.get("location", "").strip()
        level = request.form.get("level", "").strip()
        capacity = request.form.get("capacity", 0, type=int)
        description = request.form.get("description", "").strip()

        if not day or not start_time or not end_time or not class_name:
            flash("Day, times, and class name are required.", "error")
            return redirect(url_for("admin_classes_edit", schedule_id=schedule_id))

        schedule.day_of_week = day
        schedule.start_time = start_time
        schedule.end_time = end_time
        schedule.class_name = class_name
        schedule.location = location or None
        schedule.level = level or None
        schedule.capacity = capacity or None
        schedule.description = description or None
        db.session.commit()
        flash("Class schedule updated successfully.", "success")
        return redirect(url_for("admin_classes"))

    return render_template("admin_classes_form.html", schedule=schedule)


@app.route("/admin/classes/delete/<int:schedule_id>", methods=["POST"])
@admin_required
def admin_classes_delete(schedule_id):
    schedule = ClassSchedule.query.get_or_404(schedule_id)
    db.session.delete(schedule)
    db.session.commit()
    flash("Class schedule deleted successfully.", "success")
    return redirect(url_for("admin_classes"))


# Admin Merchandise Management
@app.route("/admin/merchandise")
@admin_required
def admin_merchandise():
    products = MerchandiseProduct.query.order_by(MerchandiseProduct.created_at.desc()).all()
    return render_template("admin_merchandise.html", products=products)


@app.route("/admin/merchandise/create", methods=["GET", "POST"])
@admin_required
def admin_merchandise_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()
        purchase_url = request.form.get("purchase_url", "").strip()
        available = request.form.get("available") == "on"
        featured = request.form.get("featured") == "on"
        image_file = request.files.get("image_file")

        if not name or not price:
            flash("Name and price are required.", "error")
            return redirect(url_for("admin_merchandise_create"))

        image_url = ""
        if image_file and image_file.filename:
            try:
                image_url = _upload_image_to_supabase(image_file, app.config["SUPABASE_POST_BUCKET"], "merchandise", "merchandise image")
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_merchandise_create"))

        product = MerchandiseProduct(
            name=name,
            description=description or None,
            price=price,
            image_url=image_url or None,
            category=category or None,
            available=available,
            featured=featured,
            purchase_url=purchase_url or None,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(product)
        db.session.commit()
        flash("Product created successfully.", "success")
        return redirect(url_for("admin_merchandise"))

    return render_template("admin_merchandise_form.html", product=None)


@app.route("/admin/merchandise/edit/<int:product_id>", methods=["GET", "POST"])
@admin_required
def admin_merchandise_edit(product_id):
    product = MerchandiseProduct.query.get_or_404(product_id)

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        category = request.form.get("category", "").strip()
        purchase_url = request.form.get("purchase_url", "").strip()
        available = request.form.get("available") == "on"
        featured = request.form.get("featured") == "on"
        image_file = request.files.get("image_file")

        if not name or not price:
            flash("Name and price are required.", "error")
            return redirect(url_for("admin_merchandise_edit", product_id=product_id))

        if image_file and image_file.filename:
            try:
                product.image_url = _upload_image_to_supabase(image_file, app.config["SUPABASE_POST_BUCKET"], "merchandise", "merchandise image")
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_merchandise_edit", product_id=product_id))

        product.name = name
        product.description = description or None
        product.price = price
        product.category = category or None
        product.available = available
        product.featured = featured
        product.purchase_url = purchase_url or None
        db.session.commit()
        flash("Product updated successfully.", "success")
        return redirect(url_for("admin_merchandise"))

    return render_template("admin_merchandise_form.html", product=product)


@app.route("/admin/merchandise/delete/<int:product_id>", methods=["POST"])
@admin_required
def admin_merchandise_delete(product_id):
    product = MerchandiseProduct.query.get_or_404(product_id)
    db.session.delete(product)
    db.session.commit()
    flash("Product deleted successfully.", "success")
    return redirect(url_for("admin_merchandise"))


# Admin Social Links Management
@app.route("/admin/social-links")
@admin_required
def admin_social_links():
    links = SocialLinks.query.order_by(SocialLinks.platform.asc()).all()
    return render_template("admin_social_links.html", links=links)


@app.route("/admin/social-links/create", methods=["GET", "POST"])
@admin_required
def admin_social_links_create():
    if request.method == "POST":
        platform = request.form.get("platform", "").strip()
        url = request.form.get("url", "").strip()
        display_name = request.form.get("display_name", "").strip()
        icon = request.form.get("icon", "").strip()

        if not platform or not url:
            flash("Platform and URL are required.", "error")
            return redirect(url_for("admin_social_links_create"))

        existing = SocialLinks.query.filter_by(platform=platform).first()
        if existing:
            flash("This platform already exists.", "error")
            return redirect(url_for("admin_social_links_create"))

        link = SocialLinks(
            platform=platform,
            url=url,
            display_name=display_name or None,
            icon=icon or None,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(link)
        db.session.commit()
        flash("Social link created successfully.", "success")
        return redirect(url_for("admin_social_links"))

    return render_template("admin_social_links_form.html", link=None)


@app.route("/admin/social-links/edit/<int:link_id>", methods=["GET", "POST"])
@admin_required
def admin_social_links_edit(link_id):
    link = SocialLinks.query.get_or_404(link_id)

    if request.method == "POST":
        url = request.form.get("url", "").strip()
        display_name = request.form.get("display_name", "").strip()
        icon = request.form.get("icon", "").strip()

        if not url:
            flash("URL is required.", "error")
            return redirect(url_for("admin_social_links_edit", link_id=link_id))

        link.url = url
        link.display_name = display_name or None
        link.icon = icon or None
        db.session.commit()
        flash("Social link updated successfully.", "success")
        return redirect(url_for("admin_social_links"))

    return render_template("admin_social_links_form.html", link=link)


@app.route("/admin/social-links/delete/<int:link_id>", methods=["POST"])
@admin_required
def admin_social_links_delete(link_id):
    link = SocialLinks.query.get_or_404(link_id)
    db.session.delete(link)
    db.session.commit()
    flash("Social link deleted successfully.", "success")
    return redirect(url_for("admin_social_links"))


# SEO Routes
@app.route("/robots.txt")
def robots():
    """Generate robots.txt for search engines"""
    return """User-agent: *
Allow: /
Disallow: /admin
Disallow: /admin/

Sitemap: https://sizzyafro.me/sitemap.xml

User-agent: Googlebot
Allow: /

User-agent: Bingbot
Allow: /
""", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/sitemap.xml")
def sitemap():
    """Generate dynamic XML sitemap"""
    from datetime import datetime
    
    urls = []
    
    # Static pages
    static_pages = [
        ("home", 1.0, "weekly"),
        ("about", 0.8, "monthly"),
        ("events", 0.9, "weekly"),
        ("sponsors", 0.7, "monthly"),
        ("partnerships", 0.7, "monthly"),
        ("posts", 0.9, "weekly"),
        ("gallery", 0.8, "weekly"),
        ("videos", 0.8, "weekly"),
        ("testimonials", 0.7, "monthly"),
        ("faq", 0.6, "monthly"),
        ("classes", 0.9, "weekly"),
        ("merchandise", 0.8, "weekly"),
        ("contact", 0.6, "monthly"),
    ]
    
    for page, priority, changefreq in static_pages:
        try:
            url = url_for(page, _external=True)
            urls.append({
                "loc": url,
                "lastmod": datetime.utcnow().isoformat() + "Z",
                "changefreq": changefreq,
                "priority": priority,
            })
        except:
            pass
    
    # Dynamic pages from database
    try:
        # Posts
        posts = Post.query.filter_by(published=True).all()
        for post in posts:
            try:
                url = url_for("post_detail", post_id=post.id, _external=True)
                urls.append({
                    "loc": url,
                    "lastmod": post.updated_at.isoformat() + "Z" if hasattr(post, 'updated_at') else post.created_at.isoformat() + "Z",
                    "changefreq": "monthly",
                    "priority": 0.8,
                })
            except:
                pass
        
        # Events
        events = Event.query.all()
        for event in events:
            try:
                url = url_for("events") + "#" + str(event.id)
                urls.append({
                    "loc": url,
                    "lastmod": event.date.isoformat() + "Z" if hasattr(event, 'date') else datetime.utcnow().isoformat() + "Z",
                    "changefreq": "weekly",
                    "priority": 0.7,
                })
            except:
                pass
    except:
        pass
    
    # Generate XML
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for url_entry in urls:
        xml += '  <url>\n'
        xml += f'    <loc>{url_entry["loc"]}</loc>\n'
        xml += f'    <lastmod>{url_entry["lastmod"]}</lastmod>\n'
        xml += f'    <changefreq>{url_entry["changefreq"]}</changefreq>\n'
        xml += f'    <priority>{url_entry["priority"]}</priority>\n'
        xml += '  </url>\n'
    
    xml += '</urlset>'
    
    return xml, 200, {"Content-Type": "application/xml; charset=utf-8"}


# Initialize database on startup (safely for serverless)
try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"Database initialization error: {e}")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

