# Email Notification Setup Guide

## Quick Start - Gmail Setup

1. **Create a `.env` file** in the project root:
   ```bash
   cp .env.example .env
   ```

2. **Set up Gmail App Password**:
   - Go to: https://myaccount.google.com/security
   - Enable "2-Step Verification" (if not already enabled)
   - Search for "App Passwords"
   - Create a new app password for "Mail"
   - Copy the 16-character password

3. **Edit `.env` file** with your details:
   ```
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx  # Your app password
   ADMIN_EMAIL=your-email@gmail.com    # Where you want notifications
   MAIL_SUPPRESS_SEND=False            # Must be False in production
   ```

4. **Test it**:
   - Restart your Flask app
   - Fill out the contact form on your website
   - Check your email for the notification!

## Alternative Providers

### Outlook/Hotmail
```
MAIL_SERVER=smtp-mail.outlook.com
MAIL_PORT=587
MAIL_USERNAME=your-email@outlook.com
MAIL_PASSWORD=your-password
```

### Yahoo
```
MAIL_SERVER=smtp.mail.yahoo.com
MAIL_PORT=587
MAIL_USERNAME=your-email@yahoo.com
MAIL_PASSWORD=your-app-password
```

### Custom Domain (e.g., cPanel hosting)
Check your hosting provider's documentation for SMTP settings.

## Troubleshooting

**Not receiving emails?**
- Check spam/junk folder
- Verify `.env` file is in the project root
- Confirm `MAIL_SUPPRESS_SEND=False` in production
- Ensure credentials are correct
- Check Flask terminal for error messages

**Gmail "Less secure app" error?**
- Use App Passwords instead of your regular password
- App Passwords require 2-Step Verification to be enabled

## Without Email Setup

The website works fine without email configuration - contact submissions are still saved to the database and visible in the admin panel at `/admin`. Email notifications are optional.
