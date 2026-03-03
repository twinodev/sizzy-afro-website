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
   /usr/local/bin/python3.13 -m pip install --user -r requirements.txt
   ```

2. Configure email notifications (optional but recommended):
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your email credentials:
     - For Gmail: Enable "2-Step Verification" then create an "App Password"
     - Use that app password in `MAIL_PASSWORD`
     - Set `ADMIN_EMAIL` to where you want to receive notifications

3. Start the Flask server:
   ```bash
   /usr/local/bin/python3.13 app.py
   ```

4. Open:
   - http://127.0.0.1:5000

## Admin Panel
- Login at `/admin/login`
- Default credentials: `admin` / `changeme123`
- Change via environment variables: `ADMIN_USERNAME` and `ADMIN_PASSWORD`

## Email Notifications
When configured, you'll receive email notifications for:
- New contact form submissions (with name, email, and message)

To enable:
1. Set up environment variables in `.env` file
2. For Gmail users:
   - Go to Google Account → Security
   - Enable 2-Step Verification
   - Create App Password for "Mail"
   - Use that password in `.env`

## Tech
- Flask
- Tailwind CSS (CDN)
- Flask-Mail (email notifications)
- SQLite (data storage)
