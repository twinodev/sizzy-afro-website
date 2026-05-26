import os
import re
import mimetypes
import uuid
from secrets import token_urlsafe
from hmac import compare_digest
from datetime import datetime
from functools import wraps
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for, jsonify
from types import SimpleNamespace
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
import io
import csv

app = Flask(__name__)


def _required_secret_key():
    secret_key = os.getenv("SECRET_KEY") or os.getenv("FLASK_SECRET_KEY")
    if secret_key:
        return secret_key

    env = os.getenv("FLASK_ENV", "development").lower()
    if env == "production":
        # Avoid failing the import on misconfigured deployments (Vercel, Render, etc.).
        # Use an ephemeral secret so the site stays up, but warn loudly.
        fallback = token_urlsafe(64)
        print(
            "WARNING: SECRET_KEY or FLASK_SECRET_KEY is not set. Using an ephemeral secret; sessions will not persist across restarts."
        )
        return fallback

    # Development fallback (convenience only)
    return "dev-only-change-this-secret"


app.config["SECRET_KEY"] = _required_secret_key()


def _get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = token_urlsafe(32)
        session["csrf_token"] = token
    return token


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
app.config["MAIL_SUPPRESS_SEND"] = os.getenv("MAIL_SUPPRESS_SEND", "False").lower() in {"1", "true", "yes", "on"}
app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL")
app.config["SUPABASE_SERVICE_ROLE_KEY"] = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
app.config["SUPABASE_FLYER_BUCKET"] = os.getenv("SUPABASE_FLYER_BUCKET", "event-flyers")
app.config["SUPABASE_LOGO_BUCKET"] = os.getenv("SUPABASE_LOGO_BUCKET", "sponsor-logos")
app.config["SUPABASE_POST_BUCKET"] = os.getenv("SUPABASE_POST_BUCKET", "post-images")
app.config["SUPABASE_GALLERY_BUCKET"] = os.getenv("SUPABASE_GALLERY_BUCKET", app.config["SUPABASE_POST_BUCKET"])

# Initialize mail lazily
mail = None

def get_mail():
    """Get mail instance, initializing if needed"""
    global mail
    if mail is None:
        from flask_mail import Mail
        mail = Mail(app)
    return mail


@app.context_processor
def inject_csrf_token():
    return {"csrf_token": _get_csrf_token()}


@app.before_request
def validate_csrf_token():
    if request.method != "POST":
        return

    submitted_token = (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
    )
    if not submitted_token or submitted_token != session.get("csrf_token"):
        abort(400)


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
    likes = db.Column(db.Integer, default=0, nullable=False)


class Comment(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    approved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=True)


class Testimonial(db.Model):
    __tablename__ = "testimonials"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    title = db.Column(db.String(255))
    message = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)


class FAQ(db.Model):
    __tablename__ = "faqs"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    question = db.Column(db.String(255), nullable=False)
    answer = db.Column(db.Text, nullable=False)
    order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.String(50), nullable=False)


class Merchandise(db.Model):
    __tablename__ = "merchandise"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    name = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    image_url = db.Column(db.Text)
    price = db.Column(db.String(50))
    purchase_url = db.Column(db.Text)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)


class Video(db.Model):
    __tablename__ = "videos"
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('events.id'), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    url = db.Column(db.Text, nullable=False)
    thumbnail_url = db.Column(db.Text)
    published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.String(50), nullable=False)


class GalleryItem(db.Model):
    __tablename__ = "gallery"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    category = db.Column(db.String(100))
    image_url = db.Column(db.Text)
    featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.String(50), nullable=False)


class ClassSchedule(db.Model):
    __tablename__ = "class_schedules"
    id = db.Column(db.Integer, primary_key=True)
    day_of_week = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.String(20), nullable=False)
    end_time = db.Column(db.String(20), nullable=False)
    class_name = db.Column(db.String(255), nullable=False)
    level = db.Column(db.String(50))
    location = db.Column(db.String(255))
    created_at = db.Column(db.String(50), nullable=False)


class SocialLink(db.Model):
    __tablename__ = "social_links"
    id = db.Column(db.Integer, primary_key=True)
    platform = db.Column(db.String(50), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.String(50), nullable=False)


class PageView(db.Model):
    """Track page views and user interactions for analytics."""
    __tablename__ = "page_views"
    id = db.Column(db.Integer, primary_key=True)
    endpoint = db.Column(db.String(255), nullable=False)  # e.g., 'home', 'events', 'contact'
    path = db.Column(db.String(500), nullable=False)  # e.g., '/events/5'
    method = db.Column(db.String(10), default="GET")  # GET, POST, etc.
    user_agent = db.Column(db.Text)  # Browser info
    referrer = db.Column(db.String(500))  # Where user came from
    ip_address = db.Column(db.String(50))  # Client IP
    created_at = db.Column(db.String(50), nullable=False)  # Timestamp


def init_db():
    """Initialize database tables"""
    with app.app_context():
        db.create_all()
        _ensure_posts_published_column()
        _ensure_event_flyer_column()
        _ensure_merchandise_event_id_column()
        _ensure_merchandise_published_column()
        _ensure_testimonials_event_id_column()
        _ensure_testimonials_published_column()
        _ensure_faqs_event_id_column()
        _ensure_videos_event_id_column()
        _ensure_videos_published_column()
        _ensure_posts_likes_column()
        _ensure_comments_parent_id_column()


def _ensure_merchandise_published_column():
    """Add published boolean column to merchandise if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("merchandise")}

        if "published" not in columns:
            # Add column with default True so existing records are treated as published
            db.session.execute(text("ALTER TABLE merchandise ADD COLUMN published BOOLEAN DEFAULT true"))
            db.session.commit()
            print("Added published column to merchandise table")
    except Exception as e:
        print(f"Migration: Could not add published to merchandise: {e}")


def _ensure_event_flyer_column():
    """Add flyer_url to existing events tables if needed."""
    inspector = inspect(db.engine)
    columns = {column["name"] for column in inspector.get_columns("events")}

    if "flyer_url" not in columns:
        db.session.execute(text("ALTER TABLE events ADD COLUMN flyer_url TEXT"))
        db.session.commit()


def _ensure_merchandise_event_id_column():
    """Add event_id to existing merchandise tables if needed."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("merchandise")}

        if "event_id" not in columns:
            db.session.execute(text("ALTER TABLE merchandise ADD COLUMN event_id INTEGER REFERENCES events(id)"))
            db.session.commit()
            print("Added event_id column to merchandise table")
    except Exception as e:
        print(f"Migration: Could not add event_id to merchandise: {e}")


