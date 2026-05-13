# Dance with Sizzy Afro Website

A colorful multipage Flask + Tailwind CSS website for the Dance with Sizzy Afro brand.

## Pages
- Home: `/`
- Profile: `/about`
- Events: `/events`
- Sponsors: `/sponsors`
- Partnerships: `/partnerships`
- Connect: `/contact`
- Admin Panel: `/admin`

## Setup

1. Install dependencies:
   ```bash
   python -m pip install -r requirements.txt
   ```

2. Configure environment variables:
   - Copy `.env.example` to `.env`.
   - Set `SECRET_KEY` or `FLASK_SECRET_KEY`.
   - Set `ADMIN_USERNAME` and `ADMIN_PASSWORD`.
   - Add email credentials if you want contact notifications.
   - Add Supabase storage credentials if you want image uploads.

3. Start the Flask server:
   ```bash
   python app.py
   ```

4. Open:
   - http://127.0.0.1:5000

## Admin Panel
- Login at `/admin/login`.
- Production deployments must set `ADMIN_PASSWORD`.
- Do not use shared or easy-to-guess admin credentials.

## Email Notifications
When configured, contact form submissions can send notifications to `ADMIN_EMAIL`.

For Gmail:
- Go to Google Account > Security.
- Enable 2-Step Verification.
- Create an app password for Mail.
- Use that app password as `MAIL_PASSWORD`.

## Tech
- Flask
- Tailwind CSS CDN
- Flask-Mail
- Flask-SQLAlchemy
- PostgreSQL/Supabase-ready storage configuration
