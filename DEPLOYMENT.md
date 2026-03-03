# Deployment Guide: Dance with Sizzy Afro

This guide walks you through deploying your website to production using GitHub and Render.

## Prerequisites

- GitHub account (free)
- Render account (free: https://render.com)
- Your domain: **sizzyafro.me**

## Step 1: Initialize Git Repository

```bash
cd /home/sizzyafro/Desktop/Website
git init
git add .
git commit -m "Initial commit: Dance with Sizzy Afro website"
```

## Step 2: Create GitHub Repository

1. Go to **https://github.com/new**
2. Repository name: `sizzy-afro-website` (or similar)
3. Description: `Dance with Sizzy Afro - Community & Profile Growth`
4. Choose **Public** or **Private** (your choice)
5. DO NOT initialize with README (you already have one)
6. Click **Create repository**

## Step 3: Push to GitHub

After creating the repository, you'll see commands. Run these:

```bash
git remote add origin https://github.com/YOUR_USERNAME/sizzy-afro-website.git
git branch -M main
git push -u origin main
```

Replace `YOUR_USERNAME` with your actual GitHub username.

## Step 4: Deploy to Render (Free Tier)

### 4a. Create Render Account & Connect GitHub
1. Go to **https://render.com**
2. Click **Sign up** → Choose **GitHub**
3. Authorize Render to access your GitHub account

### 4b. Create New Web Service
1. Go to Dashboard → **New +** → **Web Service**
2. Select your repository: `sizzy-afro-website`
3. Fill in details:
   - **Name**: `sizzy-afro-website`
   - **Runtime**: `Python 3`
   - **Build Command**: (auto-filled from render.yaml) `pip install -r requirements.txt`
   - **Start Command**: (auto-filled) `gunicorn app:app`
   - **Instance Type**: `Free` (0.5 CPU, 0.5 GB RAM)
   - **Region**: `Oregon` (or closest to you)

### 4c. Add Environment Variables
In Render dashboard, go to **Environment** section and add:

```
FLASK_DEBUG=false
FLASK_ENV=production
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your-secure-password
ADMIN_EMAIL=your-email@gmail.com
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

**Note on Gmail password**: Use an [App Password](https://support.google.com/accounts/answer/185833), not your regular password.

### 4d. Deploy
Click **Create Web Service** → Render will automatically build and deploy!

Website will be live at: `https://sizzy-afro-website.onrender.com` (or your custom name)

## Step 5: Connect Your Domain (sizzyafro.me)

### 5a. Get Your Render Domain Info
1. Go to your Render service settings
2. Find **Custom Domain** section
3. Note the **CNAME** target provided by Render

### 5b. Update DNS at Your Domain Registrar
1. Log into your domain registrar (GoDaddy, Namecheap, etc.)
2. Go to **DNS Settings**
3. Add/Update CNAME record:
   - **Name/Subdomain**: `www` (for www.sizzyafro.me)
   - **Value**: Your Render CNAME (e.g., `sizzy-afro-website.onrender.com`)
4. Add another CNAME for root domain `@`:
   - **Name**: `@`
   - **Value**: Same Render CNAME

(Or if your registrar doesn't support root CNAME, use A records pointing to Render's IP)

5. Click **Save** and wait 24-48 hours for DNS to propagate

### 5c. Configure SSL in Render
1. Back in Render dashboard for your service
2. Go to **Custom Domain**
3. Enter your domain: `sizzyafro.me`
4. Click **Add Custom Domain**
5. Render will generate a free SSL certificate (takes a few minutes)

## Step 6: Auto-Deployments

Every time you push to GitHub:
```bash
git add .
git commit -m "Update description"
git push origin main
```

Render will automatically build and deploy within 1-2 minutes!

## Step 7: Database & File Persistence

⚠️ **Important**: Render's free tier has ephemeral storage. This means:
- `submissions.db` will be reset when the app restarts
- User submissions and admin content will NOT persist

### Solution: Use PostgreSQL (Optional)

For production, replace SQLite with PostgreSQL:
1. Create Render PostgreSQL instance (free tier available)
2. Update `app.py` to use PostgreSQL
3. Update `requirements.txt` to include `psycopg2`

Or accept the limitation for now and back up your database regularly.

## Step 8: Monitoring

- Check deployment status: Render Dashboard → Logs
- Monitor errors: Check **Render Logs** tab in real-time
- Performance: Render shows CPU/Memory usage

## Troubleshooting

### Build Fails
Check logs in Render Dashboard. Common issues:
- Missing import: Ensure `requirements.txt` is updated
- Python version mismatch: Should be 3.11+
- Missing environment variables: Add them in Render settings

### Domain Not Working
- Wait 24-48 hours for DNS propagation
- Check DNS with: `nslookup sizzyafro.me`
- Verify CNAME records are correct in your registrar

### Email Not Sending
- Verify MAIL_USERNAME and MAIL_PASSWORD in environment
- Use Gmail App Password (not regular password)
- Check Render logs for SMTP errors

## Next Steps

1. **Test everything**: Visit `https://sizzyafro.me` and test all pages
2. **Contact form**: Submit a test message to verify email notifications
3. **Admin panel**: Log in to `/admin` and test CRUD operations
4. **Monitor logs**: Keep an eye on Render logs for errors

## Useful Commands

```bash
# View git status
git status

# Pull latest changes
git pull origin main

# Check git history
git log --oneline

# Add all changes and commit
git add . && git commit -m "Update message"

# Push to GitHub (triggers Render deploy)
git push origin main
```

---

**Questions?** Check Render's documentation: https://docs.render.com

Good luck launching Dance with Sizzy Afro! 🎉