def _ensure_testimonials_event_id_column():
    """Add event_id to existing testimonials tables if needed."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("testimonials")}

        if "event_id" not in columns:
            db.session.execute(text("ALTER TABLE testimonials ADD COLUMN event_id INTEGER REFERENCES events(id)"))
            db.session.commit()
            print("Added event_id column to testimonials table")
    except Exception as e:
        print(f"Migration: Could not add event_id to testimonials: {e}")


def _ensure_faqs_event_id_column():
    """Add event_id to existing faqs tables if needed."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("faqs")}

        if "event_id" not in columns:
            db.session.execute(text("ALTER TABLE faqs ADD COLUMN event_id INTEGER REFERENCES events(id)"))
            db.session.commit()
            print("Added event_id column to faqs table")
    except Exception as e:
        print(f"Migration: Could not add event_id to faqs: {e}")


def _ensure_videos_event_id_column():
    """Add event_id to existing videos tables if needed."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("videos")}

        if "event_id" not in columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN event_id INTEGER REFERENCES events(id)"))
            db.session.commit()
            print("Added event_id column to videos table")
    except Exception as e:
        print(f"Migration: Could not add event_id to videos: {e}")


def _ensure_posts_likes_column():
    """Add likes column to posts if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("posts")}

        if "likes" not in columns:
            db.session.execute(text("ALTER TABLE posts ADD COLUMN likes INTEGER DEFAULT 0 NOT NULL"))
            db.session.commit()
            print("Added likes column to posts table")
    except Exception as e:
        print(f"Migration: Could not add likes to posts: {e}")


def _ensure_posts_published_column():
    """Add published column to posts if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("posts")}

        if "published" not in columns:
            db.session.execute(text("ALTER TABLE posts ADD COLUMN published BOOLEAN DEFAULT true"))
            db.session.commit()
            print("Added published column to posts table")
    except Exception as e:
        print(f"Migration: Could not add published to posts: {e}")


def _ensure_testimonials_published_column():
    """Add published column to testimonials if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("testimonials")}

        if "published" not in columns:
            db.session.execute(text("ALTER TABLE testimonials ADD COLUMN published BOOLEAN DEFAULT true"))
            db.session.commit()
            print("Added published column to testimonials table")
    except Exception as e:
        print(f"Migration: Could not add published to testimonials: {e}")


def _ensure_videos_published_column():
    """Add published column to videos if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("videos")}

        if "published" not in columns:
            db.session.execute(text("ALTER TABLE videos ADD COLUMN published BOOLEAN DEFAULT true"))
            db.session.commit()
            print("Added published column to videos table")
    except Exception as e:
        print(f"Migration: Could not add published to videos: {e}")


def _ensure_comments_parent_id_column():
    """Add parent_id column to comments if missing."""
    try:
        inspector = inspect(db.engine)
        columns = {column["name"] for column in inspector.get_columns("comments")}

        if "parent_id" not in columns:
            db.session.execute(text("ALTER TABLE comments ADD COLUMN parent_id INTEGER REFERENCES comments(id)"))
            db.session.commit()
            print("Added parent_id column to comments table")
    except Exception as e:
        print(f"Migration: Could not add parent_id to comments: {e}")



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


def _upload_gallery_image_to_supabase(file_storage):
    return _upload_image_to_supabase(file_storage, app.config["SUPABASE_GALLERY_BUCKET"], "gallery", "gallery")


def _upload_merchandise_image_to_supabase(file_storage):
    return _upload_image_to_supabase(file_storage, app.config["SUPABASE_POST_BUCKET"], "merchandise", "merchandise image")


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


def _site_url():
    configured = os.getenv("SITE_URL", "").strip().rstrip("/")
    if configured:
        return configured
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return ""


def _absolute_url(path_or_url):
    if not path_or_url:
        return ""
    if path_or_url.startswith("http://") or path_or_url.startswith("https://"):
        return path_or_url
    base = _site_url()
    if not base:
        return path_or_url
    if path_or_url.startswith("/"):
        return f"{base}{path_or_url}"
    return f"{base}/{path_or_url}"


def _clean_canonical_url(url_value):
    parsed = urlparse(url_value)
    filtered_query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}
        ],
        doseq=True,
    )
    return urlunparse(parsed._replace(query=filtered_query, fragment=""))


def _truncate_text(value, length=160):
    if not value:
        return ""
    compact = " ".join(str(value).split())
    if len(compact) <= length:
        return compact
    return compact[: length - 1].rstrip() + "…"


def _default_seo_for_request():
    endpoint = request.endpoint or ""
    is_admin = endpoint.startswith("admin")

    title_map = {
        "home": "Dance with Sizzy Afro | Afro Dance Classes, Events, Community",
        "about": "Profile | Dance with Sizzy Afro",
        "community": "Community | Dance with Sizzy Afro",
        "contact": "Contact and Bookings | Dance with Sizzy Afro",
        "events": "Afro Dance Events | Dance with Sizzy Afro",
        "event_detail": "Event Details | Dance with Sizzy Afro",
        "videos": "Afro Dance Videos | Dance with Sizzy Afro",
        "merchandise": "Merchandise | Dance with Sizzy Afro",
        "sponsors": "Sponsors | Dance with Sizzy Afro",
        "partnerships": "Partnership Opportunities | Dance with Sizzy Afro",
        "posts": "Dance Blog Posts | Dance with Sizzy Afro",
        "post_detail": "Post | Dance with Sizzy Afro",
        "testimonials_page": "Testimonials | Dance with Sizzy Afro",
        "submit_testimonial": "Share Your Testimonial | Dance with Sizzy Afro",
    }

    description_map = {
        "home": "Join Dance with Sizzy Afro for Afro dance classes, live events, performances, and community-led movement experiences.",
        "about": "Meet Sizzy Afro and explore the dance journey, mission, and creative profile behind the movement.",
        "community": "Connect with the Dance with Sizzy Afro community through workshops, challenges, and collaborations.",
        "contact": "Book classes, performances, and collaborations with Dance with Sizzy Afro.",
        "events": "Discover upcoming Afro dance events, workshops, and live performances.",
        "videos": "Watch featured Afro dance videos, choreography, and performance highlights.",
        "merchandise": "Shop official Dance with Sizzy Afro merchandise and dance-inspired products.",
        "sponsors": "Explore sponsors and supporters powering Dance with Sizzy Afro experiences.",
        "partnerships": "Partner with Dance with Sizzy Afro through curated sponsorship and collaboration plans.",
        "posts": "Read dance stories, updates, and tips from Dance with Sizzy Afro.",
        "post_detail": "Read the latest dance insights and updates from Dance with Sizzy Afro.",
        "testimonials_page": "See testimonials from dancers and community members.",
        "submit_testimonial": "Share your Dance with Sizzy Afro experience.",
    }

    page_url = _clean_canonical_url(request.url)
    default_image = _absolute_url(url_for("static", filename="images/hero.jpg"))
    site_name = "Dance with Sizzy Afro"

    seo = {
        "title": title_map.get(endpoint, f"{site_name} | Afro Dance"),
        "description": description_map.get(
            endpoint,
            "Dance with Sizzy Afro brings Afro dance classes, creative performances, and vibrant community culture together.",
        ),
        "canonical_url": page_url,
        "robots": "noindex, nofollow" if is_admin else "index, follow, max-image-preview:large",
        "og_type": "website",
        "og_image": default_image,
        "twitter_card": "summary_large_image",
        "keywords": "Afro dance, dance classes, dance events, choreography, Sizzy Afro",
        "site_name": site_name,
        "json_ld": [
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": site_name,
                "url": _site_url(),
                "logo": _absolute_url(url_for("static", filename="images/logo.png")),
                "sameAs": [
                    "https://instagram.com/sizzyafro",
                    "https://tiktok.com/@sizzyafro",
                    "https://youtube.com/@sizzyafro",
                ],
            },
            {
                "@context": "https://schema.org",
                "@type": "WebSite",
                "name": site_name,
                "url": _site_url(),
            },
        ],
    }

    if endpoint in {"post_detail", "event_detail"}:
        seo["og_type"] = "article"

    return seo


def _get_client_ip():
    """Get the client IP address from request."""
    if request.environ.get('HTTP_X_FORWARDED_FOR'):
        return request.environ['HTTP_X_FORWARDED_FOR'].split(',')[0].strip()
    return request.environ.get('REMOTE_ADDR', 'unknown')


@app.before_request
def track_page_view():
    """Automatically track page views for analytics."""
    # Don't track static files, admin panel logins, or internal routes
    skip_endpoints = {'static', 'admin_login', 'send_test_email'}
    if request.endpoint and request.endpoint not in skip_endpoints:
        try:
            page_view = PageView(
                endpoint=request.endpoint or 'unknown',
                path=request.path,
                method=request.method,
                user_agent=request.headers.get('User-Agent', '')[:500],
                referrer=request.headers.get('Referer', '')[:500],
                ip_address=_get_client_ip(),
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            )
            db.session.add(page_view)
            db.session.commit()
        except Exception as e:
            # Don't let tracking errors break the app
            print(f"Failed to track page view: {e}")
            db.session.rollback()


@app.context_processor
def inject_seo_context():
    return {
        "seo_defaults": _default_seo_for_request(),
    }


@app.route("/")
def home():
    # Show latest published posts on home page
    try:
        recent_posts = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).limit(3).all()
    except Exception as e:
        # If database is unavailable, gracefully show homepage without posts
        print(f"Failed to fetch recent posts: {e}")
        recent_posts = []
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


@app.route("/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    """Handle newsletter signups from the homepage form.

    Attempts to store the signup as a lightweight Submission record. If the
    database is unavailable, silently continue so the public site doesn't 500.
    """
    email = request.form.get("email", "").strip()
    if not email:
        flash("Please enter a valid email address.", "error")
        return redirect(url_for("home"))

    try:
        submission = Submission(
            name="newsletter",
            email=email,
            message="newsletter_signup",
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.session.add(submission)
        db.session.commit()
    except Exception as e:
        # Don't raise — log and continue so the public homepage remains available.
        print(f"Failed to record newsletter signup: {e}")

    flash("Thanks — you've been added to the newsletter.", "success")
    return redirect(url_for("home"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        admin_username = os.getenv("ADMIN_USERNAME", "admin")
        admin_password = os.getenv("ADMIN_PASSWORD")
        if not admin_password:
            if os.getenv("FLASK_ENV", "development").lower() == "production":
                flash("Admin login is not configured. Set ADMIN_PASSWORD.", "error")
                return render_template("admin_login.html"), 503
            admin_password = "dev-admin-password"

        if compare_digest(username, admin_username) and compare_digest(password, admin_password):
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
    try:
        submissions = Submission.query.order_by(Submission.id.desc()).all()
    except Exception:
        submissions = []
    
    try:
        total_submissions = Submission.query.count()
    except Exception:
        total_submissions = 0
    
    try:
        total_events = Event.query.count()
    except Exception:
        total_events = 0
    
    try:
        total_posts = Post.query.count()
    except Exception:
        total_posts = 0
    
    try:
        total_sponsors = Sponsor.query.count()
    except Exception:
        total_sponsors = 0
    
    try:
        total_plans = PartnershipPlan.query.count()
    except Exception:
        total_plans = 0

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
    try:
        events_list = Event.query.order_by(Event.event_date.desc()).all()
    except Exception as e:
        print(f"Failed to load events: {e}")
        events_list = []
    return render_template("events.html", events=events_list)


@app.route("/events/<int:event_id>")
def event_detail(event_id):
    # Diagnostic logging to help trace why event details may be missing in production
    try:
        print(f"event_detail: entering event_id={event_id}")
        total_events = Event.query.count()
        print(f"event_detail: total_events={total_events}")
    except Exception as e:
        print(f"event_detail: failed pre-query diagnostics: {e}")

    try:
        event = Event.query.get_or_404(event_id)
        testimonials = Testimonial.query.filter_by(event_id=event_id, published=True).all()
        faqs = FAQ.query.filter_by(event_id=event_id).order_by(FAQ.order.asc()).all()
        merchandise = Merchandise.query.filter_by(event_id=event_id, published=True).all()
        videos = Video.query.filter_by(event_id=event_id, published=True).all()
    except Exception as e:
        # Distinguish not-found vs other DB errors in logs
        print(f"Failed to load event detail {event_id}: {type(e).__name__}: {e}")
        return render_template("event_detail.html", event=None, testimonials=[], faqs=[], merchandise=[], videos=[])

    # Log what was retrieved for easier debugging in production logs
    try:
        print(f"event_detail: event_id={event_id} event_found={bool(event)} title={getattr(event, 'title', None)} flyer_url_present={bool(getattr(event, 'flyer_url', None))}")
    except Exception:
        pass

    event_description = _truncate_text(
        event.description
        or f"Join {event.title} with Dance with Sizzy Afro at {event.location or 'our next venue'}."
    )

    seo = {
        "title": f"{event.title} | Dance with Sizzy Afro",
        "description": event_description,
        "og_type": "event",
        "og_image": _absolute_url(event.flyer_url) if event.flyer_url else _absolute_url(url_for("static", filename="images/hero.jpg")),
        "json_ld": [
            {
                "@context": "https://schema.org",
                "@type": "Event",
                "name": event.title,
                "description": event_description,
                "startDate": event.event_date,
                "location": {
                    "@type": "Place",
                    "name": event.location or "Venue To Be Announced",
                },
                "image": [
                    _absolute_url(event.flyer_url) if event.flyer_url else _absolute_url(url_for("static", filename="images/hero.jpg"))
                ],
                "organizer": {
                    "@type": "Organization",
                    "name": "Dance with Sizzy Afro",
                    "url": _site_url(),
                },
                "url": _clean_canonical_url(request.url),
            }
        ],
    }

    return render_template(
        "event_detail.html",
        event=event,
        testimonials=testimonials,
        faqs=faqs,
        merchandise=merchandise,
        videos=videos,
        seo=seo,
    )


@app.route("/videos")
def videos():
    page = request.args.get("page", 1, type=int)
    current_category = request.args.get("category")

    try:
        q = Video.query.filter_by(published=True)

        # Featured videos (most recent)
        featured_list = q.order_by(Video.created_at.desc()).limit(3).all()

        # Paginate main list
        videos_pagination = q.order_by(Video.created_at.desc()).paginate(page=page, per_page=9, error_out=False)

        # Helper to extract YouTube ID from common URL forms
        def extract_youtube_id(url):
            if not url:
                return None
            try:
                parsed = urlparse(url)
                if parsed.netloc.endswith('youtu.be'):
                    return parsed.path.lstrip('/')
                qs = dict(parse_qsl(parsed.query))
                if 'v' in qs:
                    return qs['v']
                parts = parsed.path.split('/')
                if parts:
                    return parts[-1]
            except Exception:
                return None
            return None

        def display_thumbnail(video):
            if video.thumbnail_url:
                return video.thumbnail_url
            youtube_id = extract_youtube_id(video.url)
            if youtube_id:
                return f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
            return url_for("static", filename="images/hero.jpg")

        # Attach youtube_id attribute for template convenience
        for v in featured_list:
            setattr(v, 'youtube_id', extract_youtube_id(v.url) or '')
            setattr(v, 'display_url', v.url)
            setattr(v, 'display_thumbnail', display_thumbnail(v))
        for v in videos_pagination.items:
            setattr(v, 'youtube_id', extract_youtube_id(v.url) or '')
            setattr(v, 'display_url', v.url)
            setattr(v, 'display_thumbnail', display_thumbnail(v))

        categories = []
    except Exception as e:
        print(f"Failed to load videos: {e}")
        featured_list = []
        videos_pagination = type('P', (), {'items': [], 'pages': 0, 'has_prev': False, 'has_next': False, 'page': 1, 'prev_num': None, 'next_num': None, 'iter_pages': lambda self: []})()
        categories = []

    return render_template('videos.html', featured=featured_list, videos=videos_pagination, categories=categories, current_category=current_category)


@app.route("/merchandise")
def merchandise():
    page = request.args.get("page", 1, type=int)
    current_category = request.args.get("category")

    try:
        q = Merchandise.query.filter_by(published=True)

        # Featured items (most recent)
        featured_list = q.order_by(Merchandise.created_at.desc()).limit(4).all()

        # Paginate main list
        products_pagination = q.order_by(Merchandise.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

        categories = []
    except Exception as e:
        print(f"Failed to load merchandise: {e}")
        featured_list = []
        products_pagination = type('P', (), {'items': [], 'pages': 0, 'has_prev': False, 'has_next': False, 'page': 1, 'prev_num': None, 'next_num': None, 'iter_pages': lambda self: []})()
        categories = []

    return render_template('merchandise.html', featured=featured_list, products=products_pagination, categories=categories, current_category=current_category)


@app.route("/sponsors")
def sponsors():
    try:
        sponsors_list = Sponsor.query.order_by(Sponsor.tier.desc(), Sponsor.name.asc()).all()
    except Exception as e:
        print(f"Failed to load sponsors: {e}")
        sponsors_list = []
    return render_template("sponsors.html", sponsors=sponsors_list)


@app.route("/partnerships")
def partnerships():
    try:
        plans = PartnershipPlan.query.order_by(PartnershipPlan.id.asc()).all()
    except Exception as e:
        print(f"Failed to load partnerships: {e}")
        plans = []
    return render_template("partnerships.html", plans=plans)


@app.route("/posts")
def posts():
    try:
        posts_list = Post.query.filter_by(published=True).order_by(Post.created_at.desc()).all()
    except Exception as e:
        print(f"Failed to load posts: {e}")
        posts_list = []
    return render_template("posts.html", posts=posts_list)


@app.route("/posts/<int:post_id>", methods=["GET", "POST"])
def post_detail(post_id):
    try:
        post = Post.query.get_or_404(post_id)
    except Exception as e:
        print(f"Failed to load post {post_id}: {e}")
        flash("Unable to load post at this time.", "error")
        return redirect(url_for("posts"))

    if not post.published:
        flash("This post is not published.", "error")
        return redirect(url_for("posts"))

    if request.method == "POST":
        # Accept comments on posts (including replies)
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        parent_id = request.form.get("parent_id")

        if not name or not email or not message:
            flash("Please provide your name, email, and a comment.", "error")
            return redirect(url_for("post_detail", post_id=post_id))

        comment = Comment(
            post_id=post.id,
            name=name,
            email=email,
            message=message,
            approved=False,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            parent_id=int(parent_id) if parent_id else None,
        )
        db.session.add(comment)
        db.session.commit()
        flash("Thanks — your comment is pending approval.", "success")
        return redirect(url_for("post_detail", post_id=post_id))

    related_posts = Post.query.filter(Post.published == True, Post.id != post_id).order_by(Post.created_at.desc()).limit(3).all()
    # Fetch approved comments and assemble nested replies
    comments_all = Comment.query.filter_by(post_id=post.id, approved=True).order_by(Comment.id.asc()).all()
    comments_by_id = {c.id: c for c in comments_all}
    roots = []
    for c in comments_all:
        setattr(c, 'replies', [])
    for c in comments_all:
        if getattr(c, 'parent_id', None):
            parent = comments_by_id.get(c.parent_id)
            if parent:
                parent.replies.append(c)
            else:
                roots.append(c)
        else:
            roots.append(c)
    comments = roots
    post_description = _truncate_text(post.excerpt or post.content)
    post_image = _absolute_url(post.image_url) if post.image_url else _absolute_url(url_for("static", filename="images/hero.jpg"))
    seo = {
        "title": f"{post.title} | Dance with Sizzy Afro",
        "description": post_description,
        "og_type": "article",
        "og_image": post_image,
        "json_ld": [
            {
                "@context": "https://schema.org",
                "@type": "BlogPosting",
                "headline": post.title,
                "description": post_description,
                "image": [post_image],
                "datePublished": post.created_at,
                "dateModified": post.updated_at or post.created_at,
                "author": {
                    "@type": "Organization",
                    "name": "Dance with Sizzy Afro",
                },
                "publisher": {
                    "@type": "Organization",
                    "name": "Dance with Sizzy Afro",
                    "logo": {
                        "@type": "ImageObject",
                        "url": _absolute_url(url_for("static", filename="images/logo.png")),
                    },
                },
                "mainEntityOfPage": _clean_canonical_url(request.url),
            }
        ],
    }
    return render_template("post_detail.html", post=post, related_posts=related_posts, comments=comments, seo=seo)


@app.route("/posts/<int:post_id>/like", methods=["POST"])
def post_like(post_id):
    try:
        post = Post.query.get_or_404(post_id)
        post.likes = (post.likes or 0) + 1
        db.session.commit()
    except Exception as e:
        print(f"Like failed for post {post_id}: {e}")
        if request.is_json:
            return jsonify({"error": "failed"}), 500
        flash("Unable to like post.", "error")
        return redirect(url_for('post_detail', post_id=post_id))

    if request.is_json:
        return jsonify({"likes": post.likes})
    return redirect(url_for('post_detail', post_id=post_id))


@app.route("/robots.txt")
def robots_txt():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        f"Sitemap: {_absolute_url(url_for('sitemap_xml'))}",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


def _safe_lastmod(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt).date().isoformat()
        except ValueError:
            continue
    return None


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = []

    static_endpoints = [
        "home",
        "about",
        "community",
        "contact",
        "events",
        "videos",
        "merchandise",
        "sponsors",
        "partnerships",
        "posts",
        "testimonials_page",
        "submit_testimonial",
    ]

    for endpoint in static_endpoints:
        try:
            urls.append({"loc": _absolute_url(url_for(endpoint)), "lastmod": None})
        except Exception:
            continue

    try:
        for event in Event.query.order_by(Event.id.desc()).all():
            urls.append(
                {
                    "loc": _absolute_url(url_for("event_detail", event_id=event.id)),
                    "lastmod": _safe_lastmod(event.created_at),
                }
            )
    except Exception as e:
        print(f"Sitemap events generation failed: {e}")

    try:
        for post in Post.query.filter_by(published=True).order_by(Post.id.desc()).all():
            urls.append(
                {
                    "loc": _absolute_url(url_for("post_detail", post_id=post.id)),
                    "lastmod": _safe_lastmod(post.updated_at or post.created_at),
                }
            )
    except Exception as e:
        print(f"Sitemap posts generation failed: {e}")

    xml_rows = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    for item in urls:
        xml_rows.append("  <url>")
        xml_rows.append(f"    <loc>{item['loc']}</loc>")
        if item.get("lastmod"):
            xml_rows.append(f"    <lastmod>{item['lastmod']}</lastmod>")
        xml_rows.append("  </url>")
    xml_rows.append("</urlset>")

    return Response("\n".join(xml_rows), mimetype="application/xml")


# Admin Events Management
@app.route("/admin/events")
@admin_required
def admin_events():
    try:
        events_list = Event.query.order_by(Event.event_date.desc()).all()
    except Exception as e:
        print(f"Failed to load admin events: {e}")
        events_list = []
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
    try:
        sponsors_list = Sponsor.query.order_by(Sponsor.tier.desc(), Sponsor.name.asc()).all()
    except Exception as e:
        print(f"Failed to load admin sponsors: {e}")
        sponsors_list = []
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
    try:
        plans = PartnershipPlan.query.order_by(PartnershipPlan.id.asc()).all()
    except Exception as e:
        print(f"Failed to load admin partnerships: {e}")
        plans = []
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
    try:
        posts_list = Post.query.order_by(Post.created_at.desc()).all()
    except Exception as e:
        print(f"Failed to load admin posts: {e}")
        posts_list = []
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
        if _table_has_column("posts", "published"):
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
    try:
        submissions = Submission.query.order_by(Submission.id.desc()).all()
    except Exception as e:
        print(f"Failed to load admin submissions: {e}")
        submissions = []
    return render_template("admin_submissions.html", submissions=submissions)


@app.route("/admin/submissions/delete/<int:submission_id>", methods=["POST"])
@admin_required
def admin_submissions_delete(submission_id):
    submission = Submission.query.get_or_404(submission_id)
    db.session.delete(submission)
    db.session.commit()
    flash("Submission deleted successfully.", "success")
    return redirect(url_for("admin_submissions"))


# Admin Testimonials
@app.route("/admin/testimonials")
@admin_required
def admin_testimonials():
    try:
        testimonials = Testimonial.query.order_by(Testimonial.id.desc()).all()
    except Exception as e:
        print(f"Failed to load admin testimonials: {e}")
        testimonials = []
    return render_template("admin_testimonials.html", testimonials=testimonials)


# Public testimonials page
@app.route("/testimonials")
def testimonials_page():
    # If database lacks event_id column, avoid ORM select that references it
    if not _table_has_column('testimonials', 'event_id'):
        try:
            rows = db.session.execute(text("SELECT id, name, title, message, image_url, published, created_at FROM testimonials WHERE published = true ORDER BY created_at DESC")).fetchall()
            testimonials_list = [SimpleNamespace(**dict(row)) for row in rows]
        except Exception as e:
            print(f"Failed to load testimonials (fallback): {e}")
            testimonials_list = []
    else:
        try:
            testimonials_list = Testimonial.query.filter_by(published=True).order_by(Testimonial.created_at.desc()).all()
        except Exception as e:
            print(f"Failed to load testimonials: {e}")
            testimonials_list = []

    # Split featured (first 2) from the rest for the template
    featured = testimonials_list[:2]
    others = testimonials_list[2:]
    return render_template("testimonials.html", testimonials=others, featured=featured)


@app.route("/testimonials/submit", methods=["GET", "POST"])
def submit_testimonial():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        role = request.form.get("role", "").strip()
        content = request.form.get("content", "").strip()

        if not name or not content:
            flash("Name and testimonial are required.", "error")
            return redirect(url_for("submit_testimonial"))

        testimonial = Testimonial(
            name=name,
            title=role or None,
            message=content,
            published=False,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        try:
            db.session.add(testimonial)
            db.session.commit()
            flash("Thanks for sharing your experience. Your testimonial will be reviewed soon.", "success")
            return redirect(url_for("testimonials_page"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to save testimonial")
            flash("Unable to submit testimonial at this time. Please try again later.", "error")
            return redirect(url_for("testimonials_page"))

    return render_template("testimonial_form.html")


@app.route("/admin/testimonials/create", methods=["GET", "POST"])
@admin_required
def admin_testimonials_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()
        event_id = request.form.get("event_id", type=int) or None
        
        if not name or not message:
            flash("Name and message are required.", "error")
            return redirect(url_for("admin_testimonials_create"))
        
        testimonial = Testimonial(
            event_id=event_id,
            name=name,
            title=title or None,
            message=message,
            published=True,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(testimonial)
        db.session.commit()
        flash("Testimonial created successfully.", "success")
        return redirect(url_for("admin_testimonials"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_testimonials_form.html", testimonial=None, events=events)


@app.route("/admin/testimonials/edit/<int:testimonial_id>", methods=["GET", "POST"])
@admin_required
def admin_testimonials_edit(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    
    if request.method == "POST":
        testimonial.name = request.form.get("name", "").strip()
        testimonial.title = request.form.get("title", "").strip() or None
        testimonial.message = request.form.get("message", "").strip()
        testimonial.event_id = request.form.get("event_id", type=int) or None
        if _table_has_column("testimonials", "published"):
            testimonial.published = request.form.get("published") == "on"
        db.session.commit()
        flash("Testimonial updated successfully.", "success")
        return redirect(url_for("admin_testimonials"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_testimonials_form.html", testimonial=testimonial, events=events)


@app.route("/admin/testimonials/delete/<int:testimonial_id>", methods=["POST"])
@admin_required
def admin_testimonials_delete(testimonial_id):
    testimonial = Testimonial.query.get_or_404(testimonial_id)
    db.session.delete(testimonial)
    db.session.commit()
    flash("Testimonial deleted successfully.", "success")
    return redirect(url_for("admin_testimonials"))


# Admin FAQs
@app.route("/admin/faqs")
@admin_required
def admin_faqs():
    try:
        faqs = FAQ.query.order_by(FAQ.event_id.asc(), FAQ.order.asc()).all()
    except Exception as e:
        print(f"Failed to load admin faqs: {e}")
        faqs = []
    return render_template("admin_faqs.html", faqs=faqs)


@app.route("/admin/faqs/create", methods=["GET", "POST"])
@admin_required
def admin_faqs_create():
    if request.method == "POST":
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip()
        event_id = request.form.get("event_id", type=int) or None
        order = request.form.get("order", type=int, default=0)
        
        if not question or not answer:
            flash("Question and answer are required.", "error")
            return redirect(url_for("admin_faqs_create"))
        
        faq = FAQ(
            event_id=event_id,
            question=question,
            answer=answer,
            order=order,
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )
        db.session.add(faq)
        db.session.commit()
        flash("FAQ created successfully.", "success")
        return redirect(url_for("admin_faqs"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_faqs_form.html", faq=None, events=events)


@app.route("/admin/faqs/edit/<int:faq_id>", methods=["GET", "POST"])
@admin_required
def admin_faqs_edit(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    
    if request.method == "POST":
        faq.question = request.form.get("question", "").strip()
        faq.answer = request.form.get("answer", "").strip()
        faq.event_id = request.form.get("event_id", type=int) or None
        faq.order = request.form.get("order", type=int, default=0)
        db.session.commit()
        flash("FAQ updated successfully.", "success")
        return redirect(url_for("admin_faqs"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_faqs_form.html", faq=faq, events=events)


@app.route("/admin/faqs/delete/<int:faq_id>", methods=["POST"])
@admin_required
def admin_faqs_delete(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    db.session.delete(faq)
    db.session.commit()
    flash("FAQ deleted successfully.", "success")
    return redirect(url_for("admin_faqs"))


# Admin Merchandise
@app.route("/admin/merchandise")
@admin_required
def admin_merchandise():
    try:
        merchandise = Merchandise.query.order_by(Merchandise.id.desc()).all()
    except Exception as e:
        print(f"Failed to load admin merchandise: {e}")
        merchandise = []
    return render_template("admin_merchandise.html", merchandise=merchandise)


@app.route("/admin/merchandise/create", methods=["GET", "POST"])
@admin_required
def admin_merchandise_create():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("price", "").strip()
        purchase_url = request.form.get("purchase_url", "").strip()
        event_id = request.form.get("event_id", type=int) or None
        image_file = request.files.get("image_file")
        
        if not name:
            flash("Name is required.", "error")
            return redirect(url_for("admin_merchandise_create"))
        
        image_url = None
        if image_file and image_file.filename:
            try:
                image_url = _upload_merchandise_image_to_supabase(image_file)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_merchandise_create"))
        
        merch_kwargs = {
            "name": name,
            "description": description or None,
            "image_url": image_url,
            "price": price or None,
            "purchase_url": purchase_url or None,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }

        if _table_has_column("merchandise", "event_id"):
            merch_kwargs["event_id"] = event_id

        # Only include `published` if the column exists in the DB (safer for older schemas)
        if _table_has_column("merchandise", "published"):
            merch_kwargs["published"] = True

        merchandise = Merchandise(**merch_kwargs)
        db.session.add(merchandise)
        db.session.commit()
        flash("Merchandise created successfully.", "success")
        return redirect(url_for("admin_merchandise"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_merchandise_form.html", item=None, events=events)


@app.route("/admin/merchandise/edit/<int:item_id>", methods=["GET", "POST"])
@admin_required
def admin_merchandise_edit(item_id):
    item = Merchandise.query.get_or_404(item_id)
    
    if request.method == "POST":
        item.name = request.form.get("name", "").strip()
        item.description = request.form.get("description", "").strip() or None
        item.price = request.form.get("price", "").strip() or None
        item.purchase_url = request.form.get("purchase_url", "").strip() or None
        if _table_has_column("merchandise", "event_id"):
            item.event_id = request.form.get("event_id", type=int) or None
        # Only set published if the column exists
        if _table_has_column("merchandise", "published"):
                if _table_has_column("merchandise", "published"):
                    item.published = request.form.get("published") == "on"
        
        image_file = request.files.get("image_file")
        if image_file and image_file.filename:
            try:
                item.image_url = _upload_merchandise_image_to_supabase(image_file)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_merchandise_edit", item_id=item_id))
        
        db.session.commit()
        flash("Merchandise updated successfully.", "success")
        return redirect(url_for("admin_merchandise"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_merchandise_form.html", item=item, events=events)


@app.route("/admin/merchandise/delete/<int:item_id>", methods=["POST"])
@admin_required
def admin_merchandise_delete(item_id):
    item = Merchandise.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Merchandise deleted successfully.", "success")
    return redirect(url_for("admin_merchandise"))


# Admin Videos
@app.route("/admin/videos")
@admin_required
def admin_videos():
    try:
        videos = Video.query.order_by(Video.id.desc()).all()
    except Exception as e:
        print(f"Failed to load admin videos: {e}")
        videos = []
    return render_template("admin_videos.html", videos=videos)


@app.route("/admin/videos/create", methods=["GET", "POST"])
@admin_required
def admin_videos_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        url = request.form.get("url", "").strip()
        thumbnail_url = request.form.get("thumbnail_url", "").strip()
        event_id = request.form.get("event_id", type=int) or None
        
        if not title or not url:
            flash("Title and URL are required.", "error")
            return redirect(url_for("admin_videos_create"))
        
        video_kwargs = {
            "title": title,
            "description": description or None,
            "url": url,
            "thumbnail_url": thumbnail_url or None,
            "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }
        if _table_has_column("videos", "event_id"):
            video_kwargs["event_id"] = event_id
        if _table_has_column("videos", "published"):
            video_kwargs["published"] = True

        video = Video(**video_kwargs)
        try:
            db.session.add(video)
            db.session.commit()
            flash("Video created successfully.", "success")
            return redirect(url_for("admin_videos"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to save video")
            flash("Unable to create video. Please check the form and try again.", "error")
            return redirect(url_for("admin_videos_create"))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_videos_form.html", video=None, events=events)


@app.route("/admin/videos/edit/<int:video_id>", methods=["GET", "POST"])
@admin_required
def admin_videos_edit(video_id):
    video = Video.query.get_or_404(video_id)
    
    if request.method == "POST":
        video.title = request.form.get("title", "").strip()
        video.description = request.form.get("description", "").strip() or None
        video.url = request.form.get("url", "").strip()
        video.thumbnail_url = request.form.get("thumbnail_url", "").strip() or None
        if _table_has_column("videos", "event_id"):
            video.event_id = request.form.get("event_id", type=int) or None
        if _table_has_column("videos", "published"):
            video.published = request.form.get("published") == "on"
        try:
            db.session.commit()
            flash("Video updated successfully.", "success")
            return redirect(url_for("admin_videos"))
        except Exception:
            db.session.rollback()
            app.logger.exception("Failed to update video")
            flash("Unable to update video right now.", "error")
            return redirect(url_for("admin_videos_edit", video_id=video_id))
    
    try:
        events = Event.query.all()
    except Exception as e:
        print(f"Error fetching events: {e}")
        events = []
    return render_template("admin_videos_form.html", video=video, events=events)


@app.route("/admin/videos/delete/<int:video_id>", methods=["POST"])
@admin_required
def admin_videos_delete(video_id):
    video = Video.query.get_or_404(video_id)
    db.session.delete(video)
    db.session.commit()
    flash("Video deleted successfully.", "success")
    return redirect(url_for("admin_videos"))


# Admin Gallery
@app.route("/admin/gallery")
@admin_required
def admin_gallery():
    try:
        gallery = GalleryItem.query.order_by(GalleryItem.created_at.desc()).all()
    except Exception as e:
        print(f"Failed to load gallery items: {e}")
        gallery = []
    return render_template("admin_gallery.html", gallery=gallery)


@app.route("/admin/gallery/create", methods=["GET", "POST"])
@admin_required
def admin_gallery_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        category = request.form.get("category", "").strip() or None
        image_file = request.files.get("image_file")
        featured = request.form.get("featured") == "on"

        if not title:
            flash("Title is required.", "error")
            return redirect(url_for("admin_gallery_create"))

        try:
            image_url = _upload_gallery_image_to_supabase(image_file)
        except ValueError as error:
            flash(str(error), "error")
            return redirect(url_for("admin_gallery_create"))

        try:
            item = GalleryItem(
                title=title,
                category=category,
                image_url=image_url,
                featured=featured,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.session.add(item)
            db.session.commit()
            flash("Gallery item created.", "success")
            return redirect(url_for("admin_gallery"))
        except Exception as e:
            print(f"Failed to create gallery item: {e}")
            flash("Failed to create gallery item.", "error")
            return redirect(url_for("admin_gallery_create"))

    return render_template("admin_gallery_form.html", item=None)


@app.route("/admin/gallery/edit/<int:item_id>", methods=["GET", "POST"])
@admin_required
def admin_gallery_edit(item_id):
    item = GalleryItem.query.get_or_404(item_id)

    if request.method == "POST":
        item.title = request.form.get("title", "").strip()
        item.category = request.form.get("category", "").strip() or None
        item.featured = request.form.get("featured") == "on"
        image_file = request.files.get("image_file")
        if image_file and image_file.filename:
            try:
                item.image_url = _upload_gallery_image_to_supabase(image_file)
            except ValueError as error:
                flash(str(error), "error")
                return redirect(url_for("admin_gallery_edit", item_id=item_id))
        db.session.commit()
        flash("Gallery item updated.", "success")
        return redirect(url_for("admin_gallery"))

    return render_template("admin_gallery_form.html", item=item)


@app.route("/admin/gallery/delete/<int:item_id>", methods=["POST"])
@admin_required
def admin_gallery_delete(item_id):
    item = GalleryItem.query.get_or_404(item_id)
    try:
        db.session.delete(item)
        db.session.commit()
        flash("Gallery item deleted.", "success")
    except Exception as e:
        print(f"Failed to delete gallery item: {e}")
        flash("Failed to delete gallery item.", "error")
    return redirect(url_for("admin_gallery"))


# Admin Classes (schedule)
@app.route("/admin/classes")
@admin_required
def admin_classes():
    try:
        schedules = ClassSchedule.query.order_by(ClassSchedule.id.asc()).all()
    except Exception as e:
        print(f"Failed to load class schedules: {e}")
        schedules = []
    return render_template("admin_classes.html", schedules=schedules)


@app.route("/admin/classes/create", methods=["GET", "POST"])
@admin_required
def admin_classes_create():
    if request.method == "POST":
        day_of_week = request.form.get("day_of_week", "").strip()
        start_time = request.form.get("start_time", "").strip()
        end_time = request.form.get("end_time", "").strip()
        class_name = request.form.get("class_name", "").strip()
        level = request.form.get("level", "").strip() or None
        location = request.form.get("location", "").strip() or None

        if not day_of_week or not start_time or not end_time or not class_name:
            flash("Day, time, and class name are required.", "error")
            return redirect(url_for("admin_classes_create"))

        try:
            sched = ClassSchedule(
                day_of_week=day_of_week,
                start_time=start_time,
                end_time=end_time,
                class_name=class_name,
                level=level,
                location=location,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.session.add(sched)
            db.session.commit()
            flash("Class scheduled.", "success")
            return redirect(url_for("admin_classes"))
        except Exception as e:
            print(f"Failed to create schedule: {e}")
            flash("Failed to create schedule.", "error")
            return redirect(url_for("admin_classes_create"))

    return render_template("admin_classes_form.html", schedule=None)


@app.route("/admin/classes/edit/<int:schedule_id>", methods=["GET", "POST"])
@admin_required
def admin_classes_edit(schedule_id):
    schedule = ClassSchedule.query.get_or_404(schedule_id)

    if request.method == "POST":
        schedule.day_of_week = request.form.get("day_of_week", "").strip()
        schedule.start_time = request.form.get("start_time", "").strip()
        schedule.end_time = request.form.get("end_time", "").strip()
        schedule.class_name = request.form.get("class_name", "").strip()
        schedule.level = request.form.get("level", "").strip() or None
        schedule.location = request.form.get("location", "").strip() or None
        db.session.commit()
        flash("Schedule updated.", "success")
        return redirect(url_for("admin_classes"))

    return render_template("admin_classes_form.html", schedule=schedule)


@app.route("/admin/classes/delete/<int:schedule_id>", methods=["POST"])
@admin_required
def admin_classes_delete(schedule_id):
    schedule = ClassSchedule.query.get_or_404(schedule_id)
    try:
        db.session.delete(schedule)
        db.session.commit()
        flash("Schedule deleted.", "success")
    except Exception as e:
        print(f"Failed to delete schedule: {e}")
        flash("Failed to delete schedule.", "error")
    return redirect(url_for("admin_classes"))


# Admin Comments
@app.route("/admin/comments")
@admin_required
def admin_comments():
    try:
        comments = Comment.query.order_by(Comment.created_at.desc()).all()
    except Exception as e:
        print(f"Failed to load comments: {e}")
        comments = []
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
    flash("Comment deleted.", "success")
    return redirect(url_for("admin_comments"))


# Admin Newsletter
@app.route("/admin/newsletter")
@admin_required
def admin_newsletter():
    try:
        subscribers = Submission.query.filter_by(name="newsletter").order_by(Submission.created_at.desc()).all()
    except Exception as e:
        print(f"Failed to load newsletter subscribers: {e}")
        subscribers = []
    return render_template("admin_newsletter.html", subscribers=subscribers)


# Admin Social Links
@app.route("/admin/social-links")
@admin_required
def admin_social_links():
    try:
        links = SocialLink.query.order_by(SocialLink.id.asc()).all()
    except Exception as e:
        print(f"Failed to load social links: {e}")
        links = []
    return render_template("admin_social_links.html", links=links)


@app.route("/admin/social-links/create", methods=["GET", "POST"])
@admin_required
def admin_social_links_create():
    if request.method == "POST":
        platform = request.form.get("platform", "").strip()
        url = request.form.get("url", "").strip()

        if not platform or not url:
            flash("Platform and URL are required.", "error")
            return redirect(url_for("admin_social_links_create"))

        try:
            link = SocialLink(
                platform=platform,
                url=url,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.session.add(link)
            db.session.commit()
            flash("Social link created.", "success")
            return redirect(url_for("admin_social_links"))
        except Exception as e:
            print(f"Failed to create social link: {e}")
            flash("Failed to create social link.", "error")
            return redirect(url_for("admin_social_links_create"))

    return render_template("admin_social_links_form.html", link=None)


@app.route("/admin/social-links/edit/<int:link_id>", methods=["GET", "POST"])
@admin_required
def admin_social_links_edit(link_id):
    link = SocialLink.query.get_or_404(link_id)

    if request.method == "POST":
        link.platform = request.form.get("platform", "").strip()
        link.url = request.form.get("url", "").strip()
        db.session.commit()
        flash("Social link updated.", "success")
        return redirect(url_for("admin_social_links"))

    return render_template("admin_social_links_form.html", link=link)


@app.route("/admin/social-links/delete/<int:link_id>", methods=["POST"])
@admin_required
def admin_social_links_delete(link_id):
    link = SocialLink.query.get_or_404(link_id)
    try:
        db.session.delete(link)
        db.session.commit()
        flash("Social link deleted.", "success")
    except Exception as e:
        print(f"Failed to delete social link: {e}")
        flash("Failed to delete social link.", "error")
    return redirect(url_for("admin_social_links"))


# Test Email
@app.route("/admin/send-test-email", methods=["POST"])
@admin_required
def send_test_email():
    """Send a test email to verify SMTP configuration."""
    try:
        email_body = """
Test Email from Dance with Sizzy Afro

This is a test email to verify your SMTP configuration is working correctly.

If you received this, your email setup is good to go!
        """
        result = send_notification_email(
            subject="Test Email from Dance with Sizzy Afro",
            body=email_body
        )
        if result:
            return {"message": "Test email sent successfully!"}, 200
        else:
            return {"message": "Failed to send test email. Check your SMTP configuration."}, 400
    except Exception as e:
        return {"message": f"Error: {str(e)}"}, 500


# Admin Analytics
@app.route("/admin/analytics")
@admin_required
def admin_analytics():
    """Display analytics dashboard with key metrics and insights."""
    try:
        # Total page views
        total_views = PageView.query.count()
        
        # Most visited pages
        from sqlalchemy import func
        popular_pages = db.session.query(
            PageView.endpoint,
            PageView.path,
            func.count(PageView.id).label('views')
        ).group_by(PageView.endpoint, PageView.path).order_by(
            func.count(PageView.id).desc()
        ).limit(10).all()
        
        # Recent views (last 100)
        recent_views = PageView.query.order_by(PageView.created_at.desc()).limit(100).all()
        
        # View trends - views by day
        daily_views = db.session.query(
            func.substr(PageView.created_at, 1, 10).label('date'),
            func.count(PageView.id).label('views')
        ).group_by(func.substr(PageView.created_at, 1, 10)).order_by(
            func.substr(PageView.created_at, 1, 10).desc()
        ).limit(30).all()
        
        # Top referrers
        top_referrers = db.session.query(
            PageView.referrer,
            func.count(PageView.id).label('count')
        ).filter(PageView.referrer != '').group_by(PageView.referrer).order_by(
            func.count(PageView.id).desc()
        ).limit(10).all()
        
    except Exception as e:
        print(f"Failed to load analytics: {e}")
        total_views = 0
        popular_pages = []
        recent_views = []
        daily_views = []
        top_referrers = []
    
    return render_template(
        "admin_analytics.html",
        total_views=total_views,
        popular_pages=popular_pages,
        recent_views=recent_views,
        daily_views=daily_views,
        top_referrers=top_referrers,
    )


# Admin analytics test ping (creates a PageView entry) — used to verify tracking
@app.route("/admin/analytics/ping", methods=["POST"])
@admin_required
def admin_analytics_ping():
    try:
        pv = PageView(
            endpoint="admin_analytics_ping",
            path=request.form.get("path", request.path),
            method="POST",
            user_agent=request.headers.get("User-Agent", "")[:500],
            referrer=request.headers.get("Referer", "")[:500],
            ip_address=_get_client_ip(),
            created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        )
        db.session.add(pv)
        db.session.commit()
        return jsonify({"ok": True, "message": "Ping recorded"}), 200
    except Exception:
        db.session.rollback()
        app.logger.exception("Failed to create analytics ping")
        return jsonify({"ok": False, "message": "Failed to record ping"}), 500


@app.route("/admin/analytics/export")
@admin_required
def admin_analytics_export():
    """Export page views as CSV (admin only)."""
    try:
        # Stream recent page views (limit to avoid huge exports)
        rows = PageView.query.order_by(PageView.created_at.desc()).limit(10000).all()

        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(["id", "endpoint", "path", "method", "user_agent", "referrer", "ip_address", "created_at"])
        for r in rows:
            writer.writerow([r.id, r.endpoint, r.path, r.method, (r.user_agent or '')[:1000], (r.referrer or ''), r.ip_address, r.created_at])

        output = si.getvalue()
        return Response(output, mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=page_views.csv"})
    except Exception:
        app.logger.exception("Failed to export analytics CSV")
        return abort(500)


@app.route("/admin/analytics/health")
@admin_required
def admin_analytics_health():
    """Return simple JSON health for analytics data."""
    try:
        total = PageView.query.count()
        last = PageView.query.order_by(PageView.created_at.desc()).first()
        last_at = last.created_at if last else None
        return jsonify({"ok": True, "total_views": total, "last_view_at": last_at})
    except Exception:
        app.logger.exception("Failed to read analytics health")
        return jsonify({"ok": False}), 500


# Helper: check table columns cache (used to avoid runtime errors on DBs missing columns)
_TABLE_COLUMN_CACHE = {}

def _table_has_column(table_name, column_name):
    key = f"{table_name}.{column_name}"
    if key in _TABLE_COLUMN_CACHE:
        return _TABLE_COLUMN_CACHE[key]
    try:
        inspector = inspect(db.engine)
        cols = {c["name"] for c in inspector.get_columns(table_name)}
        has = column_name in cols
    except Exception:
        has = False
    _TABLE_COLUMN_CACHE[key] = has
    return has


# Initialize database on startup (safely for serverless)
try:
    with app.app_context():
        init_db()
except Exception as e:
    print(f"Database initialization error: {e}")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    app.run(debug=debug, host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

